"""Build the seeded Lovelace dashboard from editable YAML rules."""

import json
from pathlib import Path
from typing import Any

import yaml

from .data_models import GeneratorPaths, RenderModel, ServiceModel
from .template_utils import expand_template, render_template_file


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "dashboard"


def render_dashboard(
    paths: GeneratorPaths,
    reset_dashboard: bool,
    model: RenderModel,
) -> None:
    """Reset the editable dashboard when requested, otherwise preserve it."""

    if reset_dashboard:
        paths.storage_dir.mkdir(parents=True, exist_ok=True)
        render_template_file(
            TEMPLATE_DIR / "initial_lovelace.json.j2",
            paths.lovelace_path,
            {"dashboard_json": json.dumps(lovelace_document(model), indent=2)},
        )
        print(f"Reset editable dashboard {paths.lovelace_path}")
    else:
        print(f"Preserved editable dashboard {paths.lovelace_path}")


def lovelace_document(model: RenderModel) -> dict[str, object]:
    """Return the starter Lovelace storage document."""

    seed = load_dashboard_seed()
    monitor_view = dict(seed["lovelace"]["monitor_view"])
    monitor_view["sections"] = monitor_sections(seed, model)
    alarm_setup_view = dict(seed["lovelace"]["alarm_setup_view"])
    alarm_setup_view["sections"] = alarm_setup_sections(seed, model)

    return {
        "version": seed["lovelace"]["version"],
        "minor_version": seed["lovelace"]["minor_version"],
        "key": seed["lovelace"]["key"],
        "data": {"config": {"views": [monitor_view, alarm_setup_view]}},
    }


def load_dashboard_seed() -> dict[str, Any]:
    """Load editable dashboard seed rules."""

    return yaml.safe_load((TEMPLATE_DIR / "dashboard_seed.yaml").read_text(encoding="utf-8"))


def monitor_sections(seed: dict[str, Any], model: RenderModel) -> list[dict[str, object]]:
    """Expand monitor dashboard sections for all enabled services."""

    sections = [system_health_section(seed, model)]
    sections.extend(monitor_service_section(seed, service) for service in model.services)
    return sections


def alarm_setup_sections(seed: dict[str, Any], model: RenderModel) -> list[dict[str, object]]:
    """Expand alarm setup dashboard sections for all enabled services."""

    return [alarm_setup_service_section(seed, service) for service in model.services]


def system_health_section(seed: dict[str, Any], model: RenderModel) -> dict[str, object]:
    """Return the system health dashboard section."""

    rules = seed["system_health"]
    cards = [expand_template(rules["heading_card"], {})]
    cards.extend(
        expand_template(rules["status_tile"], {"service": service})
        for service in model.services
    )
    return {"type": "grid", "cards": cards}


def monitor_service_section(seed: dict[str, Any], service: ServiceModel) -> dict[str, object]:
    """Return one monitor dashboard section for a service."""

    rules = seed["monitor_sections"]
    cards = [
        expand_template(rules["heading_card"], {"service": service}),
        expand_template(rules["status_tile"], {"service": service}),
    ]
    for reading in service.readings:
        context = {"service": service, "reading": reading}
        cards.append(expand_template(rules["reading_tile"], context))
        cards.append(expand_template(rules["state_tile"], context))
        cards.append(expand_template(rules["mute_tile"], context))

    return {"type": "grid", "cards": cards}


def alarm_setup_service_section(seed: dict[str, Any], service: ServiceModel) -> dict[str, object]:
    """Return one alarm setup dashboard section for a service."""

    rules = seed["alarm_setup_sections"]
    cards = [
        expand_template(rules["heading_card"], {"service": service}),
        expand_template(rules["controls_toggle_tile"], {"service": service}),
        expand_template(rules["service_tuning_card"], {"service": service}),
    ]
    for reading in service.readings:
        cards.append(
            expand_template(
                rules["reading_settings_card"],
                {"service": service, "reading": reading},
            )
        )

    return {"type": "grid", "cards": cards}

