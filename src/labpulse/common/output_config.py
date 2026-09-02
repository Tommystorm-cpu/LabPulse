"""Validate independently controlled LabPulse hardware outputs."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from labpulse.common.measurement_config import validate_measurement_icon
from labpulse.common.service_config import DriverConfig


class OutputConfig(BaseModel):
    """Configuration for one MQTT-controlled physical output."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    label: str
    icon: str = "mdi:toggle-switch"
    driver: DriverConfig
    reconnect_interval_seconds: float = Field(default=5.0, gt=0, le=3600)
    maximum_active_seconds: float | None = Field(default=None, gt=0, le=86400)

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, icon: str) -> str:
        """Normalize and validate the Home Assistant switch icon."""

        validated = validate_measurement_icon(icon)
        if validated is None:  # The field itself is not optional.
            raise ValueError("output icon must not be empty")
        return validated

    @model_validator(mode="after")
    def validate_output_driver(self) -> "OutputConfig":
        """Require an output-capable driver and coherent safety timing."""

        from labpulse.hardware.driver import HardwareOutputDriver
        from labpulse.hardware.registry import get_driver_definition

        definition = get_driver_definition(self.driver.type)
        if not issubclass(definition.driver_class, HardwareOutputDriver):
            raise ValueError("outputs require an output-capable driver")
        safe_state = getattr(self.driver.options, "safe_state", None)
        if self.maximum_active_seconds is not None and safe_state is not False:
            raise ValueError("maximum_active_seconds requires driver.options.safe_state: false")
        return self
