"""Deterministic lifecycle tests for the central hardware runner."""

from typing import Callable
from unittest.mock import Mock

from labpulse.hardware.driver import (
    ConnectionLost,
    DriverUnavailable,
    HardwareDriver,
    HardwareIssue,
    HardwareReadings,
    TransientReadError,
)
from labpulse.hardware.runner import HardwareServiceRunner, RunnerTimings


class FakeClock:
    """Controllable monotonic clock that advances instead of sleeping."""

    def __init__(self, value: float = 100.0) -> None:
        """Start at a non-zero time so zero remains a valid tested timestamp."""

        self.value = value
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        """Return the current fake monotonic time."""

        return self.value

    def sleep(self, seconds: float) -> None:
        """Record and advance through one requested sleep."""

        self.sleeps.append(seconds)
        self.value += seconds

    def advance(self, seconds: float) -> None:
        """Advance explicitly without recording a runner sleep."""

        self.value += seconds


class FakeDriver(HardwareDriver):
    """Script connection and read outcomes without physical hardware."""

    def __init__(
        self,
        connect_results: list[Exception | None] | None = None,
        read_results: list[HardwareReadings | Exception | None] | None = None,
        close_error: Exception | None = None,
    ) -> None:
        """Store scripted outcomes and lifecycle call counters."""

        super().__init__("fake_service")
        self.connect_results = list(connect_results or [None])
        self.read_results = list(read_results or [])
        self.close_error = close_error
        self.connect_calls = 0
        self.read_calls = 0
        self.close_calls = 0

    def connect(self) -> None:
        """Return or raise the next connection outcome."""

        self.connect_calls += 1
        result = self.connect_results.pop(0) if self.connect_results else None
        if isinstance(result, Exception):
            raise result

    def read(self) -> HardwareReadings | None:
        """Return or raise the next read outcome."""

        self.read_calls += 1
        result = self.read_results.pop(0) if self.read_results else None
        if isinstance(result, Exception):
            raise result
        return result

    def close(self) -> None:
        """Record cleanup and optionally simulate a cleanup failure."""

        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


class FakePublisher:
    """Record runner status, measurement, and cleanup publications."""

    def __init__(self, disconnect_error: Exception | None = None) -> None:
        """Initialize empty publication history."""

        self.statuses: list[str] = []
        self.measurements: list[dict[str, float]] = []
        self.events: list[tuple[str, object]] = []
        self.disconnect_calls = 0
        self.disconnect_error = disconnect_error

    def publish(self, measurements: dict[str, float]) -> None:
        """Record one measurement mapping."""

        self.measurements.append(dict(measurements))
        self.events.append(("measurements", dict(measurements)))

    def publish_status(self, status: str) -> None:
        """Record one status transition."""

        self.statuses.append(status)
        self.events.append(("status", status))

    def disconnect(self) -> None:
        """Record publisher cleanup and optionally fail."""

        self.disconnect_calls += 1
        if self.disconnect_error is not None:
            raise self.disconnect_error


def make_runner(
    driver: FakeDriver,
    publisher: FakePublisher | None = None,
    clock: FakeClock | None = None,
    *,
    reconnect: float = 5.0,
    maximum_age: float = 10.0,
    read_interval: float = 0.0,
    logger: Mock | None = None,
) -> tuple[HardwareServiceRunner, FakePublisher, FakeClock]:
    """Build one deterministic runner and its observable collaborators."""

    actual_publisher = publisher or FakePublisher()
    actual_clock = clock or FakeClock()
    runner = HardwareServiceRunner(
        driver,
        actual_publisher,
        RunnerTimings(
            reconnect_interval_seconds=reconnect,
            maximum_measurement_age_seconds=maximum_age,
            read_interval_seconds=read_interval,
        ),
        clock=actual_clock,
        sleep=actual_clock.sleep,
        logger=logger,
    )
    return runner, actual_publisher, actual_clock


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise an informative assertion when values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_connect_and_publish_batch() -> None:
    """Connect once, publish status transitions, then publish one batch."""

    driver = FakeDriver(read_results=[HardwareReadings({"pressure": 1.23})])
    runner, publisher, _ = make_runner(driver)

    runner.step()
    assert_equal(publisher.statuses, ["reconnecting"], "awaiting first sample")
    runner.step()
    assert_equal(publisher.measurements, [{"pressure": 1.23}], "measurements")
    assert_equal(publisher.statuses, ["reconnecting", "online"], "validated online")
    assert_equal(
        publisher.events,
        [
            ("status", "reconnecting"),
            ("measurements", {"pressure": 1.23}),
            ("status", "online"),
        ],
        "fresh data precedes online status",
    )


def test_connection_retry_is_throttled_and_recovers() -> None:
    """Retry an unavailable device only after the configured interval."""

    driver = FakeDriver(
        connect_results=[DriverUnavailable("missing"), None],
        read_results=[HardwareReadings({"pressure": 1.0})],
    )
    runner, publisher, clock = make_runner(driver, reconnect=5.0)

    runner.step()
    assert_equal(driver.connect_calls, 1, "initial attempt")
    assert_equal(publisher.statuses, ["reconnecting"], "failure status")
    runner.step()
    assert_equal(driver.connect_calls, 1, "throttled attempt")
    clock.advance(4.9)
    runner.step()
    assert_equal(driver.connect_calls, 2, "retry attempt")
    assert_equal(publisher.statuses[-1], "reconnecting", "awaiting recovery sample")
    runner.step()
    assert_equal(publisher.statuses[-1], "online", "recovery status")


def test_transient_failures_recycle_stale_driver_and_recover() -> None:
    """Retain brief failures, then recreate stale hardware before recovery."""

    driver = FakeDriver(
        connect_results=[None, None],
        read_results=[
            TransientReadError("timing"),
            TransientReadError("timing"),
            HardwareReadings({"temperature": 21.4}),
        ]
    )
    runner, publisher, clock = make_runner(driver, maximum_age=5.0)

    runner.step()
    runner.step()
    assert_equal(driver.close_calls, 0, "driver retained after transient failure")
    assert_equal(publisher.statuses[-1], "reconnecting", "initial transient status")
    clock.advance(5.0)
    runner.step()
    assert_equal(publisher.statuses[-1], "error", "freshness status")
    assert_equal(driver.close_calls, 1, "stale driver closed")
    clock.advance(5.0)
    runner.step()
    assert_equal(driver.connect_calls, 2, "stale driver reinitialized")
    runner.step()
    assert_equal(publisher.statuses[-1], "online", "recovered status")
    assert_equal(publisher.measurements, [{"temperature": 21.4}], "recovery data")


def test_transient_failure_logs_are_rate_limited() -> None:
    """Prevent repeated expected sample failures from flooding service logs."""

    logger = Mock()
    driver = FakeDriver(
        read_results=[
            TransientReadError("timing"),
            TransientReadError("timing"),
            TransientReadError("timing"),
        ]
    )
    runner, _, clock = make_runner(driver, logger=logger)

    runner.step()
    runner.step()
    runner.step()
    assert_equal(logger.warning.call_count, 1, "warnings within interval")
    clock.advance(60.0)
    runner.step()
    assert_equal(logger.warning.call_count, 2, "warning after interval")


def test_status_logs_include_freshness_context() -> None:
    """Put the service transition and last-reading state in operator logs."""

    logger = Mock()
    driver = FakeDriver(read_results=[HardwareReadings({"temperature": 21.0})])
    runner, _, _ = make_runner(driver, logger=logger)

    runner.step()
    runner.step()
    rendered_calls = [" ".join(str(value) for value in call.args) for call in logger.info.call_args_list]
    if not any(
        "Service status changed" in call and "last successful reading" in call
        for call in rendered_calls
    ):
        raise AssertionError(f"status log lacks freshness context: {rendered_calls!r}")


def test_connection_loss_closes_and_reconnects() -> None:
    """Close a lost connection, wait, reconnect, and resume publication."""

    driver = FakeDriver(
        connect_results=[None, None],
        read_results=[
            ConnectionLost("unplugged"),
            HardwareReadings({"pressure": 1.4}),
        ],
    )
    runner, publisher, clock = make_runner(driver, reconnect=5.0)

    runner.step()
    runner.step()
    assert_equal(driver.close_calls, 1, "close after connection loss")
    assert_equal(publisher.statuses[-1], "disconnected", "loss status")
    runner.step()
    assert_equal(publisher.statuses[-1], "reconnecting", "waiting status")
    clock.advance(5.0)
    runner.step()
    runner.step()
    assert_equal(publisher.measurements, [{"pressure": 1.4}], "recovered data")


def test_unexpected_read_error_enters_error_and_recovers() -> None:
    """Contain an unexpected driver error and retain the service process."""

    driver = FakeDriver(
        connect_results=[None, None],
        read_results=[
            ValueError("bad library state"),
            HardwareReadings({"value": 2.0}),
        ],
    )
    runner, publisher, clock = make_runner(driver, reconnect=2.0, logger=Mock())

    runner.step()
    runner.step()
    assert_equal(publisher.statuses[-1], "error", "unexpected failure status")
    clock.advance(2.0)
    runner.step()
    runner.step()
    assert_equal(publisher.measurements, [{"value": 2.0}], "post-error data")


def test_component_issue_keeps_partial_measurements() -> None:
    """Publish valid values alongside an X1200-style component fault."""

    batch = HardwareReadings(
        {"voltage": 4.13, "battery_level": 94.2},
        issues=(HardwareIssue("gpio_fault", "GPIO unavailable"),),
    )
    driver = FakeDriver(read_results=[batch])
    runner, publisher, _ = make_runner(driver)

    runner.step()
    runner.step()
    assert_equal(publisher.statuses[-1], "gpio_fault", "component status")
    assert_equal(
        publisher.measurements,
        [{"voltage": 4.13, "battery_level": 94.2}],
        "partial measurements",
    )


def test_read_interval_is_scheduled_by_runner() -> None:
    """Throttle driver reads centrally instead of inside each implementation."""

    driver = FakeDriver(
        read_results=[
            HardwareReadings({"value": 1.0}),
            HardwareReadings({"value": 2.0}),
        ]
    )
    runner, publisher, clock = make_runner(driver, read_interval=2.0)

    runner.step()
    runner.step()
    runner.step()
    assert_equal(driver.read_calls, 1, "reads before interval")
    clock.advance(1.9)
    runner.step()
    assert_equal(driver.read_calls, 2, "reads after interval")
    assert_equal(
        publisher.measurements,
        [{"value": 1.0}, {"value": 2.0}],
        "scheduled measurements",
    )


def test_cleanup_failures_do_not_skip_other_cleanup() -> None:
    """Contain cleanup errors and still close both lifecycle collaborators."""

    logger = Mock()
    driver = FakeDriver(close_error=OSError("driver close failed"))
    publisher = FakePublisher(disconnect_error=OSError("publisher close failed"))
    runner, _, _ = make_runner(driver, publisher=publisher, logger=logger)

    runner.close()
    runner.close()
    assert_equal(driver.close_calls, 1, "driver cleanup attempts")
    assert_equal(publisher.disconnect_calls, 1, "publisher cleanup attempts")
    assert_equal(logger.warning.call_count, 2, "cleanup warnings")
