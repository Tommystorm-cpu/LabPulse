"""Hardware-free tests for the standard pipe-delimited serial driver."""

from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Callable


sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR / "src"))

from labpulse.hardware.drivers import serial_pipe
from labpulse.hardware.api import ConnectionLost, DriverUnavailable
from labpulse.hardware.drivers.serial_pipe import Driver


class FakeSerialPort:
    """In-memory serial port used instead of USB hardware."""

    def __init__(
        self,
        line: bytes = b"pressure: 1.23\n",
        read_error: Exception | None = None,
    ) -> None:
        """Configure one line or one simulated read failure."""

        self.line = line
        self.read_error = read_error
        self.is_open = True
        self.closed = False

    def readline(self) -> bytes:
        """Return the configured line or raise its error."""

        if self.read_error:
            raise self.read_error
        return self.line

    def close(self) -> None:
        """Record closure of the fake port."""

        self.is_open = False
        self.closed = True


class FakeSerialException(Exception):
    """Stand-in for pyserial's platform-specific exception."""


def make_driver() -> Driver:
    """Build one serial driver with the standard fake path."""

    return Driver(
        name="pressure_monitor",
        port="/tmp/labpulse-fake-serial/pressure",
        baud_rate=9600,
    )


def install_fake_serial(factory: Callable[..., FakeSerialPort]) -> None:
    """Patch pyserial construction without touching physical devices."""

    serial_pipe.serial = SimpleNamespace(
        Serial=factory,
        SerialException=FakeSerialException,
    )


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


def test_connect_and_read_batch() -> None:
    """Open the port and return normalized readings in a ReadingBatch."""

    install_fake_serial(lambda *args, **kwargs: FakeSerialPort())
    driver = make_driver()

    driver.connect()
    batch = driver.read()
    assert_equal(
        dict(batch.measurements) if batch else None,
        {"pressure": 1.23},
        "measurements",
    )


def test_connect_failure_is_classified() -> None:
    """Translate an unavailable serial path into DriverUnavailable."""

    def factory(*_args: Any, **_kwargs: Any) -> FakeSerialPort:
        """Simulate an OS-level open failure."""

        raise OSError("port missing")

    install_fake_serial(factory)
    driver = make_driver()

    assert_raises(DriverUnavailable, driver.connect)
    assert_equal(driver.ser, None, "serial handle")


def test_read_requires_connection() -> None:
    """Classify a read without an open handle as connection loss."""

    assert_raises(ConnectionLost, make_driver().read)


def test_blank_and_invalid_lines_are_not_batches() -> None:
    """Return None when no valid serial measurement is available."""

    ports = iter(
        (
            FakeSerialPort(line=b"\n"),
            FakeSerialPort(line=b"not a measurement\n"),
        )
    )
    install_fake_serial(lambda *args, **kwargs: next(ports))

    blank = make_driver()
    blank.connect()
    assert_equal(blank.read(), None, "blank line")

    invalid = make_driver()
    invalid.connect()
    assert_equal(invalid.read(), None, "invalid line")


def test_read_failure_is_classified_for_runner_cleanup() -> None:
    """Translate a disappearing USB device into ConnectionLost."""

    port = FakeSerialPort(read_error=OSError("device disappeared"))
    install_fake_serial(lambda *args, **kwargs: port)
    driver = make_driver()
    driver.connect()

    assert_raises(ConnectionLost, driver.read)
    driver.close()
    assert_equal(port.closed, True, "port closed")
    assert_equal(driver.ser, None, "handle cleared")


def test_close_is_idempotent() -> None:
    """Allow central cleanup to close the driver repeatedly."""

    port = FakeSerialPort()
    install_fake_serial(lambda *args, **kwargs: port)
    driver = make_driver()
    driver.connect()

    driver.close()
    driver.close()
    assert_equal(port.closed, True, "closed")


TESTS = [
    ("connect and read batch", test_connect_and_read_batch),
    ("connect failure classification", test_connect_failure_is_classified),
    ("read requires connection", test_read_requires_connection),
    ("blank and invalid lines", test_blank_and_invalid_lines_are_not_batches),
    ("read failure classification", test_read_failure_is_classified_for_runner_cleanup),
    ("idempotent close", test_close_is_idempotent),
]


def main() -> None:
    """Run all serial-driver contract tests."""

    print("Running serial driver tests")
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
