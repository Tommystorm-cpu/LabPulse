"""Normalize LabPulse config into Home Assistant template data."""

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from labpulse_common.config import LabPulseConfig, PowerDetectionConfig, ReadingConfig
from labpulse_common.identity import entity_id, slug, stable_id
from labpulse_common.mqtt_contracts import SMS_SEND_TOPIC

from .alarm_defaults import AlarmDefaults, ReadingAlarmDefaults


JsonDict = dict[str, Any]


THRESHOLD_DEFAULTS: dict[str, JsonDict] = {
    "temp": {"unit": "\u00b0C", "min": 5, "max": 35, "deadband": 1, "range_min": -20, "range_max": 80, "step": 0.1},
    "hum": {"unit": "%", "min": 20, "max": 80, "deadband": 5, "range_min": 0, "range_max": 100, "step": 1},
    "flow": {"unit": "L/min", "min": 1, "max": 999, "deadband": 0.5, "range_min": 0, "range_max": 999, "step": 0.1},
    "pressure": {"unit": "bar", "min": 1, "max": 999, "deadband": 0.1, "range_min": 0, "range_max": 999, "step": 0.1},
    "generic": {"unit": "", "min": 0, "max": 999, "deadband": 1, "range_min": 0, "range_max": 999, "step": 1},
}


@dataclass
class ThresholdModel:
    """Default Home Assistant helper settings for one reading.

    User config describes hardware and labels only. Alarm behavior is rendered
    as Home Assistant helpers for min/max thresholds and recovery deadband.
    """

    unit: str
    minimum: float | int
    maximum: float | int
    deadband: float | int
    range_min: float | int
    range_max: float | int
    step: float | int
    version: str


@dataclass
class EntityReference:
    """A Home Assistant registry identity with a deterministic fallback ID."""

    platform: str
    unique_id: str
    default_entity_id: str
    resolved_entity_id: str | None = None
    resolution_status: Literal[
        "not_queried",
        "matched",
        "renamed",
        "missing",
        "disabled",
        "ambiguous",
    ] = "not_queried"

    @property
    def entity_id(self) -> str:
        """Return the registry ID when resolved, otherwise the stable default."""

        return self.resolved_entity_id or self.default_entity_id

@dataclass
class ReadingModel:
    """Template data for one Home Assistant reading."""

    # Basic reading identity and user-facing display information.
    name: str
    label: str
    group: str | None
    reading_id: str

    # MQTT discovery identity for the physical sensor reading. The unique ID
    # anchors Home Assistant's entity registry; the object/entity IDs are the
    # predictable names used by generated dashboards and automations.
    mqtt_entity: EntityReference

    # User-editable Home Assistant helpers that hold the expansion, alarm state, selected
    # alarm mode, mute setting, thresholds, and recovery deadband.
    alarm_controls_expanded_entity: str
    alarm_state_entity: str
    alarm_mode_entity: str
    alarm_muted_entity: str
    minimum_threshold_entity: str
    maximum_threshold_entity: str
    recovery_deadband_entity: str

    # Derived Home Assistant entities used by the alarm state machine. Zone
    # entities report current conditions; the observed percentage sensor
    # measures how much of the configured window has been in the danger zone.
    danger_zone_unique_id: str
    danger_zone_entity: str
    recovery_zone_unique_id: str
    recovery_zone_entity: str
    sensor_fault_zone_unique_id: str
    sensor_fault_zone_entity: str
    observed_danger_percent_unique_id: str
    observed_danger_percent_entity: str

    # Initial helper behavior and editable numeric limits generated for the
    # reading before users tune them through Home Assistant.
    default_alarm_mode: str
    threshold: ThresholdModel

    @property
    def mqtt_unique_id(self) -> str:
        """Return the MQTT unique ID retained for template compatibility."""

        return self.mqtt_entity.unique_id

    @property
    def expected_entity_id(self) -> str:
        """Return the effective MQTT entity ID used by generated files."""

        return self.mqtt_entity.entity_id

@dataclass
class PowerModel:
    """Dedicated UPS low-voltage lifecycle identities and timing settings."""

    source: str
    voltage: ReadingModel
    battery_level: ReadingModel
    low_voltage_threshold: float
    outage_confirm_seconds: int
    restore_confirm_seconds: int
    maximum_reading_age_seconds: int
    low_voltage_evidence_unique_id: str
    low_voltage_evidence_entity: str
    sensor_fault_unique_id: str
    sensor_fault_entity: str
    sensor_fault_confirmed_entity: str
    state_entity: str
    muted_entity: str
    outage_confirm_seconds_entity: str
    restore_confirm_seconds_entity: str
    timing_initialized_entity: str
    outage_candidate_entity: str
    recovery_candidate_entity: str
    outage_active_entity: str
    outage_candidate_started_entity: str
    outage_candidate_deadline_entity: str
    recovery_candidate_started_entity: str
    recovery_candidate_deadline_entity: str
    outage_started_entity: str
    last_outage_started_entity: str
    last_outage_duration_entity: str
    last_outage_started_sensor_unique_id: str
    last_outage_started_sensor_entity: str
    last_outage_duration_sensor_unique_id: str
    last_outage_duration_sensor_entity: str


@dataclass
class ServiceModel:
    """Template data for one enabled LabPulse service."""

    # Service identity and dashboard presentation.
    name: str
    service_id: str
    label: str
    section: str
    icon: str
    order: int

    # MQTT-discovered health sensor for the hardware service.
    status_entity: EntityReference

    # Home Assistant helpers shared by every reading in this service. They
    # control danger timing and recovery for the generated alarm state machines.
    required_danger_percent_entity: str
    observation_window_seconds_entity: str
    required_recovery_seconds_entity: str
    sensor_fault_confirm_seconds: int

    # Per-reading template models generated from the service configuration.
    readings: list[ReadingModel] = field(default_factory=list)
    power: PowerModel | None = None

    @property
    def status_unique_id(self) -> str:
        """Return the MQTT service-status unique ID."""

        return self.status_entity.unique_id

    @property
    def status_entity_id(self) -> str:
        """Return the effective MQTT service-status entity ID."""

        return self.status_entity.entity_id


@dataclass
class RenderModel:
    """All data needed to render Home Assistant templates."""

    services: list[ServiceModel]
    sms_send_topic: str = SMS_SEND_TOPIC
    global_muted_entity: str = "input_boolean.labpulse_global_notifications_muted"
    test_mode_entity: str = "input_boolean.labpulse_notification_test_mode"

    @property
    def readings(self) -> list[tuple[ServiceModel, ReadingModel]]:
        """Return all readings paired with their parent service."""

        return [
            (service, reading)
            for service in self.services
            for reading in service.readings
        ]

    @property
    def alarm_readings(self) -> list[tuple[ServiceModel, ReadingModel]]:
        """Return readings governed by the normal aggregate alarm machinery."""

        return [
            (service, reading)
            for service in self.services
            if service.power is None
            for reading in service.readings
        ]

    @property
    def registry_entities(self) -> list[tuple[str, EntityReference]]:
        """Return all MQTT registry identities with readable diagnostic labels."""

        result: list[tuple[str, EntityReference]] = []
        for service in self.services:
            result.append((f"{service.name}.status", service.status_entity))
            result.extend(
                (f"{service.name}.{reading.name}", reading.mqtt_entity)
                for reading in service.readings
            )
        return result


def reading_defaults(reading_name: str) -> JsonDict:
    """Infer default threshold settings from a reading name."""

    name = slug(reading_name)
    if "temp" in name:
        return THRESHOLD_DEFAULTS["temp"]
    if "hum" in name:
        return THRESHOLD_DEFAULTS["hum"]
    if "flow" in name:
        return THRESHOLD_DEFAULTS["flow"]
    if "press" in name or "pressure" in name:
        return THRESHOLD_DEFAULTS["pressure"]
    return THRESHOLD_DEFAULTS["generic"]


def build_render_model(
    config: LabPulseConfig,
    alarm_defaults: AlarmDefaults | None = None,
) -> RenderModel:
    """Build the complete Home Assistant render model from validated config.

    The render model is the boundary between user config and Home Assistant
    templates. Templates should not need to know how IDs are derived.
    """

    services = []
    service_items = sorted(
        config.services.items(),
        key=lambda item: item[1].display.order,
    )

    for service_name, service_config in service_items:
        if not service_config.enabled:
            continue

        service_id = slug(service_name)
        display = service_config.display
        label = service_config.display_label
        service = ServiceModel(
            name                           = str(service_name),
            service_id                     = service_id,
            label                          = label,
            section                        = service_config.dashboard_section,
            icon                           = service_config.dashboard_icon,
            order                          = display.order,
            status_entity                  = EntityReference(
                platform="mqtt",
                unique_id=stable_id(service_name, "status"),
                default_entity_id=entity_id("sensor", service_name, "status"),
            ),
            required_danger_percent_entity      = entity_id("input_number", service_name, "required_danger_percent"),
            observation_window_seconds_entity  = entity_id("input_number", service_name, "observation_window_seconds"),
            required_recovery_seconds_entity   = entity_id("input_number", service_name, "required_recovery_seconds"),
            sensor_fault_confirm_seconds       = min(
                15,
                service_config.maximum_reading_age_seconds,
            ),
        )

        for reading in service_config.readings:
            configured_defaults = (
                alarm_defaults.get((service_name, reading.name))
                if alarm_defaults is not None
                else None
            )
            service.readings.append(
                build_reading_model(
                    service_name,
                    service_id,
                    reading,
                    configured_defaults,
                )
            )

        if service_config.power_detection is not None:
            service.power = build_power_model(
                service_name,
                service.readings,
                service_config.power_detection,
            )

        services.append(service)

    return RenderModel(services=services)


def build_power_model(
    service_name: str,
    readings: list[ReadingModel],
    config: PowerDetectionConfig,
) -> PowerModel:
    """Build the dedicated power model from normalized telemetry readings."""

    by_name = {reading.name: reading for reading in readings}
    prefix = (service_name, "power")
    return PowerModel(
        source=config.source,
        voltage=by_name["voltage"],
        battery_level=by_name["battery_level"],
        low_voltage_threshold=config.low_voltage_threshold,
        outage_confirm_seconds=config.outage_confirm_seconds,
        restore_confirm_seconds=config.restore_confirm_seconds,
        maximum_reading_age_seconds=config.maximum_reading_age_seconds,
        low_voltage_evidence_unique_id=stable_id(*prefix, "low_voltage_evidence"),
        low_voltage_evidence_entity=entity_id("binary_sensor", *prefix, "low_voltage_evidence"),
        sensor_fault_unique_id=stable_id(*prefix, "sensor_fault"),
        sensor_fault_entity=entity_id("binary_sensor", *prefix, "sensor_fault"),
        sensor_fault_confirmed_entity=entity_id(
            "input_boolean", *prefix, "sensor_fault_confirmed"
        ),
        state_entity=entity_id("input_select", *prefix, "state"),
        muted_entity=entity_id("input_boolean", *prefix, "muted"),
        outage_confirm_seconds_entity=entity_id("input_number", *prefix, "outage_confirm_seconds"),
        restore_confirm_seconds_entity=entity_id("input_number", *prefix, "restore_confirm_seconds"),
        timing_initialized_entity=entity_id("input_boolean", *prefix, "timing_initialized"),
        outage_candidate_entity=entity_id("input_boolean", *prefix, "outage_candidate"),
        recovery_candidate_entity=entity_id("input_boolean", *prefix, "recovery_candidate"),
        outage_active_entity=entity_id("input_boolean", *prefix, "outage_active"),
        outage_candidate_started_entity=entity_id("input_datetime", *prefix, "outage_candidate_started"),
        outage_candidate_deadline_entity=entity_id("input_datetime", *prefix, "outage_candidate_deadline"),
        recovery_candidate_started_entity=entity_id("input_datetime", *prefix, "recovery_candidate_started"),
        recovery_candidate_deadline_entity=entity_id("input_datetime", *prefix, "recovery_candidate_deadline"),
        outage_started_entity=entity_id("input_datetime", *prefix, "outage_started"),
        last_outage_started_entity=entity_id("input_datetime", *prefix, "last_outage_started"),
        last_outage_duration_entity=entity_id("input_number", *prefix, "last_outage_duration"),
        last_outage_started_sensor_unique_id=stable_id(*prefix, "last_outage_started"),
        last_outage_started_sensor_entity=entity_id("sensor", *prefix, "last_outage_started"),
        last_outage_duration_sensor_unique_id=stable_id(*prefix, "last_outage_duration"),
        last_outage_duration_sensor_entity=entity_id("sensor", *prefix, "last_outage_duration"),
    )


def build_reading_model(
    service_name: str,
    service_id: str,
    reading: ReadingConfig,
    configured_defaults: ReadingAlarmDefaults | None = None,
) -> ReadingModel:
    """Build template data for one configured reading."""

    reading_name = slug(reading.name)
    reading_id = f"{service_id}_{reading_name}"
    label = reading.display_label
    threshold = build_threshold(
        service_name,
        reading_name,
        reading,
        configured_defaults,
    )
    minimum = f"input_number.{stable_id(service_name, reading_name, 'minimum_threshold')}"
    maximum = f"input_number.{stable_id(service_name, reading_name, 'maximum_threshold')}"
    deadband = f"input_number.{stable_id(service_name, reading_name, 'recovery_deadband')}"

    return ReadingModel(
        name                        = reading_name,
        label                       = label,
        group                       = reading.group,
        reading_id                  = reading_id,
        mqtt_entity                 = EntityReference(
            platform="mqtt",
            unique_id=stable_id(service_name, reading_name),
            default_entity_id=entity_id("sensor", service_name, reading_name),
        ),
        alarm_controls_expanded_entity = entity_id("input_boolean", service_name, reading_name, "alarm_controls_expanded"),
        alarm_state_entity          = entity_id("input_select", service_name, reading_name, "alarm_state"),
        alarm_mode_entity           = entity_id("input_select", service_name, reading_name, "alarm_mode"),
        alarm_muted_entity          = entity_id("input_boolean", service_name, reading_name, "alarm_muted"),
        danger_zone_unique_id       = stable_id(service_name, reading_name, "danger_zone"),
        danger_zone_entity          = entity_id("binary_sensor", service_name, reading_name, "danger_zone"),
        recovery_zone_unique_id     = stable_id(service_name, reading_name, "recovery_zone"),
        recovery_zone_entity        = entity_id("binary_sensor", service_name, reading_name, "recovery_zone"),
        sensor_fault_zone_unique_id = stable_id(service_name, reading_name, "sensor_fault_zone"),
        sensor_fault_zone_entity    = entity_id("binary_sensor", service_name, reading_name, "sensor_fault_zone"),
        observed_danger_percent_unique_id = stable_id(service_name, reading_name, "observed_danger_percent"),
        observed_danger_percent_entity    = entity_id("sensor", service_name, reading_name, "observed_danger_percent"),
        default_alarm_mode          = default_alarm_mode(reading_name),
        minimum_threshold_entity    = minimum,
        maximum_threshold_entity    = maximum,
        recovery_deadband_entity    = deadband,
        threshold                   = threshold,
    )

def default_alarm_mode(reading_name: str) -> str:
    """Infer the initial Home Assistant alarm mode for one reading."""

    name = slug(reading_name)
    if "flow" in name or "press" in name or "pressure" in name:
        return "Low Only"
    return "Range"


def build_threshold(
    service_name: str,
    reading_name: str,
    reading: ReadingConfig,
    configured: ReadingAlarmDefaults | None,
) -> ThresholdModel:
    """Return default editable threshold helper settings for one reading.

    Threshold values come from alarm_defaults.json rather than hardware config.
    Once generated, users can still tune the Home Assistant dashboard helpers.
    """

    metadata = reading_defaults(reading_name)
    defaults = configured or ReadingAlarmDefaults(
        minimum=metadata["min"],
        maximum=metadata["max"],
        deadband=metadata["deadband"],
    )
    if not metadata["range_min"] <= defaults.minimum <= metadata["range_max"]:
        raise ValueError(
            f"alarm default {service_name}.{reading_name}.minimum is outside "
            f"{metadata['range_min']}..{metadata['range_max']}"
        )
    if not metadata["range_min"] <= defaults.maximum <= metadata["range_max"]:
        raise ValueError(
            f"alarm default {service_name}.{reading_name}.maximum is outside "
            f"{metadata['range_min']}..{metadata['range_max']}"
        )
    version_payload = json.dumps(defaults.model_dump(), sort_keys=True).encode("utf-8")
    version = hashlib.sha256(version_payload).hexdigest()[:12]

    return ThresholdModel(
        unit=reading.unit or str(metadata["unit"]),
        minimum=defaults.minimum,
        maximum=defaults.maximum,
        deadband=defaults.deadband,
        range_min=metadata["range_min"],
        range_max=metadata["range_max"],
        step=metadata["step"],
        version=version,
    )


@dataclass
class GeneratorPaths:
    """Filesystem paths used by the Home Assistant generator."""

    config_path: Path
    ha_config_dir: Path

    @property
    def alarm_defaults_path(self) -> Path:
        """Return the user-owned alarm defaults beside the selected config."""

        return self.config_path.parent / "alarm_defaults.json"

    @property
    def packages_dir(self) -> Path:
        """Return the Home Assistant packages directory."""

        return self.ha_config_dir / "packages"

    @property
    def package_path(self) -> Path:
        """Return the generated package YAML path."""

        return self.packages_dir / "labpulse_generated.yaml"

    @property
    def entity_map_path(self) -> Path:
        """Return the generated entity map path."""

        return self.ha_config_dir / "labpulse_entity_map.yaml"

    @property
    def configuration_path(self) -> Path:
        """Return Home Assistant's main configuration path."""

        return self.ha_config_dir / "configuration.yaml"

    @property
    def ui_automations_path(self) -> Path:
        """Return the Home Assistant UI-managed automations path."""

        return self.ha_config_dir / "automations.yaml"

    @property
    def ui_scripts_path(self) -> Path:
        """Return the Home Assistant UI-managed scripts path."""

        return self.ha_config_dir / "scripts.yaml"

    @property
    def ui_scenes_path(self) -> Path:
        """Return the Home Assistant UI-managed scenes path."""

        return self.ha_config_dir / "scenes.yaml"

    @property
    def storage_dir(self) -> Path:
        """Return Home Assistant's hidden UI storage directory."""

        return self.ha_config_dir / ".storage"

    @property
    def lovelace_path(self) -> Path:
        """Return the active storage-backed Overview dashboard file."""

        registry_path = self.storage_dir / "lovelace_dashboards"
        if registry_path.exists():
            try:
                registry = json.loads(registry_path.read_text(encoding="utf-8"))
                items = registry.get("data", {}).get("items", [])
                overview = next(
                    (
                        item
                        for item in items
                        if item.get("url_path") == "lovelace"
                        and item.get("mode", "storage") == "storage"
                    ),
                    None,
                )
                if overview and isinstance(overview.get("id"), str):
                    return self.storage_dir / f"lovelace.{overview['id']}"
            except (OSError, json.JSONDecodeError, AttributeError):
                pass
        return self.storage_dir / "lovelace"
