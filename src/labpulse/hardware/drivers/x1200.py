"""Typed configuration and implementation for the Geekworm X1200 UPS."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from labpulse.hardware.api import (
    BaseSensorDriver,
    ComponentIssue,
    ContainerRequirements,
    ConnectionLost,
    DriverDefinition,
    DriverUnavailable,
    ReadingBatch,
)


REG_VCELL = 0x02
REG_SOC = 0x04
CommandRunner = Callable[..., Any]


class X1200Options(BaseModel):
    """Normalized I2C and GPIO configuration for the X1200."""

    model_config = ConfigDict(extra="forbid", strict=True)

    bus: int = Field(default=1, ge=0, le=255)
    address: int = Field(default=0x36, ge=0x36, le=0x36)
    gpio_chip: str = Field(default="/dev/gpiochip0", pattern=r"^/dev/gpiochip\d+$")
    gpio_line: int = Field(default=6, ge=0, le=53)
    mains_present_active_high: bool = True


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


class GpiodLineReader:
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
        result = self._run_gpioget(["gpioget", "-c", chip_name, str(self.line)])
        if result.returncode != 0:
            legacy_result = self._run_gpioget(["gpioget", chip_name, str(self.line)])
            if legacy_result.returncode != 0:
                modern_detail = (
                    result.stderr.strip() or f"gpioget exited {result.returncode}"
                )
                legacy_detail = (
                    legacy_result.stderr.strip()
                    or f"gpioget exited {legacy_result.returncode}"
                )
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

    def _run_gpioget(self, command: list[str]) -> Any:
        """Run one bounded gpioget attempt with consistent process options."""

        return self._command_runner(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )


class Driver(BaseSensorDriver):
    """Publish X1200 battery telemetry and direct external-power state."""

    def __init__(
        self,
        name: str,
        bus_number: int,
        address: int,
        gpio_chip: str,
        gpio_line: int,
        mains_present_active_high: bool,
        bus_factory: Callable[[int], Any] | None = None,
        gpio_reader: GpiodLineReader | None = None,
    ) -> None:
        """Store the verified X1200 identities and injectable dependencies."""

        super().__init__(name)
        if address != 0x36:
            raise ValueError("X1200 MAX17043 fuel gauge must use address 0x36")
        self.bus_number = bus_number
        self.address = address
        self._bus_factory = bus_factory or self._default_bus_factory
        self.gpio_reader = gpio_reader or GpiodLineReader(
            gpio_chip,
            gpio_line,
            mains_present_active_high,
        )
        self.bus: Any | None = None
        self._gpio_faulted = False

    @staticmethod
    def _default_bus_factory(bus_number: int) -> Any:
        """Open SMBus lazily so hardware-free tests do not require smbus2."""

        import smbus2

        return smbus2.SMBus(bus_number)

    def connect(self) -> None:
        """Open the X1200 fuel-gauge connection without writing registers."""

        try:
            self.bus = self._bus_factory(self.bus_number)
        except (OSError, IOError, ImportError) as error:
            self.bus = None
            raise DriverUnavailable(
                f"failed to open X1200 MAX17043 at 0x{self.address:02X}: {error}"
            ) from error
        self.logger.info(
            "Connected to X1200 on I2C bus %s at 0x%02X",
            self.bus_number,
            self.address,
        )

    def read(self) -> ReadingBatch:
        """Return battery and mains telemetry or classify a hardware fault."""

        if self.bus is None:
            raise ConnectionLost("X1200 I2C bus is not open")

        try:
            voltage = decode_voltage(self._read_register(REG_VCELL))
            battery_level = min(
                decode_state_of_charge(self._read_register(REG_SOC)),
                100.0,
            )
            self._validate_measurements(voltage, battery_level)
        except (OSError, IOError, ValueError) as error:
            raise ConnectionLost(f"X1200 fuel-gauge read failed: {error}") from error

        measurements = {
            "voltage": round(voltage, 3),
            "battery_level": round(battery_level, 1),
        }

        try:
            measurements["mains_present"] = self.gpio_reader.read()
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            if not self._gpio_faulted:
                self.logger.error("X1200 mains GPIO read failed: %s", error)
            self._gpio_faulted = True
            return ReadingBatch(
                measurements,
                issues=(
                    ComponentIssue(
                        code="gpio_fault",
                        message=f"X1200 mains GPIO read failed: {error}",
                    ),
                ),
            )

        if self._gpio_faulted:
            self.logger.info("X1200 mains GPIO measurement recovered")
        self._gpio_faulted = False
        return ReadingBatch(measurements)

    def close(self) -> None:
        """Close the I2C handle safely and idempotently."""

        if self.bus is not None:
            try:
                self.bus.close()
            except (OSError, IOError, AttributeError) as error:
                self.logger.warning("Failed to close X1200 I2C bus: %s", error)
        self.bus = None

    def _read_register(self, register: int) -> int:
        """Read one MAX17043 register from the X1200."""

        if self.bus is None:
            raise OSError("I2C bus is not open")
        data = self.bus.read_i2c_block_data(self.address, register, 2)
        return register_word([int(value) for value in data])

    @staticmethod
    def _validate_measurements(voltage: float, battery_level: float) -> None:
        """Reject values outside the physical cell and fuel-gauge range."""

        if not 2.0 <= voltage <= 5.0:
            raise ValueError(f"impossible X1200 battery voltage: {voltage}")
        if not 0.0 <= battery_level <= 100.0:
            raise ValueError(f"impossible X1200 state of charge: {battery_level}")


def build_driver(
    service_name: str,
    raw_options: BaseModel,
) -> BaseSensorDriver:
    """Construct one X1200 driver from registry-validated options."""

    if not isinstance(raw_options, X1200Options):
        raise TypeError(
            "X1200 driver expected X1200Options, "
            f"got {type(raw_options).__name__}"
        )
    return Driver(
        name=service_name,
        bus_number=raw_options.bus,
        address=raw_options.address,
        gpio_chip=raw_options.gpio_chip,
        gpio_line=raw_options.gpio_line,
        mains_present_active_high=raw_options.mains_present_active_high,
    )


def resources(
    raw_options: BaseModel,
    _force_simulated: bool,
) -> ContainerRequirements:
    """Expose only the configured I2C bus and GPIO chip."""

    if not isinstance(raw_options, X1200Options):
        raise TypeError("X1200 resources require X1200Options")
    return ContainerRequirements(
        devices=(
            f"/dev/i2c-{raw_options.bus}",
            raw_options.gpio_chip,
        )
    )


DRIVER = DriverDefinition(
    driver_id="labpulse.x1200",
    options_model=X1200Options,
    build=build_driver,
    resources=resources,
    default_read_interval_seconds=1.0,
)
