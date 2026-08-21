"""Typed configuration and implementation for Sensirion SHT40 sensors."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from labpulse.hardware.api import (
    BaseSensorDriver,
    ContainerRequirements,
    ConnectionLost,
    DriverSpec,
    DriverUnavailable,
    ReadingBatch,
    TransientReadError,
)


SHT40_ADDRESS = 0x44
MEASURE_HIGH_PRECISION = 0xFD
MEASUREMENT_DELAY_SECONDS = 0.01


class Sht40Options(BaseModel):
    """Normalized I2C configuration for one SHT40 sensor."""

    model_config = ConfigDict(extra="forbid", strict=True)

    bus: int = Field(default=1, ge=0, le=255)
    address: int = SHT40_ADDRESS

    @field_validator("address")
    @classmethod
    def validate_address(cls, address: int) -> int:
        """Reject addresses belonging to a different I2C device."""

        if address != SHT40_ADDRESS:
            raise ValueError("SHT40 must use I2C address 0x44")
        return address


# Keep smbus2 optional and lazy so config generation and unrelated workers can
# discover this module on development machines without Raspberry Pi libraries.
_UNLOADED = object()
smbus2: Any = _UNLOADED


def _load_i2c_dependency() -> Any:
    """Load smbus2 only when an SHT40 worker opens its configured bus."""

    global smbus2
    if smbus2 is _UNLOADED:
        try:
            import smbus2 as smbus2_module
        except ImportError:
            smbus2 = None
        else:
            smbus2 = smbus2_module
    if smbus2 is None:
        raise DriverUnavailable(
            "SHT40 dependency is missing. Install the LabPulse i2c extra "
            "or install smbus2 in the container."
        )
    return smbus2


def crc8(data: Sequence[int]) -> int:
    """Return the SHT4x CRC-8 for one two-byte sensor word."""

    crc = 0xFF
    for value in data:
        if not 0 <= value <= 0xFF:
            raise ValueError(f"invalid SHT40 response byte: {value!r}")
        crc ^= value
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x31) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def decode_measurement(data: Sequence[int]) -> tuple[float, float]:
    """Validate and convert one six-byte SHT40 temperature/humidity response."""

    if len(data) != 6:
        raise ValueError(f"invalid SHT40 response length: {len(data)}")
    values = [int(value) for value in data]
    if any(not 0 <= value <= 0xFF for value in values):
        raise ValueError(f"invalid SHT40 response bytes: {values!r}")
    if crc8(values[0:2]) != values[2]:
        raise ValueError("SHT40 temperature CRC mismatch")
    if crc8(values[3:5]) != values[5]:
        raise ValueError("SHT40 humidity CRC mismatch")

    raw_temperature = (values[0] << 8) | values[1]
    raw_humidity = (values[3] << 8) | values[4]
    temperature = -45.0 + 175.0 * raw_temperature / 65535.0
    humidity = -6.0 + 125.0 * raw_humidity / 65535.0
    return temperature, min(max(humidity, 0.0), 100.0)


class Driver(BaseSensorDriver):
    """Read temperature and relative humidity from one SHT40 over I2C."""

    def __init__(
        self,
        name: str,
        options: Sht40Options,
        *,
        bus_factory: Callable[[int], Any] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        """Store the I2C identity and injectable hardware dependencies."""

        super().__init__(name)
        self.bus_number = options.bus
        self.address = options.address
        self._bus_factory = bus_factory or self._default_bus_factory
        self._sleep = sleeper
        self.bus: Any | None = None

    @staticmethod
    def _default_bus_factory(bus_number: int) -> Any:
        """Open SMBus lazily so hardware-free processes need no I2C library."""

        return _load_i2c_dependency().SMBus(bus_number)

    def connect(self) -> None:
        """Open the configured I2C bus or report it as unavailable."""

        try:
            self.bus = self._bus_factory(self.bus_number)
        except DriverUnavailable:
            self.bus = None
            raise
        except (OSError, IOError, ImportError) as error:
            self.bus = None
            raise DriverUnavailable(
                f"failed to open SHT40 at 0x{self.address:02X} on "
                f"I2C bus {self.bus_number}: {error}"
            ) from error

        self.logger.info(
            "Connected to SHT40 on I2C bus %s at 0x%02X",
            self.bus_number,
            self.address,
        )

    def read(self) -> ReadingBatch:
        """Request one high-precision sample and return normalized measurements."""

        if self.bus is None:
            raise ConnectionLost("SHT40 I2C bus is not open")

        dependency = _load_i2c_dependency()
        try:
            command = dependency.i2c_msg.write(
                self.address,
                [MEASURE_HIGH_PRECISION],
            )
            self.bus.i2c_rdwr(command)
            self._sleep(MEASUREMENT_DELAY_SECONDS)
            response = dependency.i2c_msg.read(self.address, 6)
            self.bus.i2c_rdwr(response)
            payload = list(response)
        except (OSError, IOError) as error:
            raise ConnectionLost(f"SHT40 I2C read failed: {error}") from error

        try:
            temperature, humidity = decode_measurement(payload)
        except (TypeError, ValueError) as error:
            raise TransientReadError(f"invalid SHT40 sample: {error}") from error

        return ReadingBatch(
            {
                "temperature": round(temperature, 2),
                "humidity": round(humidity, 2),
            }
        )

    def close(self) -> None:
        """Close the I2C handle safely and idempotently."""

        if self.bus is not None:
            try:
                self.bus.close()
            except (OSError, IOError, AttributeError) as error:
                self.logger.warning("Failed to close SHT40 I2C bus: %s", error)
        self.bus = None


def resources(
    options: Sht40Options,
    _force_simulated: bool,
) -> ContainerRequirements:
    """Expose only the configured Raspberry Pi I2C device."""

    return ContainerRequirements(devices=(f"/dev/i2c-{options.bus}",))


DRIVER = DriverSpec(
    driver_id="labpulse.sht40",
    options_model=Sht40Options,
    implementation=Driver,
    resources=resources,
    default_read_interval_seconds=2.0,
)
