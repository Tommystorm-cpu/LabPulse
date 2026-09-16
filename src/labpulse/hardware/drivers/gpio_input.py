"""Read multiple Raspberry Pi GPIO inputs as named numeric measurements."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from labpulse.hardware.driver import ConnectionLost, ContainerRequirements, DriverDefinition, DriverUnavailable, HardwareDriver, HardwareReadings


@dataclass(frozen=True)
class GpioInputMeasurement:
    """One validated measurement-to-line binding."""

    gpio_line: int
    active_high: bool


class GpioInputConfig(BaseModel):
    """Hardware identity for one multi-line GPIO input service."""

    model_config = ConfigDict(extra="forbid", strict=True)
    gpio_chip: str = Field(default="/dev/gpiochip0", pattern=r"^/dev/gpiochip\d+$")
    _measurements: dict[str, GpioInputMeasurement] = PrivateAttr(default_factory=dict)

    def bind_measurements(self, measurements: Mapping[str, BaseModel]) -> None:
        """Retain measurement IDs and their validated GPIO settings."""

        self._measurements = {
            key: GpioInputMeasurement(gpio_line=value.gpio_line, active_high=value.active_high)
            for key, value in measurements.items()
        }


class GpioInputDriver(HardwareDriver):
    """Own and read every GPIO line configured for one service."""

    def __init__(self, service_name: str, config: GpioInputConfig) -> None:
        """Store the chip and measurement bindings."""

        super().__init__(service_name)
        self.gpio_chip = config.gpio_chip
        self.measurements = dict(config._measurements)
        self._gpiod: Any | None = None
        self._line_request: Any | None = None

    def connect(self) -> None:
        """Request every configured input line in one operation."""

        try:
            import gpiod
            settings = gpiod.LineSettings(direction=gpiod.line.Direction.INPUT)
            request = gpiod.request_lines(
                self.gpio_chip,
                consumer=f"LabPulse-{self.service_name}",
                config={item.gpio_line: settings for item in self.measurements.values()},
            )
        except ImportError as error:
            raise DriverUnavailable("GPIO input dependency is missing. Install gpiod 2.x in the container.") from error
        except (OSError, ValueError, AttributeError) as error:
            raise DriverUnavailable(f"failed to request GPIO inputs from {self.gpio_chip}: {error}") from error
        self._gpiod = gpiod
        self._line_request = request

    def read(self) -> HardwareReadings:
        """Read all lines and return their configured measurement IDs."""

        if self._line_request is None or self._gpiod is None:
            raise ConnectionLost("GPIO inputs are not connected")
        try:
            values = {}
            active_value = self._gpiod.line.Value.ACTIVE
            for key, item in self.measurements.items():
                electrical_active = self._line_request.get_value(item.gpio_line) == active_value
                logical_active = electrical_active if item.active_high else not electrical_active
                values[key] = 1.0 if logical_active else 0.0
        except (OSError, ValueError, AttributeError) as error:
            raise ConnectionLost(f"GPIO input read failed: {error}") from error
        return HardwareReadings(values)

    def close(self) -> None:
        """Release the shared line request safely and idempotently."""

        request = self._line_request
        self._line_request = None
        self._gpiod = None
        if request is not None:
            try:
                request.release()
            except (OSError, ValueError, AttributeError) as error:
                self.logger.warning("Could not release GPIO input lines: %s", error)


def bind_measurements(config: BaseModel, measurements: Mapping[str, BaseModel]) -> None:
    """Attach validated measurement bindings to the driver config."""

    if not isinstance(config, GpioInputConfig):
        raise TypeError("labpulse.gpio_input received the wrong config model")
    config.bind_measurements(measurements)


def container_requirements(config: GpioInputConfig, _force_simulated: bool) -> ContainerRequirements:
    """Expose only the configured GPIO chip to this service container."""

    return ContainerRequirements(devices=(config.gpio_chip,))


DRIVER_DEFINITION = DriverDefinition(
    driver_id="labpulse.gpio_input",
    config_model=GpioInputConfig,
    driver_class=GpioInputDriver,
    container_requirements=container_requirements,
    default_read_interval_seconds=1.0,
    bind_measurements=bind_measurements,
)
