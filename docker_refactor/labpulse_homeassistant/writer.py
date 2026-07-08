"""Write generated LabPulse Home Assistant config files.

The build modules return plain Python dictionaries. This module is the only
place that turns those dictionaries into YAML/JSON files under Home Assistant's
config directory.
"""

import json
import re

import yaml

from .models import GeneratedConfig, GeneratorOptions, GeneratorPaths, JsonDict


DEFAULT_CONFIGURATION = """homeassistant:
  packages: !include_dir_named packages

default_config:

frontend:

history:

logbook:

my:

mobile_app:

system_health:
"""


def ensure_configuration_file(paths: GeneratorPaths) -> None:
    """Create/update configuration.yaml with LabPulse's package include.

    MQTT broker settings are intentionally not written here; Home Assistant's
    MQTT integration owns the broker connection. The package include is the
    only required generated setting.
    """

    paths.ha_config_dir.mkdir(parents=True, exist_ok=True)

    if not paths.configuration_path.exists():
        paths.configuration_path.write_text(DEFAULT_CONFIGURATION, encoding="utf-8")
        return

    text = paths.configuration_path.read_text(encoding="utf-8")
    additions = []

    text = re.sub(
        r"(?ms)^mqtt:\n  broker: 127\.0\.0\.1\n  port: 1883\n?",
        "",
        text,
    )

    if "!include_dir_named packages" not in text:
        if re.search(r"(?m)^homeassistant:\s*$", text):
            text = re.sub(
                r"(?m)^homeassistant:\s*$",
                "homeassistant:\n  packages: !include_dir_named packages",
                text,
                count=1,
            )
        else:
            additions.append("homeassistant:\n  packages: !include_dir_named packages\n")

    if additions:
        separator = "\n" if text.endswith("\n") else "\n\n"
        text = text + separator + "\n".join(additions)

    paths.configuration_path.write_text(text, encoding="utf-8")


def write_lovelace_dashboard(
    paths: GeneratorPaths,
    options: GeneratorOptions,
    sections: list[JsonDict],
) -> None:
    """Seed or refresh the editable Home Assistant UI dashboard.

    Existing dashboards are preserved by default so user edits made in the Home
    Assistant UI survive normal config regeneration.
    """

    if (
        paths.lovelace_path.exists()
        and not options.fresh_homeassistant
        and not options.refresh_dashboard
    ):
        print(f"Preserved existing editable dashboard: {paths.lovelace_path}")
        return

    paths.storage_dir.mkdir(parents=True, exist_ok=True)
    dashboard = lovelace_storage_document(sections)
    paths.lovelace_path.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")


def lovelace_storage_document(sections: list[JsonDict]) -> JsonDict:
    """Return Home Assistant's `.storage/lovelace` document shape."""

    return {
        "version": 1,
        "minor_version": 1,
        "key": "lovelace",
        "data": {
            "config": {
                "views": [
                    {
                        "title": "LabPulse",
                        "path": "labpulse",
                        "type": "sections",
                        "sections": sections,
                    }
                ]
            }
        },
    }


def write_generated_files(
    paths: GeneratorPaths,
    options: GeneratorOptions,
    generated: GeneratedConfig,
) -> None:
    """Write generated package, dashboard helper, and UI files to disk."""

    paths.packages_dir.mkdir(parents=True, exist_ok=True)
    package = {
        "input_number": generated.input_numbers,
        "input_boolean": generated.input_booleans,
        "automation": generated.automations,
    }

    paths.package_path.write_text(yaml.safe_dump(package, sort_keys=False), encoding="utf-8")
    paths.dashboard_cards_path.write_text(
        yaml.safe_dump(generated.dashboard_cards, sort_keys=False),
        encoding="utf-8",
    )
    ensure_configuration_file(paths)

    sections = [{"type": "grid", "cards": generated.system_health_cards}]
    sections.extend(generated.dashboard_sections)
    write_lovelace_dashboard(
        paths,
        options,
        sections,
    )

    print(f"Generated {paths.package_path}")
    print(f"Generated {paths.dashboard_cards_path}")
    print(f"Updated {paths.configuration_path}")
    print(f"Generated or preserved editable dashboard {paths.lovelace_path}")
