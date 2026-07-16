"""Write Home Assistant YAML files from a normalized model."""

from pathlib import Path

import yaml

from .data_models import GeneratorPaths, RenderModel
from .template_utils import render_template_file


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "core"


def render_core(paths: GeneratorPaths, model: RenderModel) -> None:
    """Write shared Home Assistant configuration and diagnostic files."""

    paths.ha_config_dir.mkdir(parents=True, exist_ok=True)

    render_template_file(
        TEMPLATE_DIR / "configuration.yaml.j2",
        paths.configuration_path,
        {"body": ""},
    )
    render_template_file(
        TEMPLATE_DIR / "entity_map.yaml.j2",
        paths.entity_map_path,
        {"entity_map": yaml.safe_dump(entity_map(model), sort_keys=False).rstrip()},
    )
    ensure_ui_yaml_files(paths)

    print(f"Generated {paths.configuration_path}")
    print(f"Generated {paths.entity_map_path}")


def ensure_ui_yaml_files(paths: GeneratorPaths) -> None:
    """Create Home Assistant UI-managed YAML files if they are missing.

    Home Assistant's automation/script/scene editors write to these files.
    They must be included by configuration.yaml, but the generator should never
    overwrite them once a user has made UI edits.
    """

    for path in (paths.ui_automations_path, paths.ui_scripts_path, paths.ui_scenes_path):
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")
            print(f"Created {path}")

def entity_map(model: RenderModel) -> dict[str, object]:
    """Return a human-readable map of LabPulse generated entities."""

    result: dict[str, object] = {}
    for service in model.services:
        service_map: dict[str, object] = {
            "status": {
                "mqtt_unique_id": service.status_unique_id,
                "default_entity_id": service.status_entity.default_entity_id,
                "resolved_entity_id": service.status_entity.resolved_entity_id,
                "effective_entity_id": service.status_entity_id,
                "resolution_status": service.status_entity.resolution_status,
            }
        }
        for reading in service.readings:
            reading_map = {
                "mqtt_unique_id": reading.mqtt_unique_id,
                "default_entity_id": reading.mqtt_entity.default_entity_id,
                "resolved_entity_id": reading.mqtt_entity.resolved_entity_id,
                "effective_entity_id": reading.expected_entity_id,
                "resolution_status": reading.mqtt_entity.resolution_status,
            }
            if service.power is None:
                reading_map.update(
                    alarm_state=reading.alarm_state_entity,
                    alarm_mode=reading.alarm_mode_entity,
                    alarm_muted=reading.alarm_muted_entity,
                    minimum_threshold=reading.minimum_threshold_entity,
                    maximum_threshold=reading.maximum_threshold_entity,
                    recovery_deadband=reading.recovery_deadband_entity,
                    danger_zone=reading.danger_zone_entity,
                    recovery_zone=reading.recovery_zone_entity,
                    sensor_fault_zone=reading.sensor_fault_zone_entity,
                    observed_danger_percent=reading.observed_danger_percent_entity,
                    required_danger_percent=service.required_danger_percent_entity,
                    observation_window_seconds=service.observation_window_seconds_entity,
                    required_recovery_seconds=service.required_recovery_seconds_entity,
                    alarm_controls_expanded=reading.alarm_controls_expanded_entity,
                )
            service_map[reading.name] = reading_map
        if service.power is not None:
            power = service.power
            service_map["power_lifecycle"] = {
                "evidence_source": power.source,
                "low_voltage_evidence": power.low_voltage_evidence_entity,
                "voltage_change": power.voltage_change_entity,
                "charge_change": power.charge_change_entity,
                "outage_transition": power.outage_transition_entity,
                "recovery_transition": power.recovery_transition_entity,
                "sensor_fault": power.sensor_fault_entity,
                "sensor_fault_confirmed": power.sensor_fault_confirmed_entity,
                "state": power.state_entity,
                "muted": power.muted_entity,
                "outage_confirm_seconds": power.outage_confirm_seconds_entity,
                "restore_confirm_seconds": power.restore_confirm_seconds_entity,
                "last_outage_started": power.last_outage_started_sensor_entity,
                "last_outage_duration": power.last_outage_duration_sensor_entity,
                "last_outage_started_storage": power.last_outage_started_entity,
                "last_outage_duration_storage": power.last_outage_duration_entity,
            }
        result[service.name] = service_map
    return result


def load_previous_entity_ids(entity_map_path: Path) -> dict[str, str]:
    """Return unique-ID to effective-entity-ID mappings from an earlier run."""

    if not entity_map_path.exists():
        return {}
    payload = yaml.safe_load(entity_map_path.read_text(encoding="utf-8")) or {}
    result: dict[str, str] = {}

    def visit(value: object) -> None:
        if isinstance(value, dict):
            unique_id = value.get("mqtt_unique_id")
            entity_id = value.get("effective_entity_id") or value.get("expected_entity_id")
            if isinstance(unique_id, str) and isinstance(entity_id, str):
                result[unique_id] = entity_id
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return result
