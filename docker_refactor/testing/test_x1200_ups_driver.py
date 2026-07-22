"""Hardware-independent tests for the single Geekworm X1200 UPS driver."""

from pathlib import Path
from types import SimpleNamespace
import sys
from typing import Any, Callable


REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_hardware.drivers.x1200_ups_driver import (
    Driver,
    GpiodLineReader,
    REG_SOC,
    REG_VCELL,
    decode_state_of_charge,
    decode_voltage,
    register_word,
)


class FakeBus:
    """Return fixed X1200 fuel-gauge registers and simulated I2C failures."""

    def __init__(self, registers: dict[int, int] | None = None) -> None:
        self.registers = registers or {}
        self.closed = False
        self.fail_reads = False
        self.reads: list[tuple[int, int, int]] = []

    def read_i2c_block_data(
        self,
        address: int,
        register: int,
        length: int,
    ) -> list[int]:
        """Return one big-endian register response."""

        self.reads.append((address, register, length))
        if self.fail_reads:
            raise OSError("simulated I2C fault")
        value = self.registers[register]
        return [value >> 8, value & 0xFF]

    def close(self) -> None:
        """Record closure of the fake bus."""

        self.closed = True


def command_result(
    stdout: str = "1\n",
    returncode: int = 0,
    stderr: str = "",
) -> object:
    """Build a subprocess-like result for GPIO reader tests."""

    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def runner_for(result: object) -> Callable[..., object]:
    """Return a command runner that always yields one result."""

    def run(*_args: object, **_kwargs: object) -> object:
        """Return the configured fake process result."""

        return result

    return run


def sequence_runner(
    results: list[object],
    commands: list[list[str]],
) -> Callable[..., object]:
    """Return queued results while recording each attempted command."""

    pending = list(results)

    def run(command: list[str], **_kwargs: object) -> object:
        """Record a command and return its queued fake result."""

        commands.append(command)
        return pending.pop(0)

    return run


def healthy_registers() -> dict[int, int]:
    """Return live-like 4.13 V and 94.2% X1200 register values."""

    return {
        REG_VCELL: 3304 << 4,
        REG_SOC: round(94.2 * 256),
    }


def make_driver(
    reader: GpiodLineReader | None = None,
    bus_factory: Callable[[int], Any] | None = None,
    monotonic: Callable[[], float] = lambda: 0.0,
    address: int = 0x36,
) -> Driver:
    """Build a deterministic X1200 driver around fake hardware."""

    default_bus = FakeBus(healthy_registers())
    return Driver(
        name="ups_monitor",
        bus_number=1,
        address=address,
        gpio_chip="/dev/gpiochip0",
        gpio_line=6,
        mains_present_active_high=True,
        read_interval_seconds=1,
        reconnect_interval_seconds=5,
        bus_factory=bus_factory or (lambda _: default_bus),
        monotonic=monotonic,
        sleep=lambda _: None,
        gpio_reader=reader
        or GpiodLineReader(
            "/dev/gpiochip0",
            6,
            True,
            runner_for(command_result("1\n")),
        ),
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


def test_libgpiod_cli_versions() -> None:
    """Support libgpiod v2 output and fall back to the v1 syntax."""

    modern_commands: list[list[str]] = []
    modern = GpiodLineReader(
        "/dev/gpiochip0",
        6,
        True,
        sequence_runner([command_result('"6"=active\n')], modern_commands),
    )
    if modern.read() != 1.0 or modern_commands != [
        ["gpioget", "-c", "gpiochip0", "6"]
    ]:
        raise AssertionError(f"libgpiod 2.x command is incorrect: {modern_commands!r}")

    legacy_commands: list[list[str]] = []
    legacy = GpiodLineReader(
        "/dev/gpiochip0",
        6,
        True,
        sequence_runner(
            [
                command_result("", 1, "invalid option -- c"),
                command_result("0\n"),
            ],
            legacy_commands,
        ),
    )
    if legacy.read() != 0.0 or legacy_commands != [
        ["gpioget", "-c", "gpiochip0", "6"],
        ["gpioget", "gpiochip0", "6"],
    ]:
        raise AssertionError(f"libgpiod 1.x fallback is incorrect: {legacy_commands!r}")


def test_register_conversion_is_read_only() -> None:
    """Decode X1200 battery telemetry without issuing configuration writes."""

    bus = FakeBus(healthy_registers())
    driver = make_driver(bus_factory=lambda _: bus)
    if not driver.setup():
        raise AssertionError("driver failed to open fake X1200")
    measurements = driver.read()
    expected = {
        "voltage": 4.13,
        "battery_level": 94.2,
        "mains_present": 1.0,
    }
    if measurements != expected:
        raise AssertionError(f"expected {expected!r}, got {measurements!r}")
    if bus.reads != [(0x36, REG_VCELL, 2), (0x36, REG_SOC, 2)]:
        raise AssertionError(f"unexpected register reads: {bus.reads!r}")
    if decode_voltage(3304 << 4) != 4.13:
        raise AssertionError("VCELL conversion is incorrect")
    if round(decode_state_of_charge(round(94.2 * 256)), 1) != 94.2:
        raise AssertionError("SOC conversion is incorrect")
    if register_word([0x12, 0x34]) != 0x1234:
        raise AssertionError("register byte order is incorrect")


def test_full_charge_soc_is_capped() -> None:
    """Publish an over-100% gauge estimate as full instead of a fault."""

    registers = healthy_registers()
    registers[REG_SOC] = round(100.98046875 * 256)
    driver = make_driver(bus_factory=lambda _: FakeBus(registers))
    driver.setup()
    measurements = driver.read()
    if measurements != {
        "voltage": 4.13,
        "battery_level": 100.0,
        "mains_present": 1.0,
    }:
        raise AssertionError(f"over-full SOC was not capped: {measurements!r}")


def test_rejects_invalid_gauge_configuration() -> None:
    """Reject wrong addresses and malformed or impossible register values."""

    try:
        make_driver(address=0x42)
    except ValueError as error:
        if "0x36" not in str(error):
            raise
    else:
        raise AssertionError("non-X1200 fuel-gauge address was accepted")

    try:
        register_word([0x12])
    except ValueError:
        pass
    else:
        raise AssertionError("short register response was accepted")

    driver = make_driver(bus_factory=lambda _: FakeBus({REG_VCELL: 0, REG_SOC: 0}))
    driver.setup()
    if driver.read() is not None or driver.get_status() != "disconnected":
        raise AssertionError("impossible voltage did not become a hardware fault")


def test_i2c_fault_disconnect_and_reconnect() -> None:
    """Close a failed bus and resume the complete X1200 measurement set."""

    clock = [0.0]
    failed_bus = FakeBus(healthy_registers())
    healthy_bus = FakeBus(healthy_registers())
    buses = iter((failed_bus, healthy_bus))
    driver = make_driver(
        bus_factory=lambda _: next(buses),
        monotonic=lambda: clock[0],
    )
    driver.setup()
    failed_bus.fail_reads = True
    if driver.read() is not None or driver.get_status() != "disconnected":
        raise AssertionError("I2C read fault was not exposed")
    if not failed_bus.closed:
        raise AssertionError("faulted I2C handle was not closed")
    if driver.read() is not None or driver.get_status() != "online":
        raise AssertionError("first reconnect attempt did not restore the bus")
    if driver.read() != {
        "voltage": 4.13,
        "battery_level": 94.2,
        "mains_present": 1.0,
    }:
        raise AssertionError("reconnected X1200 did not resume telemetry")


def test_gpio_fault_omits_only_mains_measurement() -> None:
    """Keep battery telemetry while allowing the mains entity to expire."""

    reader = GpiodLineReader(
        "/dev/gpiochip0",
        6,
        True,
        runner_for(command_result("", 1, "line unavailable")),
    )
    driver = make_driver(reader=reader)
    driver.setup()
    measurements = driver.read()
    if measurements != {"voltage": 4.13, "battery_level": 94.2}:
        raise AssertionError(f"GPIO fault discarded battery telemetry: {measurements!r}")
    if driver.status != "gpio_fault":
        raise AssertionError("GPIO failure did not publish a distinct service status")


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("active-high values", test_active_high_gpio_values),
    ("configurable polarity", test_configurable_polarity),
    ("libgpiod CLI versions", test_libgpiod_cli_versions),
    ("read-only register conversion", test_register_conversion_is_read_only),
    ("full-charge SOC cap", test_full_charge_soc_is_capped),
    ("invalid gauge configuration", test_rejects_invalid_gauge_configuration),
    ("I2C fault and reconnect", test_i2c_fault_disconnect_and_reconnect),
    ("GPIO fault", test_gpio_fault_omits_only_mains_measurement),
]


def main() -> None:
    """Run the complete X1200 driver tests."""

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
