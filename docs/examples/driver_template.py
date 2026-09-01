"""Copy this file to add a self-contained LabPulse hardware driver.

Rename the module, replace the example names, and keep the module-level
``DRIVER_DEFINITION``. The registry discovers it automatically. Optional
hardware libraries must only be imported when the driver connects.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from labpulse.hardware.driver import (
    ConnectionLost,
    ContainerRequirements,
    DriverDefinition,
    DriverUnavailable,
    HardwareDriver,
    HardwareReadings,
)


class ExampleConfig(BaseModel):
    """Configuration accepted below ``driver.options`` in config.yaml."""

    model_config = ConfigDict(extra="forbid", strict=True)
    device: str = Field(min_length=1)


class ExampleDriver(HardwareDriver):
    """Adapt one example device to the LabPulse lifecycle contract."""

    def __init__(self, service_name: str, config: ExampleConfig) -> None:
        super().__init__(service_name)
        self.device_path = config.device
        self._device: Any | None = None

    def connect(self) -> None:
        """Import the optional library and open the hardware."""

        try:
            import example_hardware_library

            self._device = example_hardware_library.open(self.device_path)
        except (ImportError, OSError) as error:
            self._device = None
            raise DriverUnavailable(f"example device unavailable: {error}") from error

    def read(self) -> HardwareReadings:
        """Return normalized numeric measurements."""

        if self._device is None:
            raise ConnectionLost("example device is not connected")
        try:
            value = float(self._device.read())
        except OSError as error:
            raise ConnectionLost(f"example device read failed: {error}") from error
        return HardwareReadings({"example_value": value})

    def close(self) -> None:
        """Release hardware safely when called more than once."""

        if self._device is not None:
            self._device.close()
        self._device = None


def container_requirements(config: ExampleConfig, _force_simulated: bool) -> ContainerRequirements:
    """Declare the narrowest device and mount access this driver requires."""

    return ContainerRequirements(devices=(config.device,))


DRIVER_DEFINITION = DriverDefinition(
    driver_id="example.device",
    config_model=ExampleConfig,
    driver_class=ExampleDriver,
    container_requirements=container_requirements,
    default_read_interval_seconds=1.0,
)
