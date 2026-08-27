"""Read battery and mains-power measurements from a Geekworm X1200 UPS."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from labpulse.hardware.driver import (
    ContainerRequirements,
    ConnectionLost,
    DriverDefinition,
    DriverUnavailable,
    HardwareDriver,
    HardwareIssue,
    HardwareReadings,
)


BATTERY_VOLTAGE_REGISTER = 0x02
STATE_OF_CHARGE_REGISTER = 0x04
CommandRunner = Callable[..., Any]


# Driver configuration
class X1200Config(BaseModel):
    """I2C and GPIO configuration for the X1200."""

    model_config = ConfigDict(extra="forbid", strict=True)

    bus: int = Field(default=1, ge=0, le=255)
    address: int = 0x36
    gpio_chip: str = Field(default="/dev/gpiochip0", pattern=r"^/dev/gpiochip\d+$")
    gpio_line: int = Field(default=6, ge=0, le=53)
    mains_present_active_high: bool = True

    @field_validator("address")
    @classmethod
    def validate_address(cls, address: int) -> int:
        """Reject addresses belonging to a different I2C device."""

        if address != 0x36:
            raise ValueError("X1200 MAX17043 fuel gauge must use address 0x36")
        return address


# Battery fuel-gauge decoding
def register_word(data: list[int]) -> int:
    """Decode one big-endian two-byte MAX17043 register response."""

    if len(data) != 2 or any(not 0 <= value <= 0xFF for value in data):
        raise ValueError(f"invalid MAX17043 register response: {data!r}")
    return (data[0] << 8) | data[1]


def decode_voltage(raw: int) -> float:
    """Decode the X1200 MAX17043 VCELL register using its 1.25 mV scale."""

    return (raw >> 4) * 0.00125


def decode_state_of_charge(raw: int) -> float:
    """Decode the X1200 MAX17043 8.8 fixed-point SOC register."""

    return raw / 256.0


# Mains-power GPIO reading
class MainsGpioReader:
    """Read the X1200 mains-detection GPIO with either libgpiod CLI version."""

    def __init__(
        self,
        chip: str,
        line: int,
        active_high: bool = True,
        command_runner: CommandRunner = subprocess.run,
    ) -> None:
        """Store the configured GPIO identity and injectable process runner."""

        self.chip = chip
        self.line = line
        self.active_high = active_high
        self._command_runner = command_runner

    def read(self) -> float:
        """Return normalized mains presence as 1.0 or 0.0."""

        chip_name = Path(self.chip).name
        result = self._command_runner(["gpioget", "-c", chip_name, str(self.line)], capture_output=True, text=True, check=False, timeout=2)
        if result.returncode != 0:
            legacy_result = self._command_runner(["gpioget", chip_name, str(self.line)], capture_output=True, text=True, check=False, timeout=2)
            if legacy_result.returncode != 0:
                modern_detail = result.stderr.strip() or f"gpioget exited {result.returncode}"
                legacy_detail = legacy_result.stderr.strip() or f"gpioget exited {legacy_result.returncode}"
                raise OSError(
                    f"libgpiod 2.x read failed: {modern_detail}; "
                    f"libgpiod 1.x read failed: {legacy_detail}"
                )
            result = legacy_result

        raw = result.stdout.strip()
        value = raw.rsplit("=", 1)[-1].strip().lower()
        if value not in {"0", "1", "active", "inactive"}:
            raise ValueError(f"unexpected gpioget output: {raw!r}")

        asserted = value in {"1", "active"}
        mains_present = asserted if self.active_high else not asserted
        return 1.0 if mains_present else 0.0
# Required driver lifecycle
class X1200Driver(HardwareDriver):
    """Read X1200 battery telemetry and direct external-power state."""

    def __init__(
        self,
        service_name: str,
        config: X1200Config,
        *,
        bus_factory: Callable[[int], Any] | None = None,
        mains_gpio_reader: MainsGpioReader | None = None,
    ) -> None:
        """Store the verified X1200 identities and injectable dependencies."""

        super().__init__(service_name)
        self.bus_number = config.bus
        self.address = config.address
        self._bus_factory = bus_factory or self._default_bus_factory
        self._mains_gpio_reader = mains_gpio_reader or MainsGpioReader(
            config.gpio_chip,
            config.gpio_line,
            config.mains_present_active_high,
        )
        self._i2c_bus: Any | None = None
        self._mains_read_was_faulted = False

    @staticmethod
    def _default_bus_factory(bus_number: int) -> Any:
        """Open SMBus lazily so hardware-free tests do not require smbus2."""

        import smbus2

        return smbus2.SMBus(bus_number)

    def connect(self) -> None:
        """Open the X1200 fuel-gauge connection without writing registers."""

        try:
            self._i2c_bus = self._bus_factory(self.bus_number)
        except ImportError as error:
            self._i2c_bus = None
            raise DriverUnavailable(
                "X1200 dependency is missing. Install the LabPulse i2c extra "
                "or install smbus2 in the container."
            ) from error
        except OSError as error:
            self._i2c_bus = None
            raise DriverUnavailable(
                f"failed to open X1200 MAX17043 at 0x{self.address:02X}: {error}"
            ) from error
        self.logger.info("Connected to X1200 on I2C bus %s at 0x%02X", self.bus_number, self.address)

    def read(self) -> HardwareReadings:
        """Return battery and mains telemetry or classify a hardware fault."""

        if self._i2c_bus is None:
            raise ConnectionLost("X1200 I2C bus is not open")

        try:
            voltage = decode_voltage(self._read_fuel_gauge_register(BATTERY_VOLTAGE_REGISTER))
            raw_battery_level = self._read_fuel_gauge_register(STATE_OF_CHARGE_REGISTER)
            battery_level = min(decode_state_of_charge(raw_battery_level), 100.0)
            if not 2.0 <= voltage <= 5.0:
                raise ValueError(f"impossible X1200 battery voltage: {voltage}")
            if not 0.0 <= battery_level <= 100.0:
                raise ValueError(f"impossible X1200 state of charge: {battery_level}")
        except (OSError, ValueError) as error:
            raise ConnectionLost(f"X1200 fuel-gauge read failed: {error}") from error

        values = {
            "voltage": round(voltage, 3),
            "battery_level": round(battery_level, 1),
        }

        try:
            values["mains_present"] = self._mains_gpio_reader.read()
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            if not self._mains_read_was_faulted:
                self.logger.error("X1200 mains GPIO read failed: %s", error)
            self._mains_read_was_faulted = True
            issue = HardwareIssue(code="gpio_fault", message=f"X1200 mains GPIO read failed: {error}")
            return HardwareReadings(values, issues=(issue,))

        if self._mains_read_was_faulted:
            self.logger.info("X1200 mains GPIO measurement recovered")
        self._mains_read_was_faulted = False
        return HardwareReadings(values)

    def close(self) -> None:
        """Close the I2C handle safely and idempotently."""

        if self._i2c_bus is not None:
            try:
                self._i2c_bus.close()
            except (OSError, AttributeError) as error:
                self.logger.warning("Failed to close X1200 I2C bus: %s", error)
        self._i2c_bus = None

    def _read_fuel_gauge_register(self, register: int) -> int:
        """Read one MAX17043 register from the X1200."""

        if self._i2c_bus is None:
            raise OSError("I2C bus is not open")
        data = self._i2c_bus.read_i2c_block_data(self.address, register, 2)
        return register_word([int(value) for value in data])


# Container access and driver registration
def container_requirements(config: X1200Config, _force_simulated: bool) -> ContainerRequirements:
    """Expose only the configured I2C bus and GPIO chip."""

    return ContainerRequirements(devices=(f"/dev/i2c-{config.bus}", config.gpio_chip))


DRIVER_DEFINITION = DriverDefinition(
    driver_id="labpulse.x1200",
    config_model=X1200Config,
    driver_class=X1200Driver,
    container_requirements=container_requirements,
    default_read_interval_seconds=1.0,
)
