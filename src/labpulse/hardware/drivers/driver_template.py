"""Copy this file to add a self-contained LabPulse hardware driver.

Rename the module, replace the example names and options, and keep the
module-level ``DRIVER`` definition. The registry discovers it automatically.
Pydantic is a host and container dependency, but optional hardware libraries
must only be imported inside ``connect()`` or a helper called from it.

This template is deliberately excluded from automatic discovery.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from labpulse.hardware.api import (
    BaseSensorDriver,
    ConnectionLost,
    ContainerRequirements,
    DriverDefinition,
    DriverUnavailable,
    ReadingBatch,
)


class ExampleOptions(BaseModel):
    """Configuration accepted below ``driver.options``."""

    model_config = ConfigDict(extra="forbid", strict=True)

    device: str = Field(min_length=1)


class Driver(BaseSensorDriver):
    """Adapt one example device to the LabPulse lifecycle contract."""

    def __init__(self, name: str, device: str) -> None:
        """Store configuration without opening hardware."""

        super().__init__(name)
        self.device_path = device
        self.device: Any | None = None

    def connect(self) -> None:
        """Import the optional library and open the hardware."""

        try:
            import example_hardware_library

            self.device = example_hardware_library.open(self.device_path)
        except (ImportError, OSError) as error:
            self.device = None
            raise DriverUnavailable(f"example device unavailable: {error}") from error

    def read(self) -> ReadingBatch:
        """Return normalized numeric measurements."""

        if self.device is None:
            raise ConnectionLost("example device is not connected")
        try:
            value = float(self.device.read())
        except OSError as error:
            raise ConnectionLost(f"example device read failed: {error}") from error
        return ReadingBatch({"example_value": value})

    def close(self) -> None:
        """Release hardware safely when called more than once."""

        if self.device is not None:
            self.device.close()
        self.device = None


def build_driver(service_name: str, raw_options: BaseModel) -> BaseSensorDriver:
    """Construct this driver from validated options."""

    if not isinstance(raw_options, ExampleOptions):
        raise TypeError("example driver expected ExampleOptions")
    return Driver(service_name, raw_options.device)


def resources(
    raw_options: BaseModel,
    _force_simulated: bool,
) -> ContainerRequirements:
    """Declare the narrowest device and mount access this driver requires."""

    if not isinstance(raw_options, ExampleOptions):
        raise TypeError("example resources require ExampleOptions")
    return ContainerRequirements(devices=(raw_options.device,))


DRIVER = DriverDefinition(
    driver_id="example.device",
    options_model=ExampleOptions,
    build=build_driver,
    resources=resources,
    default_read_interval_seconds=1.0,
)
