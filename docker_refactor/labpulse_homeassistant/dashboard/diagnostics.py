"""Render the physical-service diagnostics view.

The Monitor and Alarm Setup views organise measurements by logical setup.  This
view deliberately answers a different question: *which physical hub should I
inspect?*  Every service therefore remains a self-contained native section
containing connection state, health signals, and its latest raw measurements.
"""

from __future__ import annotations

from ..measurement_catalog import ConfiguredMeasurement, MeasurementCatalog
from ..render_model import RenderModel, ServiceModel
from .primitives import (
    Card,
    DashboardIndex,
    entities_card,
    heading_card,
    require_power,
)


def diagnostics_sections(
    catalog: MeasurementCatalog,
    model: RenderModel,
    index: DashboardIndex,
) -> list[Card]:
    """Return one responsive section per physical sensor service."""

    # Construct one diagnostics column for every enabled physical service.
    return [
        _service_diagnostics_section(
            service,
            catalog.by_service[service.name],
            index,
        )
        for service in model.services
    ]


def _service_diagnostics_section(
    service: ServiceModel,
    items: tuple[ConfiguredMeasurement, ...],
    index: DashboardIndex,
) -> Card:
    """Render connection, health, and current values in one native section."""

    # Start with connection, health, and raw measurement cards.
    cards: list[Card] = [
        heading_card(service.label, "mdi:chip", "title"),
        {
            "type": "tile",
            "entity": service.status_entity.entity_id,
            "name": "Connection",
            "icon": "mdi:lan-connect",
        },
        {
            "type": "grid",
            "columns": 2,
            "square": False,
            "cards": [
                {
                    "type": "tile",
                    "entity": service.entities["health_unhealthy"],
                    "name": "Service Health",
                    "icon": "mdi:heart-pulse",
                },
                {
                    "type": "tile",
                    "entity": service.entities["health_fault_active"],
                    "name": "Confirmed service fault",
                    "icon": "mdi:alert-circle-outline",
                },
            ],
        },
        entities_card(
            [
                {
                    "entity": index.measurements[item.key].mqtt_entity.entity_id,
                    "name": index.measurements[item.key].label,
                }
                for item in items
            ],
            title="Latest measurements",
        ),
    ]

    # Add lifecycle diagnostics only for the dedicated power service.
    if service.power is not None:
        cards.append(_power_diagnostics_card(service))
    return {"type": "grid", "column_span": 1, "cards": cards}


def _power_diagnostics_card(service: ServiceModel) -> Card:
    """Return derived power lifecycle state without repeating raw measurements."""

    # Get the validated power model before constructing lifecycle rows.
    power = require_power(service, "power diagnostics")
    return entities_card(
        [
            {"entity": power.entities["state"], "name": "Power state"},
            {
                "entity": power.entities["mains_present"],
                "name": "External power present",
            },
            {
                "entity": power.entities["sensor_fault"],
                "name": "Power sensor fault",
            },
            {"entity": power.entities["outage_active"], "name": "Outage active"},
            {
                "entity": power.entities["last_outage_started_sensor"],
                "name": "Last outage started",
            },
            {
                "entity": power.entities["last_outage_duration_sensor"],
                "name": "Last outage duration",
            },
        ],
        title="Power Lifecycle",
    )
