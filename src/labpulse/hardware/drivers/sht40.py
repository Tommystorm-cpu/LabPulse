"""Read temperature and humidity from a Sensirion SHT40 sensor."""

from __future__ import annotations

from collections.abc import Sequence
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from labpulse.hardware.driver import (
    ContainerRequirements,
    ConnectionLost,
    DriverDefinition,
    DriverUnavailable,
    HardwareDriver,
    HardwareReadings,
    TransientReadError,
)


SHT40_ADDRESS = 0x44
MEASURE_HIGH_PRECISION = 0xFD
MEASUREMENT_DELAY_SECONDS = 0.01


# Values accepted under driver.options in config.yaml.
class Sht40Config(BaseModel):
    """I2C configuration for one SHT40 sensor."""

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


# The sensor appends a checksum byte to each two-byte measurement. Recalculate
# it here so a damaged I2C response is rejected rather than treated as a value.
def crc8(data: Sequence[int]) -> int:
    """Return the SHT4x CRC-8 for one two-byte sensor word."""

    crc = 0xFF
    for value in data:
        if not 0 <= value <= 0xFF:
            raise ValueError(f"invalid SHT40 response byte: {value!r}")
        crc ^= value
        # Process the byte one bit at a time. When the top bit would be shifted
        # out, XOR with the SHT40's 0x31 checksum polynomial.
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


# The runner calls this connect/read/close lifecycle for the selected service.
class Sht40Driver(HardwareDriver):
    """Read temperature and relative humidity from one SHT40 over I2C."""

    def __init__(self, service_name: str, config: Sht40Config) -> None:
        """Store the configured I2C identity."""

        super().__init__(service_name)
        self.bus_number = config.bus
        self.address = config.address
        self._smbus2: Any | None = None
        self._i2c_bus: Any | None = None

    def connect(self) -> None:
        """Open the configured I2C bus or report it as unavailable."""

        try:
            import smbus2
        except ImportError as error:
            self._i2c_bus = None
            raise DriverUnavailable(
                "SHT40 dependency is missing. Install the LabPulse i2c extra "
                "or install smbus2 in the container."
            ) from error
        try:
            self._i2c_bus = smbus2.SMBus(self.bus_number)
        except OSError as error:
            self._i2c_bus = None
            raise DriverUnavailable(
                f"failed to open SHT40 at 0x{self.address:02X} on "
                f"I2C bus {self.bus_number}: {error}"
            ) from error
        self._smbus2 = smbus2

        self.logger.info("Connected to SHT40 on I2C bus %s at 0x%02X", self.bus_number, self.address)

    def read(self) -> HardwareReadings:
        """Request one high-precision sample and return normalized measurements."""

        if self._i2c_bus is None or self._smbus2 is None:
            raise ConnectionLost("SHT40 I2C bus is not open")

        try:
            command = self._smbus2.i2c_msg.write(self.address, [MEASURE_HIGH_PRECISION])
            self._i2c_bus.i2c_rdwr(command)
            time.sleep(MEASUREMENT_DELAY_SECONDS)
            response = self._smbus2.i2c_msg.read(self.address, 6)
            self._i2c_bus.i2c_rdwr(response)
            payload = list(response)
        except OSError as error:
            raise ConnectionLost(f"SHT40 I2C read failed: {error}") from error

        try:
            temperature, humidity = decode_measurement(payload)
        except (TypeError, ValueError) as error:
            raise TransientReadError(f"invalid SHT40 sample: {error}") from error

        return HardwareReadings({"temperature": round(temperature, 2), "humidity": round(humidity, 2)})

    def close(self) -> None:
        """Close the I2C handle safely and idempotently."""

        if self._i2c_bus is not None:
            try:
                self._i2c_bus.close()
            except (OSError, AttributeError) as error:
                self.logger.warning("Failed to close SHT40 I2C bus: %s", error)
        self._i2c_bus = None
        self._smbus2 = None


# This becomes the I2C-device access granted to the service in Docker Compose.
def container_requirements(config: Sht40Config, _force_simulated: bool) -> ContainerRequirements:
    """Expose only the configured Raspberry Pi I2C device."""

    return ContainerRequirements(devices=(f"/dev/i2c-{config.bus}",))


DRIVER_DEFINITION = DriverDefinition(
    driver_id="labpulse.sht40",
    config_model=Sht40Config,
    driver_class=Sht40Driver,
    container_requirements=container_requirements,
    default_read_interval_seconds=2.0,
)
