"""Hold one generic Raspberry Pi GPIO output at a commanded logical state."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from labpulse.hardware.driver import (
    ConnectionLost,
    ContainerRequirements,
    DriverDefinition,
    DriverUnavailable,
    HardwareOutputDriver,
    HardwareReadings,
)


class GpioOutputConfig(BaseModel):
    """Hardware identity, polarity, and fail-safe state for one GPIO output."""

    model_config = ConfigDict(extra="forbid", strict=True)

    gpio_chip: str = Field(default="/dev/gpiochip0", pattern=r"^/dev/gpiochip\d+$")
    gpio_line: int = Field(ge=0, le=53)
    active_high: bool = True
    safe_state: bool = False


class GpioOutputDriver(HardwareOutputDriver):
    """Own a GPIO line continuously and change it without releasing the line."""

    def __init__(self, service_name: str, config: GpioOutputConfig) -> None:
        """Store the validated GPIO identity, polarity, and logical safe state."""

        super().__init__(service_name)
        self.gpio_chip = config.gpio_chip
        self.gpio_line = config.gpio_line
        self.active_high = config.active_high
        self._safe_state = config.safe_state
        self._state = config.safe_state
        self._gpiod: Any | None = None
        self._line_request: Any | None = None

    @property
    def safe_state(self) -> bool:
        """Return the configured logical state used when control is unavailable."""

        return self._safe_state

    def connect(self) -> None:
        """Request the output line and atomically initialize it to the safe state."""

        try:
            import gpiod

            safe_value = self._electrical_value(gpiod, self._safe_state)
            settings = gpiod.LineSettings(
                direction=gpiod.line.Direction.OUTPUT,
                output_value=safe_value,
            )
            line_request = gpiod.request_lines(
                self.gpio_chip,
                consumer=f"LabPulse-{self.service_name}",
                config={self.gpio_line: settings},
            )
        except ImportError as error:
            raise DriverUnavailable(
                "GPIO output dependency is missing. Install gpiod 2.x in the container."
            ) from error
        except (OSError, ValueError, AttributeError) as error:
            raise DriverUnavailable(
                f"failed to request GPIO output {self.gpio_chip} line {self.gpio_line}: {error}"
            ) from error

        self._gpiod = gpiod
        self._line_request = line_request
        self._state = self._safe_state
        self.logger.info(
            "Connected to GPIO output %s line %s in safe state %s",
            self.gpio_chip,
            self.gpio_line,
            self._safe_state,
        )

    def set_state(self, active: bool) -> None:
        """Set and verify one logical output state while retaining line ownership."""

        if not isinstance(active, bool):
            raise ValueError("GPIO output state must be true or false")
        if self._line_request is None or self._gpiod is None:
            raise ConnectionLost("GPIO output is not connected")
        try:
            expected = self._electrical_value(self._gpiod, active)
            self._line_request.set_value(self.gpio_line, expected)
            actual = self._line_request.get_value(self.gpio_line)
        except (OSError, ValueError, AttributeError) as error:
            raise ConnectionLost(f"GPIO output write failed: {error}") from error
        if actual != expected:
            raise ConnectionLost(
                f"GPIO output verification failed: wrote {expected!r}, read {actual!r}"
            )
        self._state = active

    def read(self) -> HardwareReadings:
        """Return the GPIO latch state as an ordinary numeric diagnostic reading."""

        if self._line_request is None or self._gpiod is None:
            raise ConnectionLost("GPIO output is not connected")
        try:
            electrical_state = self._line_request.get_value(self.gpio_line)
        except (OSError, ValueError, AttributeError) as error:
            raise ConnectionLost(f"GPIO output readback failed: {error}") from error
        active_value = self._gpiod.line.Value.ACTIVE
        electrical_active = electrical_state == active_value
        self._state = electrical_active if self.active_high else not electrical_active
        return HardwareReadings({"state": 1.0 if self._state else 0.0})

    def close(self) -> None:
        """Apply the safe state and release the GPIO line safely and idempotently."""

        line_request = self._line_request
        gpiod_module = self._gpiod
        self._line_request = None
        self._gpiod = None
        if line_request is not None and gpiod_module is not None:
            try:
                line_request.set_value(
                    self.gpio_line,
                    self._electrical_value(gpiod_module, self._safe_state),
                )
            except (OSError, ValueError, AttributeError) as error:
                self.logger.error("Could not apply GPIO safe state during shutdown: %s", error)
            try:
                line_request.release()
            except (OSError, ValueError, AttributeError) as error:
                self.logger.warning("Could not release GPIO output line: %s", error)
        self._state = self._safe_state

    def _electrical_value(self, gpiod_module: Any, logical_state: bool) -> Any:
        """Translate the logical state through the configured output polarity."""

        electrical_active = logical_state if self.active_high else not logical_state
        return (
            gpiod_module.line.Value.ACTIVE
            if electrical_active
            else gpiod_module.line.Value.INACTIVE
        )


def container_requirements(config: GpioOutputConfig, _force_simulated: bool) -> ContainerRequirements:
    """Expose only the configured GPIO chip to this output worker."""

    return ContainerRequirements(devices=(config.gpio_chip,))


DRIVER_DEFINITION = DriverDefinition(
    driver_id="labpulse.gpio_output",
    config_model=GpioOutputConfig,
    driver_class=GpioOutputDriver,
    container_requirements=container_requirements,
    default_read_interval_seconds=0.0,
)
