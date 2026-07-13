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
                "expected_entity_id": service.status_entity_id,
            },
            "alarm_controls_expanded": service.alarm_controls_expanded_entity,
        }
        for reading in service.readings:
            service_map[reading.name] = {
                "mqtt_unique_id": reading.mqtt_unique_id,
                "expected_entity_id": reading.expected_entity_id,
                "alarm_state": reading.alarm_state_entity,
                "alarm_mode": reading.alarm_mode_entity,
                "alarm_muted": reading.alarm_muted_entity,
                "minimum_threshold": reading.minimum_threshold_entity,
                "maximum_threshold": reading.maximum_threshold_entity,
                "recovery_deadband": reading.recovery_deadband_entity,
                "danger_zone": reading.danger_zone_entity,
                "recovery_zone": reading.recovery_zone_entity,
                "sensor_fault_zone": reading.sensor_fault_zone_entity,
                "danger_ratio": reading.danger_ratio_entity,
                "danger_ratio_percent": service.danger_ratio_percent_entity,
                "danger_window_seconds": service.danger_window_seconds_entity,
                "recovery_seconds": service.recovery_seconds_entity,
                "stale_timeout_seconds": service.stale_timeout_seconds_entity,
            }
        result[service.name] = service_map
    return result
