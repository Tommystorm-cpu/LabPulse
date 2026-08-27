"""Run one hardware service through connection, reading, and recovery.

The runner owns the lifecycle shared by every device::

    connect -> read -> publish
       ^                  |
       +------ retry <----+

Drivers only open hardware, return readings, and close hardware. The runner
decides when to retry, when readings are stale, and which status to publish.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
import logging
import time
from typing import Protocol

from labpulse.hardware.driver import (
    ConnectionLost,
    DriverUnavailable,
    HardwareDriver,
    TransientReadError,
)


EMPTY_READ_RETRY_DELAY_SECONDS = 0.1


class ServiceStatus(StrEnum):
    """Health states owned and published by the hardware runner."""

    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    ONLINE = "online"
    ERROR = "error"


class ServicePublisher(Protocol):
    """Operations the runner needs from a measurement publisher."""

    def publish(self, measurements: dict[str, float]) -> None:
        """Publish current measurements."""

    def publish_status(self, status: str) -> None:
        """Publish the current service status."""

    def disconnect(self) -> None:
        """Close the publisher connection."""


@dataclass(frozen=True)
class RunnerTimings:
    """Timing settings shared by every hardware service."""

    reconnect_interval_seconds: float
    maximum_measurement_age_seconds: float
    read_interval_seconds: float = 0.0
    failure_log_interval_seconds: float = 60.0


class HardwareServiceRunner:
    """Keep one hardware service connected, current, and safely recoverable."""

    def __init__(
        self,
        driver: HardwareDriver,
        publisher: ServicePublisher,
        timings: RunnerTimings,
        *,
        print_measurements: bool = False,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        logger: logging.Logger | None = None,
    ) -> None:
        """Store dependencies and begin in a disconnected state."""

        # The three main components define what this service reads, where its
        # results go, and how often lifecycle actions should happen.
        self.driver = driver
        self.publisher = publisher
        self.timings = timings

        # Runtime facilities are replaceable for diagnostics and deterministic
        # tests, but are not part of the runner's public state.
        self._print_measurements = print_measurements
        self._clock = clock
        self._sleep = sleep
        self._logger = logger or logging.getLogger(f"HardwareServiceRunner.{driver.service_name}")

        # Everything below is internal lifecycle bookkeeping.
        current_time = self._clock()
        self._is_connected = False
        self._is_closed = False
        self._current_status: str | None = None
        self._next_connection_attempt_at = current_time
        self._next_reading_at = current_time
        self._connection_started_at: float | None = None
        self._last_successful_read_at: float | None = None
        self._last_transient_failure_log_at: float | None = None

    def run_forever(self) -> None:
        """Run continuously until the process is interrupted."""

        try:
            while True:
                self.step()
        finally:
            self.close()

    def step(self) -> None:
        """Perform the next connection or reading action that is due."""

        if self._is_closed:
            raise RuntimeError("HardwareServiceRunner is closed")

        current_time = self._clock()

        # Connect first. Failed devices wait for their scheduled retry rather
        # than spinning continuously and filling the service logs.
        if not self._is_connected:
            if current_time < self._next_connection_attempt_at:
                self._publish_status(ServiceStatus.RECONNECTING)
                time_until_retry = self._next_connection_attempt_at - current_time
                self._sleep(time_until_retry)
                return
            self._connect(current_time)
            return

        # The runner owns read timing so individual drivers never contain their
        # own polling loops or sleeps.
        if current_time < self._next_reading_at:
            time_until_read = self._next_reading_at - current_time
            self._sleep(time_until_read)
            return

        self._read_and_publish()

    def close(self) -> None:
        """Close the driver and publisher once, even after an earlier failure."""

        if self._is_closed:
            return

        self._is_closed = True
        self._close_driver_safely()
        self._is_connected = False

        try:
            self.publisher.disconnect()
        except Exception as error:
            self._logger.warning("Publisher cleanup failed: %s", error)

    def _connect(self, connection_attempted_at: float) -> None:
        """Attempt to connect and schedule another attempt when it fails."""

        try:
            self.driver.connect()
        except DriverUnavailable as error:
            self._logger.error("Hardware connection failed: %s", error)
            self._prepare_for_reconnect(ServiceStatus.RECONNECTING, connection_attempted_at)
            return
        except Exception as error:
            self._logger.exception("Unexpected hardware connection failure: %s", error)
            self._prepare_for_reconnect(ServiceStatus.ERROR, connection_attempted_at)
            return

        self._is_connected = True
        self._connection_started_at = connection_attempted_at
        self._last_successful_read_at = None
        self._last_transient_failure_log_at = None
        self._next_reading_at = connection_attempted_at

        # An open handle is not proof that the device can produce data. The
        # service remains reconnecting until its first valid reading arrives.
        self._publish_status(ServiceStatus.RECONNECTING)

    def _read_and_publish(self) -> None:
        """Read one sample, handle its outcome, and publish valid values."""

        try:
            hardware_readings = self.driver.read()
        except TransientReadError as error:
            reading_completed_at = self._clock()
            self._log_transient_failure(error, reading_completed_at)
            self._next_reading_at = reading_completed_at + self.timings.read_interval_seconds
            self._handle_missing_readings(reading_completed_at)
            return
        except ConnectionLost as error:
            self._logger.error("Hardware connection lost: %s", error)
            self._prepare_for_reconnect(ServiceStatus.DISCONNECTED, self._clock())
            return
        except Exception as error:
            self._logger.exception("Unexpected hardware read failure: %s", error)
            self._prepare_for_reconnect(ServiceStatus.ERROR, self._clock())
            return

        reading_completed_at = self._clock()
        self._next_reading_at = reading_completed_at + self.timings.read_interval_seconds

        if hardware_readings is None:
            self._handle_missing_readings(reading_completed_at)
            return

        values = dict(hardware_readings.values)
        if not values:
            self._handle_missing_readings(reading_completed_at)
            return

        self._last_successful_read_at = reading_completed_at
        self._last_transient_failure_log_at = None

        if self._print_measurements:
            self._logger.info("Measurements: %s", values)

        # Values must arrive before the online status. Home Assistant recovery
        # rules are gated by status and could otherwise use an old retained value.
        self.publisher.publish(values)

        reading_status = hardware_readings.issues[0].code if hardware_readings.issues else ServiceStatus.ONLINE
        self._publish_status(reading_status)

    def _handle_missing_readings(self, current_time: float) -> None:
        """Reconnect stale hardware and avoid a busy loop after an empty read."""

        freshness_started_at = (
            self._last_successful_read_at
            if self._last_successful_read_at is not None
            else self._connection_started_at
        )
        if freshness_started_at is not None:
            missing_for_seconds = current_time - freshness_started_at
            readings_are_stale = missing_for_seconds >= self.timings.maximum_measurement_age_seconds

            if readings_are_stale:
                if self._last_successful_read_at is None:
                    last_success = "none since this connection opened"
                else:
                    seconds_since_success = current_time - self._last_successful_read_at
                    last_success = f"{seconds_since_success:.1f} seconds ago"

                self._logger.error(
                    "No valid hardware readings for %.1f seconds "
                    "(last successful reading: %s); reinitializing driver. "
                    "Check the configured device, cable, power, and service logs.",
                    missing_for_seconds,
                    last_success,
                )
                self._prepare_for_reconnect(ServiceStatus.ERROR, current_time)

        if self.timings.read_interval_seconds == 0:
            self._sleep(EMPTY_READ_RETRY_DELAY_SECONDS)

    def _log_transient_failure(self, error: TransientReadError, current_time: float) -> None:
        """Log recurring sample failures at a bounded rate."""

        enough_time_has_passed = (
            self._last_transient_failure_log_at is None
            or current_time - self._last_transient_failure_log_at
            >= self.timings.failure_log_interval_seconds
        )
        if enough_time_has_passed:
            self._logger.warning("Transient hardware read failure: %s", error)
            self._last_transient_failure_log_at = current_time

    def _prepare_for_reconnect(self, status: ServiceStatus, current_time: float) -> None:
        """Close hardware, clear reading history, and schedule a reconnect."""

        self._close_driver_safely()
        self._is_connected = False
        self._next_connection_attempt_at = current_time + self.timings.reconnect_interval_seconds
        self._connection_started_at = None
        self._last_successful_read_at = None
        self._publish_status(status)

    def _close_driver_safely(self) -> None:
        """Prevent a driver cleanup error from stopping service recovery."""

        try:
            self.driver.close()
        except Exception as error:
            self._logger.warning("Driver cleanup failed: %s", error)

    def _publish_status(self, status: ServiceStatus | str) -> None:
        """Publish status changes without repeating the same value."""

        new_status = status.value if isinstance(status, ServiceStatus) else status
        if new_status == self._current_status:
            return

        previous_status = self._current_status or ServiceStatus.DISCONNECTED.value
        self._current_status = new_status

        current_time = self._clock()
        if self._last_successful_read_at is None:
            last_success = "none"
        else:
            seconds_since_success = max(0.0, current_time - self._last_successful_read_at)
            last_success = f"{seconds_since_success:.1f} seconds ago"

        self._logger.info(
            "Service status changed: %s -> %s (last successful reading: %s)",
            previous_status,
            new_status,
            last_success,
        )
        self.publisher.publish_status(new_status)
