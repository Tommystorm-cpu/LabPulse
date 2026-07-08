from pathlib import Path
import sys
import time
from typing import Any, Callable


REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.drivers import serial_driver
from labpulse_common.drivers.serial_driver import Driver


class FakeSerialPort:
    """In-memory serial port used to test Driver without USB hardware."""

    def __init__(self, line: bytes = b"0.123\n", read_error: Exception | None = None) -> None:
        """Create a fake serial port that either returns a line or raises."""

        self.line = line
        self.read_error = read_error
        self.is_open = True
        self.closed = False

    def readline(self) -> bytes:
        """Return one fake serial line or raise the configured error."""

        if self.read_error:
            raise self.read_error

        return self.line

    def close(self) -> None:
        """Mark the fake port as closed."""

        self.is_open = False
        self.closed = True


class FakeSerialException(Exception):
    """Fallback SerialException for environments without pyserial installed."""


def make_driver(**overrides: Any) -> Driver:
    """Build a pressure parser serial driver with optional config overrides."""

    config = {
        "port": "/tmp/labpulse-fake-serial/pressure",
        "baud_rate": 9600,
        "parser": "pressure",
        "reconnect_interval_seconds": 5.0,
    }
    config.update(overrides)
    return Driver("pressure_monitor", config)


def install_fake_serial(factory: Callable[..., FakeSerialPort]) -> None:
    """Patch serial_driver.serial so tests do not require real pyserial ports."""

    serial_driver.serial.Serial = factory
    serial_driver.serial.SerialException = FakeSerialException


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise AssertionError when two values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_setup_connects() -> None:
    """Check setup opens the serial port and marks the driver connected."""

    install_fake_serial(lambda *args, **kwargs: FakeSerialPort())
    driver = make_driver()

    assert_equal(driver.setup(), True, "setup result")
    assert_equal(driver.connected, True, "connected")
    assert_equal(driver.get_status(), "online", "status")
    assert_equal(driver.ser is not None, True, "serial handle")


def test_setup_failure_marks_disconnected() -> None:
    """Check setup handles OS-level open failures without crashing."""

    def factory(*args: Any, **kwargs: Any) -> FakeSerialPort:
        """Raise an OS error to mimic a missing USB serial device."""

        raise OSError("port missing")

    install_fake_serial(factory)
    driver = make_driver()

    assert_equal(driver.setup(), False, "setup result")
    assert_equal(driver.connected, False, "connected")
    assert_equal(driver.get_status(), "disconnected", "status")
    assert_equal(driver.ser, None, "serial handle")


def test_read_attempts_reconnect_when_disconnected() -> None:
    """Check read tries reconnecting when the driver is disconnected."""

    install_fake_serial(lambda *args, **kwargs: FakeSerialPort())
    driver = make_driver(reconnect_interval_seconds=0.01)

    first_read = driver.read()
    second_read = driver.read()

    assert_equal(first_read, None, "first read while reconnecting")
    assert_equal(second_read, {"pressure": 1.23}, "second read")
    assert_equal(driver.get_status(), "online", "status")


def test_failed_reconnect_reports_reconnecting() -> None:
    """Check periodic reconnect failures leave a visible reconnecting status."""

    def factory(*args: Any, **kwargs: Any) -> FakeSerialPort:
        """Raise an OS error to mimic a still-missing serial device."""

        raise OSError("port still missing")

    install_fake_serial(factory)
    driver = make_driver(reconnect_interval_seconds=0.01)

    assert_equal(driver.read(), None, "read result")
    assert_equal(driver.connected, False, "connected")
    assert_equal(driver.get_status(), "reconnecting", "status")


def test_reconnect_is_throttled() -> None:
    """Check reconnect attempts are skipped until the interval has passed."""

    attempts = 0

    def factory(*args: Any, **kwargs: Any) -> FakeSerialPort:
        """Count fake serial open attempts."""

        nonlocal attempts
        attempts += 1
        return FakeSerialPort()

    install_fake_serial(factory)
    driver = make_driver(reconnect_interval_seconds=60.0)
    driver.last_reconnect_attempt = time.monotonic()

    assert_equal(driver.read(), None, "read result")
    assert_equal(attempts, 0, "reconnect attempts")
    assert_equal(driver.get_status(), "disconnected", "status")


def test_read_error_marks_disconnected() -> None:
    """Check USB-style read errors close the port and mark disconnected."""

    port = FakeSerialPort(read_error=OSError("device disappeared"))
    install_fake_serial(lambda *args, **kwargs: port)
    driver = make_driver()

    assert_equal(driver.setup(), True, "setup result")
    assert_equal(driver.read(), None, "read result")
    assert_equal(driver.connected, False, "connected")
    assert_equal(driver.get_status(), "disconnected", "status")
    assert_equal(driver.ser, None, "serial handle cleared")
    assert_equal(port.closed, True, "serial port closed")


TESTS = [
    ("setup connects", test_setup_connects),
    ("setup failure marks disconnected", test_setup_failure_marks_disconnected),
    ("read attempts reconnect when disconnected", test_read_attempts_reconnect_when_disconnected),
    ("failed reconnect reports reconnecting", test_failed_reconnect_reports_reconnecting),
    ("reconnect is throttled", test_reconnect_is_throttled),
    ("read error marks disconnected", test_read_error_marks_disconnected),
]


def main() -> None:
    """Run all serial driver reconnect tests."""

    print("Running serial Driver tests")
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

    total = len(TESTS)
    failed_count = total - passed_count

    print(f"Summary: {passed_count}/{total} passed, {failed_count} failed")

    if failed_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
