"""Self-building Home Assistant render model for one configured measurement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from labpulse_common.config import MeasurementConfig
from labpulse_common.identity import entity_id, slug, stable_id


EntityMap = dict[str, str]
JsonDict = dict[str, Any]

THRESHOLD_RANGES: dict[str, JsonDict] = {
    "temp": {"unit": "\u00b0C", "range_min": -20, "range_max": 80, "step": 0.1},
    "hum": {"unit": "%", "range_min": 0, "range_max": 100, "step": 1},
    "flow": {"unit": "L/min", "range_min": 0, "range_max": 999, "step": 0.1},
    "pressure": {"unit": "bar", "range_min": 0, "range_max": 999, "step": 0.1},
    "generic": {"unit": "", "range_min": 0, "range_max": 999, "step": 1},
}


@dataclass(frozen=True)
class MqttEntity:
    """Deterministic MQTT discovery identity used by generated YAML."""

    unique_id: str
    entity_id: str


@dataclass(frozen=True)
class ThresholdModel:
    """Home Assistant threshold-editor bounds for one measurement."""

    unit: str
    range_min: float | int
    range_max: float | int
    step: float | int

    @classmethod
    def from_config(
        cls: type[ThresholdModel], config: MeasurementConfig
    ) -> ThresholdModel:
        """Infer editor bounds from the measurement name and configured unit."""

        name = slug(config.name)
        kind = next(
            (key for key in ("temp", "hum", "flow") if key in name),
            "pressure" if "press" in name else "generic",
        )
        values = THRESHOLD_RANGES[kind]
        return cls(
            unit=config.unit or str(values["unit"]),
            range_min=values["range_min"],
            range_max=values["range_max"],
            step=values["step"],
        )


@dataclass(frozen=True)
class MeasurementModel:
    """Complete template data for one configured Home Assistant measurement."""

    ENTITY_SPECS: ClassVar[dict[str, tuple[str, str]]] = {
        "alarm_state": ("input_select", "alarm_state"),
        "alarm_mode": ("input_select", "alarm_mode"),
        "alarm_muted": ("input_boolean", "alarm_muted"),
        "minimum_threshold": ("input_number", "minimum_threshold"),
        "maximum_threshold": ("input_number", "maximum_threshold"),
        "recovery_deadband": ("input_number", "recovery_deadband"),
        "danger_zone": ("binary_sensor", "danger_zone"),
        "recovery_zone": ("binary_sensor", "recovery_zone"),
        "sensor_fault_zone": ("binary_sensor", "sensor_fault_zone"),
        "observed_danger_percent": ("sensor", "observed_danger_percent"),
        "required_danger_percent": ("input_number", "required_danger_percent"),
        "observation_window_seconds": ("input_number", "observation_window_seconds"),
        "required_recovery_seconds": ("input_number", "required_recovery_seconds"),
        "alarm_controls_expanded": ("input_boolean", "alarm_controls_expanded"),
        "alarm_timing_initialized": ("input_boolean", "alarm_timing_initialized"),
    }
    UNIQUE_ID_NAMES: ClassVar[tuple[str, ...]] = (
        "danger_zone",
        "recovery_zone",
        "sensor_fault_zone",
        "observed_danger_percent",
    )

    service_name: str
    name: str
    label: str
    subcategory: str | None
    notification_context: str
    mqtt_entity: MqttEntity
    entities: EntityMap
    unique_ids: EntityMap
    setup_muted_entities: tuple[str, ...]
    setup_notifications_unmuted_template: str
    threshold: ThresholdModel

    @property
    def measurement_id(self) -> str:
        """Return the stable service-and-measurement identifier used in helpers."""

        return f"{slug(self.service_name)}_{self.name}"

    @classmethod
    def from_config(
        cls: type[MeasurementModel],
        service_name: str,
        config: MeasurementConfig,
        notification_context: str,
        setup_ids: tuple[str, ...],
    ) -> MeasurementModel:
        """Build one complete measurement model from validated configuration."""

        name = slug(config.name)
        entities = {
            key: entity_id(domain, service_name, name, suffix)
            for key, (domain, suffix) in cls.ENTITY_SPECS.items()
        }
        setup_mutes = tuple(
            entity_id("input_boolean", "setup", setup_id, "notifications_muted")
            for setup_id in setup_ids
        )
        checks = " and ".join(
            f"is_state('{mute}', 'off')" for mute in setup_mutes
        )
        return cls(
            service_name=service_name,
            name=name,
            label=config.display_label,
            subcategory=config.subcategory,
            notification_context=notification_context,
            mqtt_entity=MqttEntity(
                unique_id=stable_id(service_name, name),
                entity_id=entity_id("sensor", service_name, name),
            ),
            entities=entities,
            unique_ids={
                key: stable_id(service_name, name, key)
                for key in cls.UNIQUE_ID_NAMES
            },
            setup_muted_entities=setup_mutes,
            setup_notifications_unmuted_template="{{ " + (checks or "true") + " }}",
            threshold=ThresholdModel.from_config(config),
        )
