"""Unit tests for INA219 UPS register conversion and fault recovery."""

from pathlib import Path
import sys
from typing import Callable

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_hardware.drivers.ina219_ups_driver import (
    Driver,
    REG_BUS_VOLTAGE,
    REG_CALIBRATION,
    REG_CONFIG,
    REG_CURRENT,
    swap_word,
    twos_complement,
)


class FakeBus:
    def __init__(self, registers: dict[int, int] | None = None) -> None:
        self.registers = registers or {}
        self.writes: list[tuple[int, int, int]] = []
        self.closed = False
        self.fail_reads = False

    def write_word_data(self, address: int, register: int, value: int) -> None:
        self.writes.append((address, register, value))

    def read_word_data(self, address: int, register: int) -> int:
        if self.fail_reads:
            raise OSError("simulated I2C fault")
        return swap_word(self.registers[register])

    def close(self) -> None:
        self.closed = True


def make_driver(bus_factory, monotonic=lambda: 0.0) -> Driver:
    return Driver(
        name="ups_monitor",
        bus_number=1,
        address=0x42,
        empty_voltage=3.0,
        full_voltage=4.2,
        read_interval_seconds=1,
        reconnect_interval_seconds=5,
        calibration_register=4096,
        config_register=0x399F,
        current_lsb_ma=0.1,
        bus_factory=bus_factory,
        monotonic=monotonic,
        sleep=lambda _: None,
    )


def test_register_conversion_and_calibration() -> None:
    bus = FakeBus(
        {
            REG_BUS_VOLTAGE: 1000 << 3,  # 1000 * 4 mV = 4.000 V
            REG_CURRENT: (1 << 16) - 1200,  # -1200 * 0.1 mA
        }
    )
    driver = make_driver(lambda _: bus)
    if not driver.setup():
        raise AssertionError("driver failed to configure fake INA219")
    if bus.writes != [
        (0x42, REG_CALIBRATION, swap_word(4096)),
        (0x42, REG_CONFIG, swap_word(0x399F)),
    ]:
        raise AssertionError(f"unexpected register writes: {bus.writes!r}")
    readings = driver.read()
    expected = {"voltage": 4.0, "current": -120.0, "battery_level": 83.3}
    if readings != expected:
        raise AssertionError(f"expected {expected!r}, got {readings!r}")
    if twos_complement(0xFFFF) != -1 or twos_complement(0x7FFF) != 32767:
        raise AssertionError("signed current conversion is incorrect")


def test_percentage_clamps() -> None:
    driver = make_driver(lambda _: FakeBus())
    if driver.battery_percentage(2.5) != 0.0:
        raise AssertionError("low voltage was not clamped")
    if driver.battery_percentage(4.5) != 100.0:
        raise AssertionError("high voltage was not clamped")


def test_fault_disconnect_and_reconnect() -> None:
    clock = [0.0]
    failed_bus = FakeBus({REG_BUS_VOLTAGE: 1000 << 3, REG_CURRENT: 0})
    healthy_bus = FakeBus({REG_BUS_VOLTAGE: 1000 << 3, REG_CURRENT: 0})
    buses = iter((failed_bus, healthy_bus))
    driver = make_driver(lambda _: next(buses), monotonic=lambda: clock[0])
    if not driver.setup():
        raise AssertionError("initial setup failed")
    failed_bus.fail_reads = True
    if driver.read() is not None or driver.get_status() != "disconnected":
        raise AssertionError("I2C read fault was not exposed")
    if not failed_bus.closed:
        raise AssertionError("faulted I2C handle was not closed")
    if driver.read() is not None or driver.get_status() != "online":
        raise AssertionError("first reconnect attempt did not restore the bus")
    if driver.read() != {"voltage": 4.0, "current": 0.0, "battery_level": 83.3}:
        raise AssertionError("reconnected driver did not resume telemetry")


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("register conversion and calibration", test_register_conversion_and_calibration),
    ("percentage clamps", test_percentage_clamps),
    ("fault disconnect and reconnect", test_fault_disconnect_and_reconnect),
]


def main() -> None:
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
