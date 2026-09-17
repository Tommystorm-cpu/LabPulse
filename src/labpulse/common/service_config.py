"""Validate hardware driver, timing, measurement, and power-service settings."""

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny, StrictBool, model_validator

from labpulse.common.identity import slug
from labpulse.common.measurement_config import (
    MeasurementConfig,
    MeasurementDefaultsConfig,
)


class DriverConfig(BaseModel):
    """One stable driver identity and its typed, driver-owned options."""

    model_config = ConfigDict(extra="forbid")

    type: str
    options: SerializeAsAny[BaseModel]

    @model_validator(mode="before")
    @classmethod
    def validate_registered_driver(cls, value: object) -> object:
        """Resolve the driver and retain its concrete validated config model."""

        # Import after driver.py has loaded. Driver discovery imports every
        # module in hardware/drivers, and importing it at module level here
        # would create a circular import during application startup.
        from labpulse.hardware.registry import get_driver_definition

        if not isinstance(value, Mapping):
            raise ValueError("driver must be a mapping")
        raw = dict(value)
        driver_value = raw.get("type")
        if not isinstance(driver_value, str):
            raise ValueError("driver type must be a string")
        driver_type = driver_value.strip()
        if not driver_type:
            raise ValueError("driver type must not be blank")
        definition = get_driver_definition(driver_type)
        options = raw.get("options", {})
        if not isinstance(options, Mapping):
            raise ValueError("driver options must be a mapping")
        raw["type"] = driver_type
        raw["options"] = definition.validate_config(options)
        return raw


class PowerDetectionConfig(BaseModel):
    """Home Assistant timing for direct external-power detection."""

    model_config = ConfigDict(extra="forbid")

    outage_confirm_seconds: int = Field(default=3, ge=1, le=3600)
    restore_confirm_seconds: int = Field(default=5, ge=1, le=3600)


class ServiceHealthOverrideConfig(BaseModel):
    """Optional per-service overrides for whole-service alarm confirmation."""

    model_config = ConfigDict(extra="forbid")

    offline_confirm_seconds: int | None = Field(default=None, ge=1, le=3600)
    recovery_confirm_seconds: int | None = Field(default=None, ge=1, le=3600)


class ServiceConfig(BaseModel):
    """Configuration for one independently running LabPulse sensor service."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    notify_on_service_failure: StrictBool = True
    label: str
    driver: DriverConfig
    measurement_defaults: MeasurementDefaultsConfig | None = None
    measurements: dict[str, MeasurementConfig]
    reconnect_interval_seconds: float = Field(default=5.0, gt=0)
    read_interval_seconds: float | None = Field(default=None, gt=0)
    maximum_measurement_age_seconds: int = Field(default=300, ge=2, le=86400)
    service_health: ServiceHealthOverrideConfig | None = None
    power_detection: PowerDetectionConfig | None = None

    @model_validator(mode="after")
    def validate_hardware_contract(self) -> "ServiceConfig":
        """Validate driver-specific fields and the normalized UPS measurements."""

        from labpulse.hardware.driver import HardwareOutputDriver
        from labpulse.hardware.registry import get_driver_definition

        definition = get_driver_definition(self.driver.type)
        if self.measurement_defaults is not None:
            inherited = self.measurement_defaults.model_dump(exclude_unset=True)
            self.measurements = {
                measurement_id: MeasurementConfig.model_validate({
                    **inherited,
                    **measurement.model_dump(include=measurement.model_fields_set),
                })
                for measurement_id, measurement in self.measurements.items()
            }
        if issubclass(definition.driver_class, HardwareOutputDriver):
            raise ValueError("output drivers must be configured under the top-level outputs section")

        measurement_names = list(self.measurements)
        for measurement_id in measurement_names:
            if not measurement_id or slug(measurement_id) != measurement_id:
                raise ValueError("measurement IDs must use lowercase letters, numbers, and underscores")

        source_mapping: dict[str, str] = {}
        for measurement_id, measurement in self.measurements.items():
            if measurement.source is not None:
                source_mapping[measurement_id] = measurement.source
        if definition.bind_measurement_sources is None:
            configured_sources = [
                measurement_id
                for measurement_id, measurement in self.measurements.items()
                if "source" in measurement.model_fields_set
            ]
            if configured_sources:
                raise ValueError(
                    f"driver {self.driver.type} does not support measurement source names: "
                    + ", ".join(configured_sources)
                )
        else:
            missing_sources = sorted(set(measurement_names).difference(source_mapping))
            if missing_sources:
                raise ValueError(
                    f"driver {self.driver.type} requires source for measurements: "
                    + ", ".join(missing_sources)
                )
            definition.bind_measurement_sources(self.driver.options, source_mapping)

        serial_pipe_driver_id = "labpulse.serial_pipe"
        gpio_input_driver_id = "labpulse.gpio_input"
        x1200_driver_id = "labpulse.x1200"

        gpio_fields = {"gpio_line", "active_high"}
        if self.driver.type == gpio_input_driver_id:
            if not measurement_names:
                raise ValueError("labpulse.gpio_input requires at least one measurement")
            line_owners: dict[int, str] = {}
            for measurement_id, measurement in self.measurements.items():
                if measurement.gpio_line is None:
                    raise ValueError(
                        f"labpulse.gpio_input measurement {measurement_id} requires gpio_line"
                    )
                previous = line_owners.get(measurement.gpio_line)
                if previous is not None:
                    raise ValueError(
                        f"GPIO measurements {measurement_id} and {previous} both use line "
                        f"{measurement.gpio_line}"
                    )
                line_owners[measurement.gpio_line] = measurement_id
                if measurement.active_high is None:
                    self.measurements[measurement_id] = measurement.model_copy(
                        update={"active_high": True}
                    )
            if definition.bind_measurements is None:
                raise RuntimeError("labpulse.gpio_input driver does not bind measurements")
            definition.bind_measurements(self.driver.options, self.measurements)
        else:
            invalid_gpio_fields = [
                f"{measurement_id}.{field_name}"
                for measurement_id, measurement in self.measurements.items()
                for field_name in gpio_fields.intersection(measurement.model_fields_set)
            ]
            if invalid_gpio_fields:
                raise ValueError(
                    f"driver {self.driver.type} does not support GPIO measurement fields: "
                    + ", ".join(invalid_gpio_fields)
                )

        if self.driver.type == x1200_driver_id and self.power_detection is None:
            raise ValueError("labpulse.x1200 services require power_detection")

        if self.power_detection is not None:
            required = {"voltage", "battery_level", "mains_present"}
            missing = sorted(required.difference(measurement_names))
            if missing:
                raise ValueError("power_detection requires measurements named: " + ", ".join(missing))
            if self.driver.type not in {x1200_driver_id, serial_pipe_driver_id}:
                raise ValueError("power_detection requires the live X1200 driver or the fake serial UPS driver")
            if self.driver.type == x1200_driver_id and self.read_interval_seconds not in (None, 1.0):
                raise ValueError("X1200 power monitoring requires read_interval_seconds: 1")

            if any(measurement.setups is not None for measurement in self.measurements.values()):
                raise ValueError(
                    "dedicated power measurements must omit setups because power is not grouped as an experimental setup"
                )
            alarmed_values = {measurement.alarmed for measurement in self.measurements.values()}
            if len(alarmed_values) > 1:
                raise ValueError(
                    "dedicated power measurements must all use the same alarmed value because they form one composite power alarm"
                )
        elif any(measurement.setups is None for measurement in self.measurements.values()):
            raise ValueError("every ordinary measurement must declare a non-empty setups list")

        return self
