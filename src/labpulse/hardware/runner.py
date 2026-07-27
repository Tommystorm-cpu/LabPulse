"""Central connection, retry, freshness, status, and cleanup lifecycle.

The runner is a small state machine::

    disconnected -> connect -> online -> disconnected
           ^          |          |
           +---- reconnecting <---+

An unavailable connection waits in ``reconnecting`` before trying again.
Connection loss closes the hardware and returns to ``disconnected``. A
transient sample failure retains the connection, but prolonged missing data
changes the published status to ``error`` and recreates the driver. A connection
is not reported online until it produces a valid reading batch.
"""

from collections.abc import Callable
from dataclasses import dataclass
import logging
import time
from typing import Protocol

from labpulse.hardware.api import (
    BaseSensorDriver,
    ConnectionLost,
    DriverUnavailable,
    ServiceStatus,
    TransientReadError,
)


class MeasurementPublisher(Protocol):
    """Publishing operations required by the hardware runner."""

    def publish(self, measurements: dict[str, float]) -> None:
        """Publish one normalized measurement mapping."""

    def publish_status(self, status: str) -> None:
        """Publish the current service status."""

    def disconnect(self) -> None:
        """Close the publisher connection."""


@dataclass(frozen=True)
class RunnerPolicy:
    """Timing policy applied consistently to one hardware service."""

    reconnect_interval_seconds: float
    maximum_measurement_age_seconds: float
    read_interval_seconds: float = 0.0
    idle_sleep_seconds: float = 0.1
    failure_log_interval_seconds: float = 60.0

    def __post_init__(self) -> None:
        """Reject non-positive safety timings and negative polling intervals."""

        if self.reconnect_interval_seconds <= 0:
            raise ValueError("reconnect_interval_seconds must be greater than zero")
        if self.maximum_measurement_age_seconds <= 0:
            raise ValueError("maximum_measurement_age_seconds must be greater than zero")
        if self.read_interval_seconds < 0:
            raise ValueError("read_interval_seconds cannot be negative")
        if self.idle_sleep_seconds <= 0:
            raise ValueError("idle_sleep_seconds must be greater than zero")
        if self.failure_log_interval_seconds <= 0:
            raise ValueError("failure_log_interval_seconds must be greater than zero")


class HardwareRunner:
    """Run one driver while owning all service-level lifecycle behaviour."""

    def __init__(
        self,
        driver: BaseSensorDriver,
        publisher: MeasurementPublisher | None,
        policy: RunnerPolicy,
        *,
        print_measurements: bool = False,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        logger: logging.Logger | None = None,
    ) -> None:
        """Store dependencies and initialize a disconnected service state."""

        self.driver = driver
        self.publisher = publisher
        self.policy = policy
        self.print_measurements = print_measurements
        self._monotonic = monotonic
        self._sleep = sleep
        self.logger = logger or logging.getLogger(f"HardwareRunner.{driver.name}")
        self.connected = False
        self.status = ServiceStatus.DISCONNECTED.value
        self.next_connect_at = self._monotonic()
        self.next_read_at = self.next_connect_at
        self.monitoring_started_at: float | None = None
        self.last_success_at: float | None = None
        self.last_failure_log_at: float | None = None
        self._status_published = False
        self._closed = False

    def step(self) -> bool:
        """Perform one connection or read action and report measurement publication."""

        if self._closed:
            raise RuntimeError("HardwareRunner is closed")

        # Connection attempts are separately scheduled so unavailable hardware
        # cannot turn the service loop into a busy retry.
        if not self.connected:
            return self._connection_step()

        # Poll intervals are owned here rather than duplicated across drivers.
        now = self._monotonic()
        if now < self.next_read_at:
            self._sleep(min(self.next_read_at - now, self.policy.idle_sleep_seconds))
            return False

        try:
            batch = self.driver.read()
        except TransientReadError as error:
            # Timing misses and incomplete samples do not prove that the
            # underlying connection is broken, so retain it and track freshness.
            completed_at = self._monotonic()
            self._record_transient_failure(error, completed_at)
            self._schedule_next_read(completed_at)
            self._check_freshness(completed_at)
            if self.policy.read_interval_seconds == 0:
                self._sleep(self.policy.idle_sleep_seconds)
            return False
        except ConnectionLost as error:
            # A dead handle must be closed before the next scheduled connect.
            self.logger.error("Hardware connection lost: %s", error)
            self._lose_connection(ServiceStatus.DISCONNECTED)
            return False
        except Exception as error:
            self.logger.exception("Unexpected hardware read failure: %s", error)
            self._lose_connection(ServiceStatus.ERROR)
            return False

        completed_at = self._monotonic()
        self._schedule_next_read(completed_at)
        if batch is None:
            # No complete sample is normal for non-blocking and serial reads,
            # but prolonged absence must eventually affect service health.
            self._check_freshness(completed_at)
            if self.policy.read_interval_seconds == 0:
                self._sleep(self.policy.idle_sleep_seconds)
            return False

        measurements = dict(batch.measurements)
        if not measurements:
            self._check_freshness(completed_at)
            if self.policy.read_interval_seconds == 0:
                self._sleep(self.policy.idle_sleep_seconds)
            return False

        self.last_success_at = completed_at
        self.last_failure_log_at = None
        batch_status = (
            batch.issues[0].code
            if batch.issues
            else ServiceStatus.ONLINE.value
        )

        if self.print_measurements:
            self.logger.info("Measurements: %s", measurements)
        if self.publisher:
            # Publish the new process's values before declaring the service
            # healthy. Home Assistant recovery rules are gated by service
            # status; reversing this order could let a cached pre-restart value
            # produce a false measurement-recovery notification.
            self.publisher.publish(measurements)
        self._set_status(batch_status)
        return True

    def run_forever(self, *, once: bool = False) -> None:
        """Run until interrupted, or until one valid batch in once mode."""

        try:
            while True:
                if self.step() and once:
                    return
        finally:
            self.close()

    def close(self) -> None:
        """Idempotently close the driver and publisher."""

        if self._closed:
            return
        self._closed = True
        self._safe_close_driver()
        self.connected = False
        if self.publisher:
            try:
                self.publisher.disconnect()
            except Exception as error:
                self.logger.warning("Publisher cleanup failed: %s", error)

    def _connection_step(self) -> bool:
        """Attempt one due connection without blocking through the retry interval."""

        now = self._monotonic()
        if now < self.next_connect_at:
            self._set_status(ServiceStatus.RECONNECTING)
            self._sleep(min(self.next_connect_at - now, self.policy.idle_sleep_seconds))
            return False

        try:
            self.driver.connect()
        except DriverUnavailable as error:
            self.logger.error("Hardware connection failed: %s", error)
            self._safe_close_driver()
            self._set_status(ServiceStatus.RECONNECTING)
            self.next_connect_at = now + self.policy.reconnect_interval_seconds
            return False
        except Exception as error:
            self.logger.exception("Unexpected hardware connection failure: %s", error)
            self._safe_close_driver()
            self._set_status(ServiceStatus.ERROR)
            self.next_connect_at = now + self.policy.reconnect_interval_seconds
            return False

        self.connected = True
        self.monitoring_started_at = now
        self.last_success_at = None
        self.last_failure_log_at = None
        self.next_read_at = now
        # Opening a handle does not prove that the sensor can produce data.
        # Stay in reconnecting until the first valid batch prevents false
        # service-recovery notifications for initialized but wedged hardware.
        self._set_status(ServiceStatus.RECONNECTING)
        return False

    def _record_transient_failure(
        self,
        error: TransientReadError,
        now: float,
    ) -> None:
        """Log recurring sample failures at a bounded rate."""

        if (
            self.last_failure_log_at is None
            or now - self.last_failure_log_at
            >= self.policy.failure_log_interval_seconds
        ):
            self.logger.warning("Transient hardware read failure: %s", error)
            self.last_failure_log_at = now

    def _check_freshness(self, now: float) -> None:
        """Recycle hardware after a connected service stops producing valid data."""

        freshness_reference = (
            self.last_success_at
            if self.last_success_at is not None
            else self.monitoring_started_at
        )
        if freshness_reference is None:
            return
        if now - freshness_reference >= self.policy.maximum_measurement_age_seconds:
            if self.last_success_at is None:
                last_success = "none since this connection opened"
            else:
                last_success = f"{now - self.last_success_at:.1f} seconds ago"
            self.logger.error(
                "No valid hardware readings for %.1f seconds "
                "(last successful reading: %s); reinitializing driver. "
                "Check the configured device, cable, power, and service logs.",
                now - freshness_reference,
                last_success,
            )
            self._lose_connection(ServiceStatus.ERROR)

    def _schedule_next_read(self, now: float) -> None:
        """Schedule the next driver read from the current monotonic time."""

        self.next_read_at = now + self.policy.read_interval_seconds

    def _lose_connection(self, status: ServiceStatus) -> None:
        """Release a failed connection and schedule a bounded reconnect."""

        self._safe_close_driver()
        self.connected = False
        now = self._monotonic()
        self.next_connect_at = now + self.policy.reconnect_interval_seconds
        self.monitoring_started_at = None
        self.last_success_at = None
        self._set_status(status)

    def _safe_close_driver(self) -> None:
        """Close hardware without letting cleanup errors kill the service."""

        try:
            self.driver.close()
        except Exception as error:
            self.logger.warning("Driver cleanup failed: %s", error)

    def _set_status(self, status: ServiceStatus | str) -> None:
        """Publish one status transition and suppress repeated values."""

        normalized = status.value if isinstance(status, ServiceStatus) else status
        if self._status_published and normalized == self.status:
            return
        previous = self.status
        self.status = normalized
        self._status_published = True
        now = self._monotonic()
        last_success = (
            "none"
            if self.last_success_at is None
            else f"{max(0.0, now - self.last_success_at):.1f} seconds ago"
        )
        self.logger.info(
            "Service status changed: %s -> %s (last successful reading: %s)",
            previous,
            normalized,
            last_success,
        )
        if self.publisher:
            self.publisher.publish_status(normalized)
