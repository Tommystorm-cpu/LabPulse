"""Render Home Assistant template files from a normalized model."""

from pathlib import Path
import json

import yaml

from .alarm import package_context
from .dashboard import lovelace_document
from .model import GeneratorOptions, GeneratorPaths, RenderModel


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def render_all(paths: GeneratorPaths, options: GeneratorOptions, model: RenderModel) -> None:
    """Write generated Home Assistant files and optionally reset dashboard."""

    paths.ha_config_dir.mkdir(parents=True, exist_ok=True)
    paths.packages_dir.mkdir(parents=True, exist_ok=True)

    write_template(
        "configuration.yaml.j2",
        paths.configuration_path,
        {"body": ""},
    )
    write_template(
        "package.yaml.j2",
        paths.package_path,
        package_context(model),
    )
    write_template(
        "entity_map.yaml.j2",
        paths.entity_map_path,
        {"entity_map": yaml.safe_dump(entity_map(model), sort_keys=False).rstrip()},
    )
    ensure_ui_yaml_files(paths)

    if options.reset_dashboard:
        paths.storage_dir.mkdir(parents=True, exist_ok=True)
        write_template(
            "initial_lovelace.json.j2",
            paths.lovelace_path,
            {"dashboard_json": json.dumps(lovelace_document(model), indent=2)},
        )
        print(f"Reset editable dashboard {paths.lovelace_path}")
    else:
        print(f"Preserved editable dashboard {paths.lovelace_path}")

    print(f"Generated {paths.configuration_path}")
    print(f"Generated {paths.package_path}")
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


def write_template(template_name: str, destination: Path, context: dict[str, str]) -> None:
    """Render a simple placeholder template to disk."""

    text = (TEMPLATE_DIR / template_name).read_text(encoding="utf-8")
    for key, value in context.items():
        text = text.replace("{{ " + key + " }}", value)
    destination.write_text(text.rstrip() + "\n", encoding="utf-8")


def entity_map(model: RenderModel) -> dict[str, object]:
    """Return a human-readable map of LabPulse generated entities."""

    result: dict[str, object] = {}
    for service in model.services:
        service_map: dict[str, object] = {
            "status": {
                "mqtt_unique_id": service.status_unique_id,
                "expected_entity_id": service.status_entity_id,
            }
        }
        for reading in service.readings:
            service_map[reading.name] = {
                "mqtt_unique_id": reading.mqtt_unique_id,
                "expected_entity_id": reading.expected_entity_id,
                "alarm_entity_id": reading.alarm_entity_id,
                "active_alert": reading.active_alert_entity,
                "minimum_threshold": reading.minimum_threshold_entity,
                "maximum_threshold": reading.maximum_threshold_entity,
                "alert_delay": service.alert_delay_entity,
                "recovery_delay": service.recovery_delay_entity,
            }
        result[service.name] = service_map
    return result
