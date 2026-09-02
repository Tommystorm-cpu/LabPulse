"""Read one generic Raspberry Pi GPIO input as a numeric measurement."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from pydantic import BaseModel, ConfigDict, Field

from labpulse.hardware.driver import (
    ConnectionLost,
    ContainerRequirements,
    DriverDefinition,
    DriverUnavailable,
    HardwareDriver,
    HardwareReadings,
)
from labpulse.hardware.drivers._gpio import read_gpio


class GpioInputConfig(BaseModel):
    """Hardware identity and polarity for one digital GPIO input."""

    model_config = ConfigDict(extra="forbid", strict=True)

    gpio_chip: str = Field(default="/dev/gpiochip0", pattern=r"^/dev/gpiochip\d+$")
    gpio_line: int = Field(ge=0, le=53)
    active_high: bool = True


class GpioInputDriver(HardwareDriver):
    """Publish a GPIO line's logical low or high state as 0.0 or 1.0."""

    def __init__(self, service_name: str, config: GpioInputConfig) -> None:
        """Store the validated GPIO line identity and polarity."""

        super().__init__(service_name)
        self.gpio_chip = config.gpio_chip
        self.gpio_line = config.gpio_line
        self.active_high = config.active_high
        self._connected = False

    def connect(self) -> None:
        """Check that the GPIO device and libgpiod reader are available."""

        if shutil.which("gpioget") is None:
            raise DriverUnavailable("GPIO dependency is missing: gpioget is not installed")
        if not Path(self.gpio_chip).exists():
            raise DriverUnavailable(f"GPIO chip is unavailable: {self.gpio_chip}")
        self._connected = True
        self.logger.info("Connected to GPIO input %s line %s", self.gpio_chip, self.gpio_line)

    def read(self) -> HardwareReadings:
        """Return the configured logical GPIO state under the fixed key ``state``."""

        if not self._connected:
            raise ConnectionLost("GPIO input is not connected")
        try:
            state = read_gpio(self.gpio_chip, self.gpio_line, self.active_high)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            raise ConnectionLost(f"GPIO input read failed: {error}") from error
        return HardwareReadings({"state": state})

    def close(self) -> None:
        """Clear the connection state; each GPIO read is already self-contained."""

        self._connected = False


def container_requirements(config: GpioInputConfig, _force_simulated: bool) -> ContainerRequirements:
    """Expose only the configured GPIO chip to this service container."""

    return ContainerRequirements(devices=(config.gpio_chip,))


DRIVER_DEFINITION = DriverDefinition(
    driver_id="labpulse.gpio_input",
    config_model=GpioInputConfig,
    driver_class=GpioInputDriver,
    container_requirements=container_requirements,
    default_read_interval_seconds=1.0,
)
