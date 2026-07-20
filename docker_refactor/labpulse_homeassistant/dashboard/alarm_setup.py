"""Render Alarm Setup navigation and focused alarm-control subviews.

The visible Alarm Setup page contains only global tools, bulk timing, and links.
Each non-empty logical setup receives a hidden three-column subview:

1. measurement launchers and the setup mute;
2. editable alarm settings for expanded measurements; and
3. matching live alarm status.

Dedicated power monitoring uses its own lifecycle subview and never enters an
ordinary setup editor. All cards reference existing helpers; dashboard
presentation does not create a second alarm state. The explicit module name
distinguishes this UI renderer from the operational alarm package generator.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from labpulse_common.config import LabPulseConfig

from ..measurement_catalog import ConfiguredMeasurement, MeasurementCatalog
from ..render_model import RenderModel, ServiceModel, SetupAlarmModel
from ..template_utils import expand_template
from .primitives import (
    Card,
    CardSeed,
    DashboardIndex,
    heading_card,
    require_power,
    vertical_stack,
)


DASHBOARD_URL_PATH = "/labpulse-monitor"
ALARM_SETUP_PATH = "alarm-setup"


def alarm_setup_landing_cards(
    model: RenderModel,
    seed: CardSeed,
) -> list[Card]:
    """Return self-contained masonry blocks for the Alarm Setup landing page."""

    cards = [_notification_controls_card(model, seed)]
    bulk = _bulk_timing_card(model, seed)
    if bulk is not None:
        cards.append(bulk)
    navigation = _alarm_navigation_card(model, seed)
    if navigation is not None:
        cards.append(navigation)
    return cards


def setup_alarm_subviews(
    config: LabPulseConfig,
    catalog: MeasurementCatalog,
    index: DashboardIndex,
    seed: CardSeed,
) -> list[Card]:
    """Return one hidden three-column alarm editor per non-empty setup.

    Setup membership comes from the canonical catalog. Power-owned measurements
    are removed before deciding whether a setup needs a subview.
    """

    views: list[Card] = []
    for setup_id, items in catalog.by_setup.items():
        selected = _ordinary_alarm_measurements(items, index)
        if not selected:
            continue
        setup = config.setups[setup_id]
        views.append(
            {
                "title": setup.display_label(setup_id),
                "path": setup_alarm_path(setup_id),
                "subview": True,
                "back_path": dashboard_view_url(ALARM_SETUP_PATH),
                "type": "sections",
                "max_columns": 3,
                "sections": _alarm_measurement_sections(
                    selected,
                    index,
                    seed,
                    index.setups[setup_id],
                ),
            }
        )
    return views


def power_alarm_subviews(model: RenderModel, seed: CardSeed) -> list[Card]:
    """Return hidden lifecycle-control subviews for dedicated power services."""

    views: list[Card] = []
    for service in model.services:
        if service.power is None:
            continue
        views.append(
            {
                "title": "Power Monitoring",
                "path": power_alarm_path(service.service_id),
                "subview": True,
                "back_path": dashboard_view_url(ALARM_SETUP_PATH),
                "type": "sections",
                "max_columns": 1,
                "sections": [_power_alarm_section(service, seed)],
            }
        )
    return views


def setup_alarm_path(setup_id: str) -> str:
    """Return the stable dashboard path for one setup alarm editor."""

    return f"alarm-setup-{setup_id}"


def power_alarm_path(service_id: str) -> str:
    """Return the stable dashboard path for one power alarm editor."""

    return f"alarm-power-{service_id}"


def dashboard_view_url(view_path: str) -> str:
    """Return an absolute navigation URL inside the generated dashboard."""

    return f"{DASHBOARD_URL_PATH}/{view_path}"


def _notification_controls_card(model: RenderModel, seed: CardSeed) -> Card:
    """Render global notification controls as one indivisible masonry block."""

    return _template_stack(
        seed["global_alarm_setup"],
        ("heading_card", "settings_card", "phone_book_button"),
        {"model": model},
    )


def _bulk_timing_card(model: RenderModel, seed: CardSeed) -> Card | None:
    """Render setup-targeted bulk timing inputs with explicit confirmation."""

    if not model.bulk_timing_targets:
        return None
    return _template_stack(
        seed["bulk_timing"],
        ("heading_card", "settings_card", "apply_button"),
        {"model": model},
    )


def _template_stack(
    rules: dict[str, Any],
    names: tuple[str, ...],
    context: dict[str, object],
) -> Card:
    """Expand ordered template fragments into one vertical masonry block.

    Notification and bulk-timing blocks share this exact construction. Keeping
    the heading in the same stack prevents Home Assistant from separating it
    from controls at narrow widths.
    """

    return vertical_stack(
        [expand_template(rules[name], context) for name in names]
    )


def _alarm_navigation_card(model: RenderModel, seed: CardSeed) -> Card | None:
    """Pair each setup navigation tile with its setup mute control."""

    rows: list[Card] = []
    for setup in model.setups:
        rows.append(
            {
                "type": "grid",
                "columns": 2,
                "square": False,
                "cards": [
                    _navigation_tile(
                        setup.muted_entity,
                        setup.label,
                        setup.icon,
                        setup_alarm_path(setup.setup_id),
                    ),
                    vertical_stack(_setup_mute_cards(setup, seed)),
                ],
            }
        )

    # Power is intentionally appended after logical setup rows because it has
    # no setup mute and opens a different lifecycle editor.
    for service in model.services:
        if service.power is None:
            continue
        rows.append(
            _navigation_tile(
                service.power.entities["state"],
                "Power Monitoring",
                "mdi:battery-charging",
                power_alarm_path(service.service_id),
            )
        )
    if not rows:
        return None
    return vertical_stack(
        [heading_card("Configure Alarms", "mdi:tune-variant", "title")] + rows
    )


def _navigation_tile(
    entity: str,
    name: str,
    icon: str,
    destination_path: str,
) -> Card:
    """Return a state-hidden tile whose body and icon open the same subview."""

    destination = dashboard_view_url(destination_path)
    return {
        "type": "tile",
        "entity": entity,
        "name": name,
        "icon": icon,
        "hide_state": True,
        "tap_action": {"action": "navigate", "navigation_path": destination},
        "icon_tap_action": {
            "action": "navigate",
            "navigation_path": destination,
        },
    }


def _ordinary_alarm_measurements(
    items: Iterable[ConfiguredMeasurement],
    index: DashboardIndex,
) -> tuple[ConfiguredMeasurement, ...]:
    """Exclude power measurements governed by the dedicated power lifecycle."""

    return tuple(
        item for item in items if index.services[item.key.service_name].power is None
    )


def _alarm_measurement_sections(
    items: tuple[ConfiguredMeasurement, ...],
    index: DashboardIndex,
    seed: CardSeed,
    setup: SetupAlarmModel,
) -> list[Card]:
    """Return aligned launcher, settings, and live-status columns."""

    launchers, settings, statuses = _alarm_control_columns(items, index, seed)
    return [
        {
            "type": "grid",
            "cards": [heading_card("Measurements", "mdi:format-list-bulleted", "title")]
            + _setup_mute_cards(setup, seed)
            + [
                {
                    "type": "grid",
                    "columns": 2,
                    "square": False,
                    "grid_options": {"columns": "full"},
                    "cards": launchers,
                }
            ],
        },
        {
            "type": "grid",
            "cards": [heading_card("Alarm Settings", "mdi:tune", "title")]
            + settings,
        },
        {
            "type": "grid",
            "cards": [heading_card("Live Alarm Status", "mdi:pulse", "title")]
            + statuses,
        },
    ]


def _setup_mute_cards(setup: SetupAlarmModel, seed: CardSeed) -> list[Card]:
    """Render a direct mute or the warning-aware shared-measurement pair."""

    rules = seed["alarm_setup_sections"]
    context = {"setup": setup}
    if not setup.shared_measurement_labels:
        return [expand_template(rules["setup_mute_tile"], context)]
    return [
        expand_template(rules["shared_setup_mute_off"], context),
        expand_template(rules["shared_setup_mute_on"], context),
    ]


def _alarm_control_columns(
    items: Iterable[ConfiguredMeasurement],
    index: DashboardIndex,
    seed: CardSeed,
) -> tuple[list[Card], list[Card], list[Card]]:
    """Expand each measurement once into aligned launcher/settings/status lists.

    All three cards reference the same expansion helper. This is why selecting
    one measurement reveals its editable settings and live status together.
    """

    rules = seed["alarm_setup_sections"]
    launchers: list[Card] = []
    settings: list[Card] = []
    statuses: list[Card] = []
    for item in items:
        context = {
            "service": index.services[item.key.service_name],
            "measurement": index.measurements[item.key],
        }
        launchers.append(expand_template(rules["controls_toggle_tile"], context))
        settings.append(expand_template(rules["measurement_settings_card"], context))
        statuses.append(expand_template(rules["measurement_status_card"], context))
    return launchers, settings, statuses


def _power_alarm_section(service: ServiceModel, seed: CardSeed) -> Card:
    """Render dedicated power lifecycle controls for one power service."""

    power = require_power(service, "power alarm section")
    rules = seed["power_alarm_setup"]
    return {
        "type": "grid",
        "cards": [
            heading_card("Power Monitoring", "mdi:battery-charging", "title"),
            heading_card(service.label, "mdi:chip", "subtitle"),
            expand_template(
                rules["settings_card"],
                {"service": service, "power": power},
            ),
        ],
    }
