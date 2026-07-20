"""Write core Home Assistant configuration from a normalized render model."""

from pathlib import Path

import yaml

from .render_model import RenderModel
from .paths import GeneratorPaths
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
                "mqtt_unique_id": service.status_entity.unique_id,
                "entity_id": service.status_entity.entity_id,
            },
            "service_health": {
                "unhealthy": service.entities["health_unhealthy"],
                "fault_active": service.entities["health_fault_active"],
                "fault_started": service.entities["health_fault_started"],
                "fault_confirm_seconds": service.health_fault_confirm_seconds,
                "recovery_confirm_seconds": service.health_recovery_confirm_seconds,
            },
        }
        for measurement in service.measurements:
            measurement_map = {
                "mqtt_unique_id": measurement.mqtt_entity.unique_id,
                "entity_id": measurement.mqtt_entity.entity_id,
            }
            if service.power is None:
                measurement_map.update(
                    **{
                        key: value
                        for key, value in measurement.entities.items()
                        if key != "alarm_timing_initialized"
                    },
                )
            service_map[measurement.name] = measurement_map
        if service.power is not None:
            power = service.power
            service_map["power_lifecycle"] = {
                "source": power.config.source,
                "raw_mains_present": power.mains_present.mqtt_entity.entity_id,
                "mains_present": power.entities["mains_present"],
                "sensor_fault": power.entities["sensor_fault"],
                "sensor_fault_confirmed": power.entities["sensor_fault_confirmed"],
                "state": power.entities["state"],
                "muted": power.entities["muted"],
                "outage_active": power.entities["outage_active"],
                "outage_confirm_seconds": power.config.outage_confirm_seconds,
                "restore_confirm_seconds": power.config.restore_confirm_seconds,
                "last_outage_started": power.entities["last_outage_started_sensor"],
                "last_outage_duration": power.entities["last_outage_duration_sensor"],
                "last_outage_started_storage": power.entities["last_outage_started"],
                "last_outage_duration_storage": power.entities["last_outage_duration"],
            }
        result[service.name] = service_map
    return result
