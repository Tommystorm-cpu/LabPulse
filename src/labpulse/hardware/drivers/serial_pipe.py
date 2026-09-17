"""Read standard pipe-delimited measurements from a serial device."""

import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from labpulse.hardware.driver import (
    ContainerRequirements,
    ConnectionLost,
    DriverDefinition,
    DriverUnavailable,
    HardwareDriver,
    HardwareReadings,
)


# Values accepted under driver.options in config.yaml.
class SerialPipeConfig(BaseModel):
    """Configuration for a standard LabPulse serial device."""

    model_config = ConfigDict(extra="forbid", strict=True)

    port: str
    baud_rate: int = Field(default=9600, ge=1)

    @field_validator("port")
    @classmethod
    def validate_port(cls, port: str) -> str:
        """Reject blank serial device paths."""

        normalized = port.strip()
        if not normalized:
            raise ValueError("port must not be blank")
        return normalized


# Arduino samples use "name: value | name: value" on one serial line.
def parse_serial_line(line: str) -> dict[str, float] | None:
    """Return finite measurements from one pipe-delimited line."""

    measurements: dict[str, float] = {}
    for part in line.strip().split("|"):
        # One malformed field must not discard valid fields from the same line.
        if ":" not in part:
            continue

        label, raw_value = part.split(":", 1)
        measurement_name = label.strip().lower()
        if not measurement_name:
            continue

        try:
            value = float(raw_value.strip())
        except ValueError:
            continue

        if math.isfinite(value):
            measurements[measurement_name] = value

    return measurements or None


# The runner calls this connect/read/close lifecycle for the selected service.
class SerialPipeDriver(HardwareDriver):
    """Read Arduino measurements using the standard LabPulse serial format."""

    def __init__(self, service_name: str, config: SerialPipeConfig) -> None:
        """Store the serial settings without opening the port."""

        super().__init__(service_name)
        self.port = config.port
        self.baud_rate = config.baud_rate
        self._serial_library: Any | None = None
        self._serial_connection: Any | None = None

    def connect(self) -> None:
        """Open the configured serial port or report it as unavailable."""

        # PySerial is optional outside serial workers, so import it only when
        # this driver is selected and opening its configured port.
        try:
            import serial
        except ImportError as error:
            raise DriverUnavailable(
                "Serial dependencies are missing. Install the LabPulse serial extra "
                "or install pyserial in the container."
            ) from error
        try:
            self._serial_connection = serial.Serial(self.port, self.baud_rate, timeout=2)
        except (serial.SerialException, OSError) as error:
            self._serial_connection = None
            raise DriverUnavailable(f"failed to open {self.port}: {error}") from error
        self._serial_library = serial
        self.logger.info("Connected to %s at %s baud", self.port, self.baud_rate)

    def read(self) -> HardwareReadings | None:
        """Read and parse one standard pipe-delimited serial line."""

        if self._serial_connection is None or self._serial_library is None:
            raise ConnectionLost(f"serial port is not open: {self.port}")

        try:
            line = self._serial_connection.readline().decode("utf-8").strip()
        except (self._serial_library.SerialException, OSError, UnicodeDecodeError) as error:
            raise ConnectionLost(f"serial read failed on {self.port}: {error}") from error

        if not line:
            return None
        measurements = parse_serial_line(line)
        return HardwareReadings(measurements) if measurements else None

    def close(self) -> None:
        """Close the serial handle safely and idempotently."""

        if self._serial_connection is not None and self._serial_connection.is_open:
            try:
                self._serial_connection.close()
            except (self._serial_library.SerialException, OSError) as error:
                self.logger.warning("Failed to close serial port %s: %s", self.port, error)
        self._serial_connection = None
        self._serial_library = None


# This becomes the serial-device access granted to the service in Docker Compose.
def container_requirements(config: SerialPipeConfig, force_simulated: bool) -> ContainerRequirements:
    """Return fake-PTY mounts or the established real serial access."""

    if force_simulated or config.port.startswith("/tmp/labpulse-fake-serial"):
        return ContainerRequirements(
            mounts=(
                "/tmp/labpulse-fake-serial:/tmp/labpulse-fake-serial",
                "/dev/pts:/dev/pts",
            )
        )
    return ContainerRequirements(mounts=("/dev:/dev",), privileged=True)


DRIVER_DEFINITION = DriverDefinition(
    driver_id="labpulse.serial_pipe",
    config_model=SerialPipeConfig,
    driver_class=SerialPipeDriver,
    container_requirements=container_requirements,
    default_read_interval_seconds=0.0,
)
