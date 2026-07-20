"""DHT11 driver tests that do not require Raspberry Pi GPIO hardware."""

from pathlib import Path
import sys
from typing import Any, Callable
from unittest.mock import Mock


sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_hardware.drivers import dht11_driver
from labpulse_hardware.drivers.dht11_driver import Driver


class FakeBoard:
    """Minimal board module stand-in with one DHT pin."""

    D4 = object()


class FakeClock:
    """Controllable monotonic clock for freshness and reconnect tests."""

    def __init__(self, value: float = 100.0) -> None:
        """Start the clock at a non-zero monotonic value."""

        self.value = value

    def __call__(self) -> float:
        """Return the current fake monotonic time."""

        return self.value

    def advance(self, seconds: float) -> None:
        """Move the fake clock forward."""

        self.value += seconds


class FakeDhtDevice:
    """Fake Adafruit DHT11 object."""

    def __init__(
        self,
        pin: object,
        use_pulseio: bool = False,
        temperature: float | None = 21.26,
        humidity: float | None = 45.74,
        read_error: Exception | None = None,
    ) -> None:
        """Capture constructor arguments and configure fake sample behavior."""

        self.pin = pin
        self.use_pulseio = use_pulseio
        self._temperature = temperature
        self._humidity = humidity
        self.read_error = read_error
        self.exited = False

    @property
    def temperature(self) -> float | None:
        """Return a fake temperature or raise a configured error."""

        if self.read_error:
            raise self.read_error
        return self._temperature

    @property
    def humidity(self) -> float | None:
        """Return a fake humidity or raise a configured error."""

        if self.read_error:
            raise self.read_error
        return self._humidity

    def exit(self) -> None:
        """Mark the fake device as released."""

        self.exited = True


class FakeAdafruitDht:
    """Minimal adafruit_dht module stand-in."""

    def __init__(self, device: FakeDhtDevice | None = None) -> None:
        """Create a fake module that returns the provided device."""

        self.device = device

    def DHT11(self, pin: object, use_pulseio: bool = False) -> FakeDhtDevice:
        """Return a fake DHT11 device."""

        if self.device is None:
            self.device = FakeDhtDevice(pin, use_pulseio=use_pulseio)
        return self.device


def make_driver(**overrides: Any) -> Driver:
    """Build a DHT11 driver with optional setting overrides."""

    settings = {
        "pin_name": "D4",
        "read_interval_seconds": 2.0,
        "reconnect_interval_seconds": 5.0,
        "maximum_measurement_age_seconds": 300.0,
    }
    settings.update(overrides)
    return Driver(name="room_environment", **settings)


def install_fake_modules(device: FakeDhtDevice | None = None, board: object | None = None) -> None:
    """Patch dht11_driver imports so tests do not need Pi-only packages."""

    dht11_driver.adafruit_dht = FakeAdafruitDht(device)
    dht11_driver.board = board or FakeBoard


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise AssertionError when two values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_setup_and_read_returns_rounded_values() -> None:
    """Check setup and one sample return normalized DHT11 measurements."""

    install_fake_modules()
    driver = make_driver(read_interval_seconds=0.01)

    assert_equal(driver.setup(), True, "setup")
    assert_equal(driver.get_status(), "online", "status")
    assert_equal(driver.read(), {"temperature": 21.3, "humidity": 45.7}, "measurements")


def test_read_interval_throttles_samples() -> None:
    """Check DHT reads are throttled to avoid hammering the sensor."""

    install_fake_modules()
    driver = make_driver(read_interval_seconds=60.0)

    assert_equal(driver.setup(), True, "setup")
    assert_equal(driver.read(), {"temperature": 21.3, "humidity": 45.7}, "first measurement")
    assert_equal(driver.read(), None, "throttled measurement")


def test_runtime_error_keeps_driver_online() -> None:
    """Check common DHT timing errors do not disconnect the driver."""

    install_fake_modules(FakeDhtDevice(FakeBoard.D4, read_error=RuntimeError("timing")))
    driver = make_driver(read_interval_seconds=0.01)

    assert_equal(driver.setup(), True, "setup")
    assert_equal(driver.read(), None, "read")
    assert_equal(driver.connected, True, "connected")
    assert_equal(driver.get_status(), "online", "status")


def test_sustained_runtime_errors_report_and_recover_health() -> None:
    """Check sustained missed samples become error until a valid sample returns."""

    clock = FakeClock()
    device = FakeDhtDevice(FakeBoard.D4, read_error=RuntimeError("not found"))
    install_fake_modules(device)
    driver = make_driver(
        read_interval_seconds=1.0,
        maximum_measurement_age_seconds=5.0,
        monotonic=clock,
    )

    assert_equal(driver.setup(), True, "setup")
    assert_equal(driver.read(), None, "first failed sample")
    assert_equal(driver.get_status(), "online", "transient failure status")
    clock.advance(4.9)
    assert_equal(driver.read(), None, "failure before freshness deadline")
    assert_equal(driver.get_status(), "online", "status before freshness deadline")
    clock.advance(1.0)
    assert_equal(driver.read(), None, "failure at freshness deadline")
    assert_equal(driver.get_status(), "error", "sustained failure status")

    device.read_error = None
    clock.advance(1.0)
    assert_equal(
        driver.read(),
        {"temperature": 21.3, "humidity": 45.7},
        "recovery measurement",
    )
    assert_equal(driver.get_status(), "online", "recovered status")


def test_repeated_runtime_errors_are_log_rate_limited() -> None:
    """Check a missing DHT sensor cannot flood persistent logs every poll."""

    clock = FakeClock()
    install_fake_modules(
        FakeDhtDevice(FakeBoard.D4, read_error=RuntimeError("not found"))
    )
    driver = make_driver(
        read_interval_seconds=1.0,
        maximum_measurement_age_seconds=300.0,
        monotonic=clock,
    )
    driver.logger = Mock()

    assert_equal(driver.setup(), True, "setup")
    assert_equal(driver.read(), None, "first failure")
    clock.advance(1.0)
    assert_equal(driver.read(), None, "second failure")
    assert_equal(driver.logger.warning.call_count, 1, "warnings within one minute")
    clock.advance(59.0)
    assert_equal(driver.read(), None, "failure after one minute")
    assert_equal(driver.logger.warning.call_count, 2, "minute warning refresh")


def test_unexpected_error_disconnects_then_reconnects() -> None:
    """Check unexpected DHT failures release GPIO and retry initialization."""

    clock = FakeClock()
    device = FakeDhtDevice(FakeBoard.D4, read_error=ValueError("GPIO failure"))
    install_fake_modules(device)
    driver = make_driver(
        read_interval_seconds=0.01,
        reconnect_interval_seconds=5.0,
        monotonic=clock,
    )

    assert_equal(driver.setup(), True, "setup")
    assert_equal(driver.read(), None, "unexpected failure")
    assert_equal(driver.connected, False, "disconnected after failure")
    assert_equal(device.exited, True, "GPIO released")
    assert_equal(driver.get_status(), "disconnected", "failure status")

    device.read_error = None
    clock.advance(4.0)
    assert_equal(driver.read(), None, "reconnect remains rate limited")
    assert_equal(driver.connected, False, "still disconnected")
    clock.advance(1.0)
    assert_equal(driver.read(), None, "reconnect attempt")
    assert_equal(driver.connected, True, "reconnected")
    clock.advance(0.01)
    assert_equal(
        driver.read(),
        {"temperature": 21.3, "humidity": 45.7},
        "measurement after reconnect",
    )


def test_unknown_pin_fails_setup() -> None:
    """Check a bad board pin fails clearly."""

    install_fake_modules(board=object())
    driver = make_driver(pin_name="D99")

    assert_equal(driver.setup(), False, "setup")
    assert_equal(driver.connected, False, "connected")
    assert_equal(driver.get_status(), "disconnected", "status")


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("setup and read returns rounded values", test_setup_and_read_returns_rounded_values),
    ("read interval throttles samples", test_read_interval_throttles_samples),
    ("runtime error keeps driver online", test_runtime_error_keeps_driver_online),
    (
        "sustained runtime errors report and recover health",
        test_sustained_runtime_errors_report_and_recover_health,
    ),
    (
        "repeated runtime errors are log rate limited",
        test_repeated_runtime_errors_are_log_rate_limited,
    ),
    (
        "unexpected error disconnects then reconnects",
        test_unexpected_error_disconnects_then_reconnects,
    ),
    ("unknown pin fails setup", test_unknown_pin_fails_setup),
]


def main() -> None:
    """Run all DHT11 driver tests."""

    print("Running DHT11 driver tests")
    print(f"Refactor dir: {REFACTOR_DIR}")
    print()

    passed_count = 0
    for name, test_func in TESTS:
        try:
            test_func()
        except Exception as error:
            print(f"[FAIL] {name}")
            print(f"  error: {type(error).__name__}: {error}")
            print()
            continue

        print(f"[PASS] {name}")
        print()
        passed_count += 1

    failed_count = len(TESTS) - passed_count
    print(f"Summary: {passed_count}/{len(TESTS)} passed, {failed_count} failed")

    if failed_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
