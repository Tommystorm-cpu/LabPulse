"""Typed configuration and implementation for pipe-delimited serial devices."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from labpulse.hardware.api import (
    BaseSensorDriver,
    ContainerRequirements,
    ConnectionLost,
    DriverDefinition,
    DriverUnavailable,
    ReadingBatch,
)
from labpulse.hardware.serial_parser import SerialParser


class SerialPipeOptions(BaseModel):
    """Normalized configuration for the standard serial driver."""

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


# PySerial is container-only. Import it on first connection so config loading,
# Home Assistant generation, and unrelated drivers never need the dependency.
_UNLOADED = object()
serial: Any = _UNLOADED


def _load_serial() -> Any:
    """Load PySerial lazily or classify the missing dependency for the runner."""

    global serial
    if serial is _UNLOADED:
        try:
            import serial as pyserial
        except ImportError as error:
            raise DriverUnavailable(
                "Serial dependencies are missing. Install pyserial in the container."
            ) from error
        serial = pyserial
    if serial is None:
        raise DriverUnavailable(
            "Serial dependencies are missing. Install pyserial in the container."
        )
    return serial


class Driver(BaseSensorDriver):
    """
    USB serial driver for Arduino-backed LabPulse services.

    The driver reads standard pipe-delimited serial lines through SerialParser.
    """

    def __init__(
        self,
        name: str,
        port: str,
        baud_rate: int,
    ) -> None:
        """Store serial settings and create the parser for this service."""

        super().__init__(name)
        self.port = port
        self.baud_rate = baud_rate
        self.ser = None
        self.parser = SerialParser()

    def connect(self) -> None:
        """Open the configured serial port or report it as unavailable."""

        serial_module = _load_serial()
        try:
            self.ser = serial_module.Serial(self.port, self.baud_rate, timeout=2)
        except (serial_module.SerialException, OSError) as error:
            self.ser = None
            raise DriverUnavailable(
                f"failed to open {self.port}: {error}"
            ) from error
        self.logger.info("Connected to %s at %s baud", self.port, self.baud_rate)

    def read(self) -> ReadingBatch | None:
        """Read and parse one standard pipe-delimited serial line."""

        if self.ser is None:
            raise ConnectionLost(f"serial port is not open: {self.port}")

        serial_module = _load_serial()
        try:
            line = self.ser.readline().decode('utf-8').strip()
        except (
            serial_module.SerialException,
            OSError,
            UnicodeDecodeError,
        ) as error:
            raise ConnectionLost(
                f"serial read failed on {self.port}: {error}"
            ) from error

        if not line:
            return None
        measurements = self.parser.parse(line)
        return ReadingBatch(measurements) if measurements else None

    def close(self) -> None:
        """Close the serial handle safely and idempotently."""

        if self.ser is not None and self.ser.is_open:
            serial_module = _load_serial()
            try:
                self.ser.close()
            except (serial_module.SerialException, OSError) as error:
                self.logger.warning(
                    "Failed to close serial port %s: %s",
                    self.port,
                    error,
                )
        self.ser = None


def build_driver(
    service_name: str,
    raw_options: BaseModel,
) -> BaseSensorDriver:
    """Construct one serial driver from registry-validated options."""

    if not isinstance(raw_options, SerialPipeOptions):
        raise TypeError(
            "serial driver expected SerialPipeOptions, "
            f"got {type(raw_options).__name__}"
        )
    return Driver(
        name=service_name,
        port=raw_options.port,
        baud_rate=raw_options.baud_rate,
    )


def resources(
    raw_options: BaseModel,
    force_simulated: bool,
) -> ContainerRequirements:
    """Return fake-PTY mounts or the established real serial access."""

    if not isinstance(raw_options, SerialPipeOptions):
        raise TypeError("serial resources require SerialPipeOptions")
    if force_simulated or raw_options.port.startswith("/tmp/labpulse-fake-serial"):
        return ContainerRequirements(
            mounts=(
                "/tmp/labpulse-fake-serial:/tmp/labpulse-fake-serial",
                "/dev/pts:/dev/pts",
            )
        )
    return ContainerRequirements(mounts=("/dev:/dev",), privileged=True)


DRIVER = DriverDefinition(
    driver_id="labpulse.serial_pipe",
    options_model=SerialPipeOptions,
    build=build_driver,
    resources=resources,
    default_read_interval_seconds=0.0,
)
