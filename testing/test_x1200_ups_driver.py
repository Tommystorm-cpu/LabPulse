"""Hardware-independent tests for the single Geekworm X1200 UPS driver."""

import sys
from types import SimpleNamespace
from collections.abc import Callable
from unittest.mock import patch

from labpulse.hardware.drivers import x1200
from labpulse.hardware.drivers.x1200 import (
    BATTERY_VOLTAGE_REGISTER,
    STATE_OF_CHARGE_REGISTER,
    X1200Config,
    X1200Driver,
    decode_state_of_charge,
    decode_voltage,
    read_mains_gpio,
    register_word,
)
from labpulse.hardware.driver import ConnectionLost


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
        BATTERY_VOLTAGE_REGISTER: 3304 << 4,
        STATE_OF_CHARGE_REGISTER: round(94.2 * 256),
    }


def make_driver(
    address: int = 0x36,
) -> X1200Driver:
    """Build an X1200 driver from its real production interface."""

    return X1200Driver(
        "ups_monitor",
        X1200Config(
            bus=1,
            address=address,
            gpio_chip="/dev/gpiochip0",
            gpio_line=6,
            mains_present_active_high=True,
        ),
    )


def connect_to_fake_bus(driver: X1200Driver, bus: FakeBus) -> None:
    """Patch the optional I2C package only while production opens the bus."""

    dependency = SimpleNamespace(SMBus=lambda _bus_number: bus)
    with patch.dict(sys.modules, {"smbus2": dependency}):
        driver.connect()


def test_active_high_gpio_values() -> None:
    """Normalize X1200 high/low values to mains present/absent."""

    with patch.object(x1200.subprocess, "run", return_value=command_result("1\n")):
        present = read_mains_gpio("/dev/gpiochip0", 6, True)
    with patch.object(x1200.subprocess, "run", return_value=command_result("0\n")):
        absent = read_mains_gpio("/dev/gpiochip0", 6, True)
    if present != 1.0 or absent != 0.0:
        raise AssertionError("active-high GPIO values were not normalized")


def test_configurable_polarity() -> None:
    """Support an inverted signal without changing lifecycle logic."""

    with patch.object(x1200.subprocess, "run", return_value=command_result("0\n")):
        mains_present = read_mains_gpio("/dev/gpiochip0", 6, False)
    if mains_present != 1.0:
        raise AssertionError("active-low GPIO did not normalize to mains present")


def test_libgpiod_cli_versions() -> None:
    """Support libgpiod v2 output and fall back to the v1 syntax."""

    modern_commands: list[list[str]] = []
    with patch.object(
        x1200.subprocess,
        "run",
        side_effect=sequence_runner([command_result('"6"=active\n')], modern_commands),
    ):
        modern = read_mains_gpio("/dev/gpiochip0", 6, True)
    if modern != 1.0 or modern_commands != [
        ["gpioget", "-c", "gpiochip0", "6"]
    ]:
        raise AssertionError(f"libgpiod 2.x command is incorrect: {modern_commands!r}")

    legacy_commands: list[list[str]] = []
    with patch.object(
        x1200.subprocess,
        "run",
        side_effect=sequence_runner(
            [
                command_result("", 1, "invalid option -- c"),
                command_result("0\n"),
            ],
            legacy_commands,
        ),
    ):
        legacy = read_mains_gpio("/dev/gpiochip0", 6, True)
    if legacy != 0.0 or legacy_commands != [
        ["gpioget", "-c", "gpiochip0", "6"],
        ["gpioget", "gpiochip0", "6"],
    ]:
        raise AssertionError(f"libgpiod 1.x fallback is incorrect: {legacy_commands!r}")


def test_register_conversion_is_read_only() -> None:
    """Decode X1200 battery telemetry without issuing configuration writes."""

    bus = FakeBus(healthy_registers())
    driver = make_driver()
    connect_to_fake_bus(driver, bus)
    with patch.object(x1200.subprocess, "run", return_value=command_result("1\n")):
        batch = driver.read()
    measurements = dict(batch.values)
    expected = {
        "voltage": 4.13,
        "battery_level": 94.2,
        "mains_present": 1.0,
    }
    if measurements != expected:
        raise AssertionError(f"expected {expected!r}, got {measurements!r}")
    if bus.reads != [
        (0x36, BATTERY_VOLTAGE_REGISTER, 2),
        (0x36, STATE_OF_CHARGE_REGISTER, 2),
    ]:
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
    registers[STATE_OF_CHARGE_REGISTER] = round(100.98046875 * 256)
    driver = make_driver()
    connect_to_fake_bus(driver, FakeBus(registers))
    with patch.object(x1200.subprocess, "run", return_value=command_result("1\n")):
        measurements = dict(driver.read().values)
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

    driver = make_driver()
    connect_to_fake_bus(
        driver,
        FakeBus({BATTERY_VOLTAGE_REGISTER: 0, STATE_OF_CHARGE_REGISTER: 0}),
    )
    try:
        driver.read()
    except ConnectionLost:
        pass
    else:
        raise AssertionError("impossible voltage was not classified as connection loss")


def test_i2c_fault_is_classified_for_runner_cleanup() -> None:
    """Classify a failed bus so the central runner can close and reconnect it."""

    failed_bus = FakeBus(healthy_registers())
    driver = make_driver()
    connect_to_fake_bus(driver, failed_bus)
    failed_bus.fail_reads = True
    try:
        driver.read()
    except ConnectionLost:
        pass
    else:
        raise AssertionError("I2C read fault was not classified as connection loss")
    driver.close()
    if not failed_bus.closed:
        raise AssertionError("central cleanup could not close the failed bus")


def test_gpio_fault_omits_only_mains_measurement() -> None:
    """Keep battery telemetry while allowing the mains entity to expire."""

    driver = make_driver()
    connect_to_fake_bus(driver, FakeBus(healthy_registers()))
    with patch.object(x1200.subprocess, "run", return_value=command_result("", 1, "line unavailable")):
        batch = driver.read()
    measurements = dict(batch.values)
    if measurements != {"voltage": 4.13, "battery_level": 94.2}:
        raise AssertionError(f"GPIO fault discarded battery telemetry: {measurements!r}")
    if not batch.issues or batch.issues[0].code != "gpio_fault":
        raise AssertionError("GPIO failure did not return a distinct component issue")
