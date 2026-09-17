"""Practice driver for the maintainer tutorial; not a production sensor.

Copy to hardware/drivers/example_counter.py on a practice branch to register it.
"""

import math

from pydantic import BaseModel, ConfigDict, Field

from labpulse.hardware.driver import (
    ConnectionLost,
    ContainerRequirements,
    DriverDefinition,
    HardwareDriver,
    HardwareReadings,
)


class CounterConfig(BaseModel):
    """Starting value and increment for the practice counter."""

    model_config = ConfigDict(extra="forbid", strict=True)
    start: float = Field(default=0.0, allow_inf_nan=False)
    step: float = Field(default=1.0, gt=0, allow_inf_nan=False)


class CounterDriver(HardwareDriver):
    """Return a count on each read while connected."""

    def __init__(self, service_name: str, config: CounterConfig) -> None:
        """Keep the settings without starting the counter."""
        super().__init__(service_name)
        self.config = config
        self._value: float | None = None

    def connect(self) -> None:
        """Start or restart at the configured value."""
        self._value = self.config.start

    def read(self) -> HardwareReadings:
        """Return the current count and advance it for the next read."""
        if self._value is None:
            raise ConnectionLost("practice counter is not connected")
        value = self._value
        if not math.isfinite(value):
            raise ConnectionLost("practice counter exceeded its finite range")
        self._value += self.config.step
        return HardwareReadings({"count": value})

    def close(self) -> None:
        """Disconnect; repeated calls are harmless."""
        self._value = None


def container_requirements(
    config: CounterConfig, force_simulated: bool
) -> ContainerRequirements:
    """The counter needs no devices, mounts, or elevated privileges."""
    return ContainerRequirements()


DRIVER_DEFINITION = DriverDefinition(
    driver_id="example.counter",
    config_model=CounterConfig,
    driver_class=CounterDriver,
    container_requirements=container_requirements,
    default_read_interval_seconds=1.0,
)
