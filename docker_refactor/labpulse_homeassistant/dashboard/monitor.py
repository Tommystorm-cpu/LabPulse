"""Render the operator-facing Monitor view.

Monitor is the logical projection of LabPulse:

* dedicated power monitoring is kept outside experiment/setup grouping;
* ordinary measurements are projected into their configured logical setups;
* ``subcategory`` creates card boundaries without visible headings;
* shared measurements may be displayed more than once but always reference one
  canonical Home Assistant entity; and
* Active Problems is nested in the first masonry column to avoid page reflow.

Physical service topology does not belong here; it is rendered by
``diagnostics.py``.
"""

from __future__ import annotations

from collections.abc import Iterable

from labpulse_common.config import LabPulseConfig

from ..measurement_catalog import ConfiguredMeasurement, MeasurementCatalog
from ..measurement_model import MeasurementModel
from ..render_model import DEFAULT_RENDER_ENTITIES, ServiceModel
from .primitives import (
    Card,
    DashboardIndex,
    entities_card,
    heading_card,
    require_power,
    vertical_stack,
)


DEFAULT_SUBCATEGORY = "Other Measurements"


def monitor_sections(
    config: LabPulseConfig,
    catalog: MeasurementCatalog,
    index: DashboardIndex,
) -> list[Card]:
    """Return ordered masonry columns for power and configured setups.

    The first real column also owns the conditional Active Problems card. This
    keeps the number and horizontal order of top-level masonry items stable when
    a problem appears or recovers.
    """

    columns: list[Card] = []

    # Create a "setup ID: display label" lookup for shared-measurement labels.
    setup_labels = {
        setup_id: setup.display_label(setup_id)
        for setup_id, setup in config.setups.items()
    }

    # Record power services so their measurements are not shown twice.
    power_service_names = {
        service.name for service in index.services.values() if service.power is not None
    }

    # Give every power service its own leading Monitor column.
    for service in index.services.values():
        if service.power is not None:
            columns.append(_power_monitor_column(service))

    # Build each setup column in the catalogue's configured order.
    for setup_id, items in catalog.by_setup.items():
        setup = config.setups[setup_id]
        ordinary_items = tuple(
            item for item in items if item.key.service_name not in power_service_names
        )
        columns.append(
            _setup_monitor_column(
                setup.display_label(setup_id),
                setup.icon,
                ordinary_items,
                index,
                setup_id,
                setup_labels,
            )
        )

    # Keep global mute and active problems visible without changing masonry order.
    _prepend_monitor_cards(
        columns,
        [
            _global_mute_banner(),
            _test_mode_banner(),
            _monitor_problems_card(catalog, index),
        ],
    )
    return columns


def _prepend_monitor_cards(columns: list[Card], cards: list[Card]) -> None:
    """Nest important status cards without changing the Monitor column count."""

    # Create a first column when the dashboard has no setup or power columns.
    if not columns:
        columns.append(vertical_stack(cards))
        return
    # Insert status cards into the existing first vertical stack.
    first_column_cards = columns[0].get("cards")
    if not isinstance(first_column_cards, list):
        raise ValueError("Monitor masonry columns must contain cards")
    first_column_cards[0:0] = cards


def _global_mute_banner() -> Card:
    """Warn prominently while the global notification mute is active."""

    global_muted = DEFAULT_RENDER_ENTITIES["global_muted"]
    return {
        "type": "conditional",
        "conditions": [
            {"condition": "state", "entity": global_muted, "state": "on"}
        ],
        "card": {
            "type": "markdown",
            "content": (
                "## 🔕 Global Mute Applied\n\n"
                "Alarm states remain visible, but LabPulse notifications are disabled.\n\n"
                "[Review notification controls](/labpulse-monitor/alarm-setup)"
            ),
        },
    }


def _test_mode_banner() -> Card:
    """Warn prominently while notifications use the test recipient list."""

    test_mode = DEFAULT_RENDER_ENTITIES["test_mode"]
    return {
        "type": "conditional",
        "conditions": [
            {"condition": "state", "entity": test_mode, "state": "on"}
        ],
        "card": {
            "type": "markdown",
            "content": (
                "## 🧪 Test Mode Applied\n\n"
                "Notifications are routed only to the configured test recipients.\n\n"
                "[Review notification controls](/labpulse-monitor/alarm-setup)"
            ),
        },
    }


def _monitor_problems_card(
    catalog: MeasurementCatalog,
    index: DashboardIndex,
) -> Card:
    """Return a hidden-when-empty summary of confirmed, unmuted problems.

    Instantaneous zone sensors are intentionally excluded. Measurement rows use the
    persistent alarm state plus individual/setup mute conditions; service and
    power rows use their confirmed lifecycle states. The global notification
    mute never hides operational state.
    """

    entities: list[Card] = []

    # Add each service's confirmed fault state.
    for service in index.services.values():
        entities.append(
            {
                "entity": service.entities["health_fault_active"],
                "name": f"{service.label}: confirmed service fault",
                "icon": "mdi:lan-disconnect",
            }
        )

    # Visit each measurement once even when it belongs to several setups.
    for item in catalog.measurements:
        measurement = index.measurements[item.key]
        service = index.services[item.key.service_name]
        if service.power is not None:
            continue
        entities.append(_measurement_problem_row(measurement))

    # Add each dedicated power lifecycle state.
    for service in index.services.values():
        if service.power is None:
            continue
        entities.append(
            {
                "entity": service.power.entities["state"],
                "name": "Power monitoring: lifecycle state",
                "icon": "mdi:power-plug-off-outline",
            }
        )

    return {
        "type": "entity-filter",
        "entities": entities,
        "conditions": [
            {
                "condition": "or",
                "conditions": [
                    {"condition": "state", "state": "on"},
                    {
                        "condition": "state",
                        "state": ["Danger", "Sensor Fault", "On Battery"],
                    },
                ],
            }
        ],
        "show_empty": False,
        "card": {
            "type": "entities",
            "title": "Active Problems",
            "show_header_toggle": False,
        },
    }


def _measurement_problem_row(measurement: MeasurementModel) -> Card:
    """Return one alarm-state row guarded by individual and setup mutes.

    Keeping this policy in one helper makes the individual/setup mute semantics
    visible and testable without repeating condition dictionaries in the loop.
    """

    # Require the measurement's own mute to be off.
    mute_conditions: list[Card] = [
        {
            "condition": "state",
            "entity": measurement.entities["alarm_muted"],
            "state": "off",
        }
    ]
    # Create one unmuted-state condition for every owning setup.
    setup_conditions = [
        {"condition": "state", "entity": entity, "state": "off"}
        for entity in measurement.setup_muted_entities
    ]

    # Keep shared measurements visible while any owning setup remains unmuted.
    if len(setup_conditions) == 1:
        mute_conditions.extend(setup_conditions)
    elif setup_conditions:
        mute_conditions.append(
            {"condition": "or", "conditions": setup_conditions}
        )

    return {
        "entity": measurement.entities["alarm_state"],
        "name": f"{measurement.label}: alarm state",
        "icon": "mdi:alert-outline",
        "conditions": [
            {"condition": "state", "state": ["Danger", "Sensor Fault"]}
        ]
        + mute_conditions,
    }


def _setup_monitor_column(
    title: str,
    icon: str,
    items: tuple[ConfiguredMeasurement, ...],
    index: DashboardIndex,
    setup_id: str,
    setup_labels: dict[str, str],
) -> Card:
    """Render one logical setup with invisible subcategory card boundaries."""

    # Start the setup column with its heading.
    cards: list[Card] = [heading_card(title, icon, "title")]
    if not items:
        cards.append(
            {
                "type": "markdown",
                "content": "No measurements are currently assigned to this setup.",
            }
        )
        return vertical_stack(cards)

    # Add one entity card for every measurement subcategory.
    for _subcategory, grouped_items in _measurements_by_subcategory(items):
        cards.append(
            _measurements_card(grouped_items, index, setup_id, setup_labels)
        )
    return vertical_stack(cards)


def _measurements_card(
    items: tuple[ConfiguredMeasurement, ...],
    index: DashboardIndex,
    setup_id: str,
    setup_labels: dict[str, str],
) -> Card:
    """Return one entity box for a subcategory without exposing its label."""

    # Resolve each catalogue record to its MQTT entity and display label.
    return entities_card(
        [
            {
                "entity": index.measurements[item.key].mqtt_entity.entity_id,
                "name": _monitor_measurement_label(
                    item, index, setup_id, setup_labels
                ),
            }
            for item in items
        ]
    )


def _power_monitor_column(service: ServiceModel) -> Card:
    """Return the dedicated operator-facing UPS summary column."""

    # Get the power model before constructing the UPS summary.
    power = require_power(service, "power Monitor column")
    return vertical_stack(
        [
            heading_card("UPS Power", "mdi:battery-charging", "title"),
            {
                "type": "tile",
                "entity": service.status_entity.entity_id,
                "name": f"{service.label} Status",
            },
            {
                "type": "gauge",
                "entity": power.battery_level.mqtt_entity.entity_id,
                "name": power.battery_level.label,
                "min": 0,
                "max": 100,
                "severity": {"red": 0, "yellow": 25, "green": 50},
            },
            entities_card(
                [
                    {"entity": power.entities["state"], "name": "Power state"},
                    {
                        "entity": power.entities["mains_present"],
                        "name": "External power present",
                    },
                    {
                        "entity": power.voltage.mqtt_entity.entity_id,
                        "name": power.voltage.label,
                    },
                    {
                        "entity": power.entities["last_outage_started_sensor"],
                        "name": "Last outage started",
                    },
                    {
                        "entity": power.entities["last_outage_duration_sensor"],
                        "name": "Last outage duration",
                    },
                ]
            ),
        ]
    )


def _measurements_by_subcategory(
    items: Iterable[ConfiguredMeasurement],
) -> list[tuple[str, tuple[ConfiguredMeasurement, ...]]]:
    """Group measurements by subcategory in first-seen configuration order."""

    # Group measurements without changing their first-seen order.
    grouped: dict[str, list[ConfiguredMeasurement]] = {}
    for item in items:
        subcategory = item.measurement.subcategory or DEFAULT_SUBCATEGORY
        grouped.setdefault(subcategory, []).append(item)
    return [(name, tuple(measurements)) for name, measurements in grouped.items()]


def _monitor_measurement_label(
    item: ConfiguredMeasurement,
    index: DashboardIndex,
    setup_id: str,
    setup_labels: dict[str, str],
) -> str:
    """Add cross-setup context without changing the referenced entity."""

    # Return the normal label when the measurement is not shared.
    label = index.measurements[item.key].label
    if item.measurement.setups is None or len(item.effective_setup_ids) <= 1:
        return label
    # Append the labels of every other setup using this measurement.
    other_ids = tuple(
        candidate for candidate in item.effective_setup_ids if candidate != setup_id
    )
    other_labels = tuple(setup_labels[candidate] for candidate in other_ids)
    return f"{label} (Shared with {', '.join(other_labels)})"
