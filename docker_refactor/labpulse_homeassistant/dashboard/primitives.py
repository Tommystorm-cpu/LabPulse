"""Shared data types, lookups, and native-card constructors for dashboards.

This module contains the deliberately small vocabulary shared by multiple
page renderers. View-specific policy remains in ``monitor``, ``alarm_setup``,
or ``diagnostics`` so this does not become a generic dashboard junk drawer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..measurement_catalog import MeasurementKey
from ..measurement_model import MeasurementModel
from ..render_model import PowerModel, RenderModel, ServiceModel, SetupAlarmModel


TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "dashboard"

# Lovelace cards stay as plain data until the outer writer serializes them.
# These aliases keep signatures readable without trying to model Home
# Assistant's large and evolving card schema.
Card = dict[str, object]
CardSeed = dict[str, Any]


@dataclass(frozen=True)
class DashboardIndex:
    """Bridge canonical catalog keys to Home Assistant render models.

    Catalog objects describe physical and logical relationships. Render
    models carry entity IDs. One shared index prevents each page from
    rebuilding nested lookup loops or deriving a second physical identity.
    """

    services: dict[str, ServiceModel]
    measurements: dict[MeasurementKey, MeasurementModel]
    setups: dict[str, SetupAlarmModel]

    @classmethod
    def from_model(
        cls: type[DashboardIndex], model: RenderModel
    ) -> DashboardIndex:
        """Build deterministic service, measurement, and setup lookup tables."""

        services = {service.name: service for service in model.services}
        measurements = {
            MeasurementKey(service.name, measurement.name): measurement
            for service in model.services
            for measurement in service.measurements
        }
        setups = {setup.setup_id: setup for setup in model.setups}
        return cls(services=services, measurements=measurements, setups=setups)


def load_card_seed() -> CardSeed:
    """Load reusable alarm-card fragments from the dashboard YAML template."""

    return yaml.safe_load((TEMPLATE_DIR / "cards.yaml").read_text(encoding="utf-8"))


def heading_card(title: str, icon: str, style: str) -> Card:
    """Return a native heading card with the project's consistent key order."""

    return {
        "type": "heading",
        "heading": title,
        "heading_style": style,
        "icon": icon,
    }


def entities_card(entities: list[Card], title: str | None = None) -> Card:
    """Return a non-toggleable entities card, optionally with a title."""

    if title is not None:
        return {
            "type": "entities",
            "title": title,
            "show_header_toggle": False,
            "entities": entities,
        }
    return {
        "type": "entities",
        "show_header_toggle": False,
        "entities": entities,
    }


def vertical_stack(cards: list[Card]) -> Card:
    """Keep one conceptual dashboard block together in a masonry column."""

    return {"type": "vertical-stack", "cards": cards}


def require_power(service: ServiceModel, purpose: str) -> PowerModel:
    """Return a service's power model or reject an invalid renderer call."""

    if service.power is None:
        raise ValueError(f"{purpose} requires a power service")
    return service.power
