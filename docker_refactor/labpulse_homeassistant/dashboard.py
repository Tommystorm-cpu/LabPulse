"""Build the seeded Lovelace dashboard from editable YAML rules."""

import json
from pathlib import Path
from typing import Any

import yaml

from .data_models import GeneratorPaths, ReadingModel, RenderModel, ServiceModel
from .template_utils import expand_template, render_template_file


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "dashboard"


def render_dashboard(
    paths: GeneratorPaths,
    reset_dashboard: bool,
    model: RenderModel,
    sync_entity_ids: bool = False,
    replacements: dict[str, str] | None = None,
) -> None:
    """Reset, surgically synchronize, or preserve the editable dashboard."""

    if reset_dashboard:
        paths.storage_dir.mkdir(parents=True, exist_ok=True)
        render_template_file(
            TEMPLATE_DIR / "initial_lovelace.json.j2",
            paths.lovelace_path,
            {
                "dashboard_json": json.dumps(
                    lovelace_document(model, paths.lovelace_path.name), indent=2
                )
            },
        )
        print(f"Reset editable dashboard {paths.lovelace_path}")
    elif sync_entity_ids:
        sync_dashboard_entity_ids(paths.lovelace_path, replacements or {})
    else:
        print(f"Preserved editable dashboard {paths.lovelace_path}")


def sync_dashboard_entity_ids(
    dashboard_path: Path,
    replacements: dict[str, str],
) -> None:
    """Replace exact entity-ID strings while preserving dashboard structure."""

    if not dashboard_path.exists():
        raise FileNotFoundError(
            f"Cannot synchronize missing editable dashboard: {dashboard_path}"
        )
    document = json.loads(dashboard_path.read_text(encoding="utf-8"))
    updated, replacement_count = replace_entity_references(document, replacements)
    dashboard_path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    print(
        f"Synchronized {replacement_count} dashboard entity references "
        f"in {dashboard_path}"
    )


def replace_entity_references(
    value: object,
    replacements: dict[str, str],
) -> tuple[object, int]:
    """Recursively replace complete string values and keys matching known IDs."""

    if isinstance(value, dict):
        result: dict[object, object] = {}
        count = 0
        for key, child in value.items():
            replaced_key = replacements.get(key, key) if isinstance(key, str) else key
            if replaced_key != key:
                count += 1
            replaced_child, child_count = replace_entity_references(child, replacements)
            result[replaced_key] = replaced_child
            count += child_count
        return result, count
    if isinstance(value, list):
        result_list = []
        count = 0
        for child in value:
            replaced_child, child_count = replace_entity_references(child, replacements)
            result_list.append(replaced_child)
            count += child_count
        return result_list, count
    if isinstance(value, str) and value in replacements:
        return replacements[value], 1
    return value, 0


def lovelace_document(model: RenderModel, storage_key: str = "lovelace") -> dict[str, object]:
    """Return the starter Lovelace storage document."""

    seed = load_dashboard_seed()
    monitor_view = dict(seed["lovelace"]["monitor_view"])
    monitor_view["sections"] = monitor_sections(seed, model)
    alarm_setup_view = dict(seed["lovelace"]["alarm_setup_view"])
    alarm_setup_view["sections"] = alarm_setup_sections(seed, model)

    return {
        "version": seed["lovelace"]["version"],
        "minor_version": seed["lovelace"]["minor_version"],
        "key": storage_key,
        "data": {"config": {"views": [monitor_view, alarm_setup_view]}},
    }


def load_dashboard_seed() -> dict[str, Any]:
    """Load editable dashboard seed rules."""

    return yaml.safe_load((TEMPLATE_DIR / "dashboard_seed.yaml").read_text(encoding="utf-8"))


def monitor_sections(seed: dict[str, Any], model: RenderModel) -> list[dict[str, object]]:
    """Expand monitor sections, merging services with the same section label."""

    return [
        monitor_location_section(seed, services)
        for services in services_by_section(model.services)
    ]


def services_by_section(services: list[ServiceModel]) -> list[list[ServiceModel]]:
    """Group ordered services by dashboard section without changing section order."""

    grouped: dict[str, list[ServiceModel]] = {}
    for service in services:
        grouped.setdefault(service.section, []).append(service)
    return list(grouped.values())


def readings_by_group(
    readings: list[ReadingModel],
) -> list[tuple[str | None, list[ReadingModel]]]:
    """Group readings by optional presentation label while preserving order."""

    grouped: dict[str | None, list[ReadingModel]] = {}
    for reading in readings:
        grouped.setdefault(reading.group, []).append(reading)
    return list(grouped.items())


def alarm_setup_sections(seed: dict[str, Any], model: RenderModel) -> list[dict[str, object]]:
    """Expand alarm setup dashboard sections for all enabled services."""

    return [global_alarm_setup_section(seed, model)] + [
        alarm_setup_service_section(seed, service) for service in model.services
    ]


def global_alarm_setup_section(
    seed: dict[str, Any], model: RenderModel
) -> dict[str, object]:
    """Return the global notification controls at the top of Alarm Setup."""

    rules = seed["global_alarm_setup"]
    return {
        "type": "grid",
        "cards": [
            expand_template(rules["heading_card"], {"model": model}),
            expand_template(rules["settings_card"], {"model": model}),
            expand_template(rules["phone_book_button"], {"model": model}),
        ],
    }


def monitor_location_section(
    seed: dict[str, Any],
    services: list[ServiceModel],
) -> dict[str, object]:
    """Return one monitor section for services sharing a display section."""

    rules = seed["monitor_sections"]
    cards = [expand_template(rules["heading_card"], {"service": services[0]})]

    for service in services:
        cards.append(
            expand_template(rules["service_heading_card"], {"service": service})
        )
        cards.append(expand_template(rules["status_tile"], {"service": service}))
        if service.power is not None:
            cards.append(
                expand_template(
                    seed["power_monitor"]["battery_gauge"],
                    {"service": service, "power": service.power},
                )
            )
            cards.append(
                expand_template(
                    seed["power_monitor"]["reading_list"],
                    {"service": service, "power": service.power},
                )
            )
            continue
        for _, readings in readings_by_group(service.readings):
            reading_list = expand_template(rules["reading_list"], {"service": service})
            reading_list["entities"] = [
                expand_template(
                    rules["reading_entity"],
                    {"service": service, "reading": reading},
                )
                for reading in readings
            ]
            cards.append(reading_list)

    return {"type": "grid", "cards": cards}


def alarm_setup_service_section(seed: dict[str, Any], service: ServiceModel) -> dict[str, object]:
    """Return one alarm setup dashboard section for a service."""

    rules = seed["alarm_setup_sections"]
    cards = [expand_template(rules["heading_card"], {"service": service})]
    if service.power is not None:
        cards.append(
            expand_template(
                seed["power_alarm_setup"]["settings_card"],
                {"service": service, "power": service.power},
            )
        )
        return {"type": "grid", "cards": cards}

    cards.append(expand_template(rules["service_tuning_card"], {"service": service}))
    for reading in service.readings:
        context = {"service": service, "reading": reading}
        cards.append(expand_template(rules["controls_toggle_tile"], context))
        cards.append(expand_template(rules["reading_settings_card"], context))

    return {"type": "grid", "cards": cards}
