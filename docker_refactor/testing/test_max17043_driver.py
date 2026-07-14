"""Unit tests for MAX17043 UPS conversion and fault recovery."""

from pathlib import Path
import sys
from typing import Callable

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_hardware.drivers.max17043_ups_driver import (
    Driver,
    REG_SOC,
    REG_VCELL,
    decode_state_of_charge,
    decode_voltage,
    register_word,
)


class FakeBus:
    """Return fixed register bytes and expose simulated I2C failures."""

    def __init__(self, registers: dict[int, int] | None = None) -> None:
        self.registers = registers or {}
        self.closed = False
        self.fail_reads = False
        self.reads: list[tuple[int, int, int]] = []

    def read_i2c_block_data(self, address: int, register: int, length: int) -> list[int]:
        """Return one big-endian register response."""

        self.reads.append((address, register, length))
        if self.fail_reads:
            raise OSError("simulated I2C fault")
        value = self.registers[register]
        return [value >> 8, value & 0xFF]

    def close(self) -> None:
        """Record closure of the fake bus."""

        self.closed = True


def make_driver(bus_factory, monotonic=lambda: 0.0, address: int = 0x36) -> Driver:
    """Build a deterministic test driver."""

    return Driver(
        name="ups_monitor",
        bus_number=1,
        address=address,
        read_interval_seconds=1,
        reconnect_interval_seconds=5,
        bus_factory=bus_factory,
        monotonic=monotonic,
        sleep=lambda _: None,
    )


def healthy_registers() -> dict[int, int]:
    """Return live-like 4.13 V and 94.2% register values."""

    return {
        REG_VCELL: 3304 << 4,
        REG_SOC: round(94.2 * 256),
    }


def test_register_conversion_is_read_only() -> None:
    """Decode real telemetry without issuing configuration writes."""

    bus = FakeBus(healthy_registers())
    driver = make_driver(lambda _: bus)
    if not driver.setup():
        raise AssertionError("driver failed to open fake MAX17043")
    readings = driver.read()
    expected = {"voltage": 4.13, "battery_level": 94.2}
    if readings != expected:
        raise AssertionError(f"expected {expected!r}, got {readings!r}")
    if bus.reads != [(0x36, REG_VCELL, 2), (0x36, REG_SOC, 2)]:
        raise AssertionError(f"unexpected register reads: {bus.reads!r}")
    if decode_voltage(3304 << 4) != 4.13:
        raise AssertionError("VCELL conversion is incorrect")
    if round(decode_state_of_charge(round(94.2 * 256)), 1) != 94.2:
        raise AssertionError("SOC conversion is incorrect")
    if register_word([0x12, 0x34]) != 0x1234:
        raise AssertionError("register byte order is incorrect")


def test_rejects_wrong_address_and_invalid_responses() -> None:
    """Reject non-live addresses and malformed/impossible gauge values."""

    try:
        make_driver(lambda _: FakeBus(), address=0x42)
    except ValueError as error:
        if "0x36" not in str(error):
            raise
    else:
        raise AssertionError("non-MAX17043 address was accepted")

    try:
        register_word([0x12])
    except ValueError:
        pass
    else:
        raise AssertionError("short register response was accepted")

    bus = FakeBus({REG_VCELL: 0, REG_SOC: 0})
    driver = make_driver(lambda _: bus)
    driver.setup()
    if driver.read() is not None or driver.get_status() != "disconnected":
        raise AssertionError("impossible voltage did not become a hardware fault")


def test_fault_disconnect_and_reconnect() -> None:
    """Close a failed bus and resume readings through reconnect throttling."""

    clock = [0.0]
    failed_bus = FakeBus(healthy_registers())
    healthy_bus = FakeBus(healthy_registers())
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
    if driver.read() != {"voltage": 4.13, "battery_level": 94.2}:
        raise AssertionError("reconnected driver did not resume telemetry")


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("read-only register conversion", test_register_conversion_is_read_only),
    ("invalid address and responses", test_rejects_wrong_address_and_invalid_responses),
    ("fault disconnect and reconnect", test_fault_disconnect_and_reconnect),
]


def main() -> None:
    """Run the MAX17043 driver tests."""

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
