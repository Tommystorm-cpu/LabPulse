"""Normalize LabPulse config into Home Assistant template data."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from labpulse_common.config import LabPulseConfig, ReadingConfig
from labpulse_common.identity import entity_id, slug, stable_id
from labpulse_common.mqtt_contracts import SMS_SEND_TOPIC


JsonDict = dict[str, Any]


THRESHOLD_DEFAULTS: dict[str, JsonDict] = {
    "temp": {"unit": "\u00b0C", "min": 5, "max": 35, "range_min": -20, "range_max": 80, "step": 0.1},
    "hum": {"unit": "%", "min": 20, "max": 80, "range_min": 0, "range_max": 100, "step": 1},
    "flow": {"unit": "L/min", "min": 1, "max": 999, "range_min": 0, "range_max": 999, "step": 0.1},
    "pressure": {"unit": "bar", "min": 1, "max": 999, "range_min": 0, "range_max": 999, "step": 0.1},
    "generic": {"unit": "", "min": 0, "max": 999, "range_min": 0, "range_max": 999, "step": 1},
}


@dataclass
class GeneratorPaths:
    """Filesystem paths used by the Home Assistant generator."""

    config_path: Path
    ha_config_dir: Path

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
        """Return the editable Lovelace dashboard storage file."""

        return self.storage_dir / "lovelace"


@dataclass
class GeneratorOptions:
    """Command-line options passed from the shell wrapper."""

    reset_dashboard: bool


@dataclass
class ThresholdModel:
    """Default Home Assistant helper settings for one reading.

    User config describes hardware and labels only. Alarm behavior is always a
    Home Assistant min/max range check, with editable helper values rendered
    from these defaults.
    """

    unit: str
    minimum: float | int
    maximum: float | int
    range_min: float | int
    range_max: float | int
    step: float | int


@dataclass
class ReadingModel:
    """Template data for one Home Assistant reading.

    `active_alert_entity` is separate from the alarm binary sensor. The binary
    sensor represents current threshold state; the boolean records whether an
    alert notification has already fired so recovery notifications only happen
    after a real alert.
    """

    name: str
    label: str
    reading_id: str
    mqtt_unique_id: str
    expected_entity_id: str
    alarm_unique_id: str
    alarm_entity_id: str
    active_alert_entity: str
    minimum_threshold_entity: str
    maximum_threshold_entity: str
    threshold: ThresholdModel


@dataclass
class ServiceModel:
    """Template data for one enabled LabPulse service."""

    name: str
    service_id: str
    label: str
    section: str
    icon: str
    order: int
    status_unique_id: str
    status_entity_id: str
    alert_delay_entity: str
    recovery_delay_entity: str
    readings: list[ReadingModel] = field(default_factory=list)


@dataclass
class RenderModel:
    """All data needed to render Home Assistant templates."""

    services: list[ServiceModel]
    sms_send_topic: str = SMS_SEND_TOPIC

    @property
    def readings(self) -> list[tuple[ServiceModel, ReadingModel]]:
        """Return all readings paired with their parent service."""

        return [
            (service, reading)
            for service in self.services
            for reading in service.readings
        ]


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


def build_render_model(config: LabPulseConfig) -> RenderModel:
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
            name=str(service_name),
            service_id=service_id,
            label=label,
            section=service_config.dashboard_section,
            icon=service_config.dashboard_icon,
            order=display.order,
            status_unique_id=stable_id(service_name, "status"),
            status_entity_id=entity_id("sensor", service_name, "status"),
            alert_delay_entity=f"input_number.{stable_id(service_name, 'alert_delay_seconds')}",
            recovery_delay_entity=f"input_number.{stable_id(service_name, 'recovery_delay_seconds')}",
        )

        for reading in service_config.readings:
            service.readings.append(build_reading_model(service_name, service_id, reading))

        services.append(service)

    return RenderModel(services=services)


def build_reading_model(
    service_name: str,
    service_id: str,
    reading: ReadingConfig,
) -> ReadingModel:
    """Build template data for one configured reading."""

    reading_name = slug(reading.name)
    reading_id = f"{service_id}_{reading_name}"
    label = reading.display_label
    threshold = build_threshold(reading_name, reading)
    minimum = f"input_number.{stable_id(service_name, reading_name, 'minimum_threshold')}"
    maximum = f"input_number.{stable_id(service_name, reading_name, 'maximum_threshold')}"

    return ReadingModel(
        name=reading_name,
        label=label,
        reading_id=reading_id,
        mqtt_unique_id=stable_id(service_name, reading_name),
        expected_entity_id=entity_id("sensor", service_name, reading_name),
        alarm_unique_id=stable_id(service_name, reading_name, "alarm"),
        alarm_entity_id=entity_id("binary_sensor", service_name, reading_name, "alarm"),
        active_alert_entity=entity_id("input_boolean", service_name, reading_name, "alert_active"),
        minimum_threshold_entity=minimum,
        maximum_threshold_entity=maximum,
        threshold=threshold,
    )


def build_threshold(reading_name: str, reading: ReadingConfig) -> ThresholdModel:
    """Return default editable threshold helper settings for one reading.

    Threshold values intentionally do not come from `config.yaml`. Once
    generated, users tune them in Home Assistant's dashboard helpers.
    """

    defaults = reading_defaults(reading_name)

    return ThresholdModel(
        unit=reading.unit or str(defaults["unit"]),
        minimum=defaults["min"],
        maximum=defaults["max"],
        range_min=defaults["range_min"],
        range_max=defaults["range_max"],
        step=defaults["step"],
    )
