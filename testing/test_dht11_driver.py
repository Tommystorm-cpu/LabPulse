"""Hardware-free contract tests for the Raspberry Pi DHT11 driver."""

from pathlib import Path
import sys
from typing import Callable


sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR / "src"))

from labpulse.hardware.drivers import dht11
from labpulse.hardware.api import (
    ConnectionLost,
    DriverUnavailable,
    TransientReadError,
)
from labpulse.hardware.drivers.dht11 import Driver


class FakeBoard:
    """Minimal board module with one valid pin."""

    D4 = object()


class FakeDhtDevice:
    """Fake Adafruit DHT11 object with configurable values and failures."""

    def __init__(
        self,
        pin: object,
        use_pulseio: bool = False,
        temperature: float | None = 21.26,
        humidity: float | None = 45.74,
        read_error: Exception | None = None,
    ) -> None:
        """Capture construction and sample behavior."""

        self.pin = pin
        self.use_pulseio = use_pulseio
        self._temperature = temperature
        self._humidity = humidity
        self.read_error = read_error
        self.exited = False

    @property
    def temperature(self) -> float | None:
        """Return temperature or raise the configured error."""

        if self.read_error:
            raise self.read_error
        return self._temperature

    @property
    def humidity(self) -> float | None:
        """Return humidity or raise the configured error."""

        if self.read_error:
            raise self.read_error
        return self._humidity

    def exit(self) -> None:
        """Record release of the fake device."""

        self.exited = True


class FakeAdafruitDht:
    """Minimal adafruit_dht module stand-in."""

    def __init__(self, device: FakeDhtDevice | None = None) -> None:
        """Return a supplied device or construct one on demand."""

        self.device = device

    def DHT11(self, pin: object, use_pulseio: bool = False) -> FakeDhtDevice:
        """Construct or return the fake DHT11."""

        if self.device is None:
            self.device = FakeDhtDevice(pin, use_pulseio=use_pulseio)
        return self.device


def install_fake_modules(
    device: FakeDhtDevice | None = None,
    board: object | None = None,
) -> None:
    """Patch Pi-only modules with in-memory stand-ins."""

    dht11.adafruit_dht = FakeAdafruitDht(device)
    dht11.board = board or FakeBoard


def make_driver(pin_name: str = "D4") -> Driver:
    """Build one DHT11 driver."""

    return Driver(name="room_environment", pin_name=pin_name)


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise an informative assertion when values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_raises(expected: type[Exception], action: Callable[[], object]) -> None:
    """Require one expected lifecycle exception."""

    try:
        action()
    except expected:
        return
    raise AssertionError(f"expected {expected.__name__}")


def test_connect_and_read_returns_rounded_batch() -> None:
    """Initialize the GPIO device and normalize one complete sample."""

    install_fake_modules()
    driver = make_driver()

    driver.connect()
    batch = driver.read()
    assert_equal(driver.device.use_pulseio, False, "PulseIn disabled")
    assert_equal(
        dict(batch.measurements),
        {"temperature": 21.3, "humidity": 45.7},
        "measurements",
    )


def test_timing_error_is_transient() -> None:
    """Classify ordinary DHT timing misses without losing the connection."""

    install_fake_modules(
        FakeDhtDevice(FakeBoard.D4, read_error=RuntimeError("timing"))
    )
    driver = make_driver()
    driver.connect()

    assert_raises(TransientReadError, driver.read)
    assert_equal(driver.device is not None, True, "device retained")


def test_incomplete_sample_is_transient() -> None:
    """Classify missing sensor values as a retryable sample failure."""

    install_fake_modules(FakeDhtDevice(FakeBoard.D4, temperature=None))
    driver = make_driver()
    driver.connect()

    assert_raises(TransientReadError, driver.read)


def test_unexpected_read_error_loses_connection() -> None:
    """Classify unexpected GPIO/library failures for runner-managed reconnect."""

    device = FakeDhtDevice(FakeBoard.D4, read_error=ValueError("GPIO failure"))
    install_fake_modules(device)
    driver = make_driver()
    driver.connect()

    assert_raises(ConnectionLost, driver.read)
    driver.close()
    assert_equal(device.exited, True, "device released")


def test_unknown_pin_is_unavailable() -> None:
    """Reject an unknown board pin during connection."""

    install_fake_modules(board=object())
    driver = make_driver("D99")

    assert_raises(DriverUnavailable, driver.connect)


def test_missing_dependencies_are_unavailable() -> None:
    """Report missing optional GPIO packages without an import crash."""

    dht11.adafruit_dht = None
    dht11.board = None

    assert_raises(DriverUnavailable, make_driver().connect)


def test_close_is_idempotent() -> None:
    """Allow central cleanup to release GPIO repeatedly."""

    device = FakeDhtDevice(FakeBoard.D4)
    install_fake_modules(device)
    driver = make_driver()
    driver.connect()

    driver.close()
    driver.close()
    assert_equal(device.exited, True, "device released")
    assert_equal(driver.device, None, "handle cleared")


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("connect and read", test_connect_and_read_returns_rounded_batch),
    ("timing error", test_timing_error_is_transient),
    ("incomplete sample", test_incomplete_sample_is_transient),
    ("unexpected read error", test_unexpected_read_error_loses_connection),
    ("unknown pin", test_unknown_pin_is_unavailable),
    ("missing dependencies", test_missing_dependencies_are_unavailable),
    ("idempotent close", test_close_is_idempotent),
]


def main() -> None:
    """Run all DHT11 driver contract tests."""

    print("Running DHT11 driver tests")
    print(f"Refactor dir: {REFACTOR_DIR}")
    print()

    passed = 0
    for name, test in TESTS:
        try:
            test()
        except Exception as error:
            print(f"[FAIL] {name}: {type(error).__name__}: {error}")
        else:
            print(f"[PASS] {name}")
            passed += 1

    failed = len(TESTS) - passed
    print(f"Summary: {passed}/{len(TESTS)} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
