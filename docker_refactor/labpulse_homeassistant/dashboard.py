"""Build the seeded Lovelace dashboard from editable YAML rules."""

from pathlib import Path
from typing import Any

import yaml

from .model import RenderModel, ServiceModel
from .template_utils import expand_template


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def lovelace_document(model: RenderModel) -> dict[str, object]:
    """Return the starter Lovelace storage document."""

    seed = load_dashboard_seed()
    view = dict(seed["lovelace"]["view"])
    view["sections"] = dashboard_sections(seed, model)

    return {
        "version": seed["lovelace"]["version"],
        "minor_version": seed["lovelace"]["minor_version"],
        "key": seed["lovelace"]["key"],
        "data": {"config": {"views": [view]}},
    }


def load_dashboard_seed() -> dict[str, Any]:
    """Load editable dashboard seed rules."""

    return yaml.safe_load((TEMPLATE_DIR / "dashboard_seed.yaml").read_text(encoding="utf-8"))


def dashboard_sections(seed: dict[str, Any], model: RenderModel) -> list[dict[str, object]]:
    """Expand configured dashboard sections for all enabled services."""

    sections = [system_health_section(seed, model)]
    sections.extend(service_section(seed, service) for service in model.services)
    return sections


def system_health_section(seed: dict[str, Any], model: RenderModel) -> dict[str, object]:
    """Return the system health dashboard section."""

    rules = seed["system_health"]
    cards = [expand_template(rules["heading_card"], {})]
    cards.extend(
        expand_template(rules["status_tile"], {"service": service})
        for service in model.services
    )
    return {"type": "grid", "cards": cards}


def service_section(seed: dict[str, Any], service: ServiceModel) -> dict[str, object]:
    """Return one service dashboard section."""

    rules = seed["service_sections"]
    cards = [
        expand_template(rules["heading_card"], {"service": service}),
        expand_template(rules["status_tile"], {"service": service}),
    ]
    for reading in service.readings:
        context = {"service": service, "reading": reading}
        cards.append(expand_template(rules["reading_tile"], context))
        cards.append(expand_template(rules["alarm_tile"], context))

    if service.readings and rules.get("include_alarm_settings_card", True):
        cards.append(alarm_settings_card(seed, service))
    if service.readings and rules.get("include_alert_memory_card", True):
        cards.append(alert_memory_card(seed, service))

    return {"type": "grid", "cards": cards}


def alarm_settings_card(seed: dict[str, Any], service: ServiceModel) -> dict[str, object]:
    """Return a service alarm settings card from seed rules."""

    rules = seed["alarm_settings_card"]
    card = base_card(rules, {"service": service})
    entities = [
        expand_template(row, {"service": service})
        for row in rules.get("service_rows", [])
    ]
    for reading in service.readings:
        entities.extend(
            expand_template(row, {"service": service, "reading": reading})
            for row in rules.get("reading_rows", [])
        )

    if entities and entities[-1] == {"type": "divider"}:
        entities.pop()
    card["entities"] = entities
    return card


def alert_memory_card(seed: dict[str, Any], service: ServiceModel) -> dict[str, object]:
    """Return the removable alert-memory card from seed rules."""

    rules = seed["alert_memory_card"]
    card = base_card(rules, {"service": service})
    card["entities"] = [
        expand_template(rules["reading_row"], {"service": service, "reading": reading})
        for reading in service.readings
    ]
    return card


def base_card(rules: dict[str, Any], context: dict[str, object]) -> dict[str, object]:
    """Return card-level seed fields, excluding row templates."""

    skipped = {"service_rows", "reading_rows", "reading_row"}
    return {
        key: expand_template(value, context)
        for key, value in rules.items()
        if key not in skipped
    }

