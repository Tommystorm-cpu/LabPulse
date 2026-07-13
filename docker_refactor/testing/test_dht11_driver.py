"""DHT11 driver tests that do not require Raspberry Pi GPIO hardware."""

from pathlib import Path
import sys
from typing import Any, Callable


sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_hardware.drivers import dht11_driver
from labpulse_hardware.drivers.dht11_driver import Driver


class FakeBoard:
    """Minimal board module stand-in with one DHT pin."""

    D4 = object()


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

    settings = {"pin_name": "D4", "read_interval_seconds": 2.0}
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
    """Check setup and one sample return normalized DHT11 readings."""

    install_fake_modules()
    driver = make_driver(read_interval_seconds=0.01)

    assert_equal(driver.setup(), True, "setup")
    assert_equal(driver.get_status(), "online", "status")
    assert_equal(driver.read(), {"temperature": 21.3, "humidity": 45.7}, "readings")


def test_read_interval_throttles_samples() -> None:
    """Check DHT reads are throttled to avoid hammering the sensor."""

    install_fake_modules()
    driver = make_driver(read_interval_seconds=60.0)

    assert_equal(driver.setup(), True, "setup")
    assert_equal(driver.read(), {"temperature": 21.3, "humidity": 45.7}, "first reading")
    assert_equal(driver.read(), None, "throttled reading")


def test_runtime_error_keeps_driver_online() -> None:
    """Check common DHT timing errors do not disconnect the driver."""

    install_fake_modules(FakeDhtDevice(FakeBoard.D4, read_error=RuntimeError("timing")))
    driver = make_driver(read_interval_seconds=0.01)

    assert_equal(driver.setup(), True, "setup")
    assert_equal(driver.read(), None, "read")
    assert_equal(driver.connected, True, "connected")
    assert_equal(driver.get_status(), "online", "status")


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
