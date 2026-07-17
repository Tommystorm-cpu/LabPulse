"""Hardware-independent tests for the Geekworm X1200 composite driver."""

from pathlib import Path
from types import SimpleNamespace
import sys
from typing import Callable

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_hardware.drivers.base import BaseSensorDriver
from labpulse_hardware.drivers.x1200_ups_driver import Driver, GpiodLineReader


class FakeFuelGauge(BaseSensorDriver):
    """Return fixed battery telemetry without I2C hardware."""

    def __init__(self) -> None:
        """Create an online fake gauge."""

        super().__init__("ups_monitor")

    def setup(self) -> bool:
        """Mark the fake gauge online."""

        self.connected = True
        self.status = "online"
        return True

    def read(self) -> dict[str, float]:
        """Return one valid battery sample."""

        return {"voltage": 4.1, "battery_level": 82.0}

    def disconnect(self) -> None:
        """Mark the fake gauge disconnected."""

        self.connected = False
        self.status = "disconnected"


def command_result(stdout: str = "1\n", returncode: int = 0, stderr: str = "") -> object:
    """Build a subprocess-like result for GPIO reader tests."""

    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def runner_for(result: object) -> Callable[..., object]:
    """Return a command runner that always yields one result."""

    def run(*_args: object, **_kwargs: object) -> object:
        """Return the configured fake process result."""

        return result

    return run


def make_driver(reader: GpiodLineReader) -> Driver:
    """Create a composite driver around fake hardware."""

    return Driver(
        name="ups_monitor",
        bus_number=1,
        address=0x36,
        gpio_chip="/dev/gpiochip0",
        gpio_line=6,
        mains_present_active_high=True,
        fuel_gauge=FakeFuelGauge(),
        gpio_reader=reader,
    )


def test_active_high_gpio_values() -> None:
    """Normalize X1200 high/low values to mains present/absent."""

    present = GpiodLineReader(
        "/dev/gpiochip0", 6, True, runner_for(command_result("1\n"))
    )
    absent = GpiodLineReader(
        "/dev/gpiochip0", 6, True, runner_for(command_result("0\n"))
    )
    if present.read() != 1.0 or absent.read() != 0.0:
        raise AssertionError("active-high GPIO values were not normalized")


def test_configurable_polarity() -> None:
    """Support an inverted signal without changing lifecycle logic."""

    reader = GpiodLineReader(
        "/dev/gpiochip0", 6, False, runner_for(command_result("0\n"))
    )
    if reader.read() != 1.0:
        raise AssertionError("active-low GPIO did not normalize to mains present")


def test_composite_publishes_mains_and_battery() -> None:
    """Publish direct mains state alongside unchanged battery telemetry."""

    reader = GpiodLineReader(
        "/dev/gpiochip0", 6, True, runner_for(command_result("1\n"))
    )
    driver = make_driver(reader)
    if not driver.setup():
        raise AssertionError("fake X1200 driver did not connect")
    readings = driver.read()
    expected = {"voltage": 4.1, "battery_level": 82.0, "mains_present": 1.0}
    if readings != expected or driver.status != "online":
        raise AssertionError(f"unexpected composite sample: {readings!r}, {driver.status}")


def test_gpio_fault_omits_only_mains_reading() -> None:
    """Keep battery telemetry while allowing the mains entity to expire."""

    reader = GpiodLineReader(
        "/dev/gpiochip0",
        6,
        True,
        runner_for(command_result("", 1, "line unavailable")),
    )
    driver = make_driver(reader)
    driver.setup()
    readings = driver.read()
    if readings != {"voltage": 4.1, "battery_level": 82.0}:
        raise AssertionError(f"GPIO fault discarded battery telemetry: {readings!r}")
    if driver.status != "gpio_fault":
        raise AssertionError("GPIO failure did not publish a distinct service status")


TESTS = [
    ("active-high values", test_active_high_gpio_values),
    ("configurable polarity", test_configurable_polarity),
    ("composite readings", test_composite_publishes_mains_and_battery),
    ("GPIO fault", test_gpio_fault_omits_only_mains_reading),
]


def main() -> None:
    """Run the standalone X1200 driver tests."""

    passed = 0
    for name, test in TESTS:
        try:
            test()
        except Exception as error:
            print(f"[FAIL] {name}: {type(error).__name__}: {error}")
        else:
            print(f"[PASS] {name}")
            passed += 1
    print(f"Summary: {passed}/{len(TESTS)} passed")
    if passed != len(TESTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
