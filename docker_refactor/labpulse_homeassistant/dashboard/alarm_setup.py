"""Render the native Sections-based Alarm Setup dashboard and subviews."""

from __future__ import annotations

from labpulse_common.config import LabPulseConfig

from ..measurement_catalog import ConfiguredMeasurement, MeasurementCatalog
from ..measurement_model import MeasurementModel
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
DESKTOP_MEDIA_QUERY = "(min-width: 900px)"
MOBILE_MEDIA_QUERY = "(max-width: 899px)"


def alarm_setup_landing_sections(
    model: RenderModel,
    seed: CardSeed,
) -> list[Card]:
    """Return notification, group-setting, and setup-navigation sections."""

    # Keep the common setup links visible before the optional group editor.
    sections: list[Card] = []
    navigation = _alarm_navigation_section(model, seed)
    if navigation is not None:
        sections.append(navigation)
    sections.append(_notification_controls_section(model, seed))
    bulk = _group_alarm_settings_section(model)
    if bulk is not None:
        sections.append(bulk)
    return sections


def setup_alarm_subviews(
    config: LabPulseConfig,
    catalog: MeasurementCatalog,
    index: DashboardIndex,
    seed: CardSeed,
) -> list[Card]:
    """Return one hidden row-based alarm editor per non-empty setup.

    Setup membership comes from the canonical catalog. Power-owned measurements
    are removed before deciding whether a setup needs a subview.
    """

    # Build one hidden editor for each setup containing ordinary measurements.
    views: list[Card] = []
    for setup_id, items in catalog.by_setup.items():
        # Remove measurements handled by the dedicated power lifecycle.
        selected = _ordinary_alarm_measurements(items, index)
        if not selected:
            continue
        # Get this setup's labels and presentation settings.
        setup = config.setups[setup_id]
        views.append(
            {
                "title": setup.display_label(setup_id),
                "path": setup_alarm_path(setup_id),
                "subview": True,
                "back_path": dashboard_view_url(ALARM_SETUP_PATH),
                "type": "sections",
                "max_columns": 3,
                "dense_section_placement": False,
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

    # Build one hidden lifecycle editor for each power service.
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


def _notification_controls_section(model: RenderModel, seed: CardSeed) -> Card:
    """Render the global delivery controls in the left landing section."""

    rules = seed["global_alarm_setup"]
    context = {"model": model}
    return {
        "type": "grid",
        "column_span": 1,
        "cards": [
            expand_template(rules[name], context)
            for name in ("heading_card", "settings_card", "phone_book_button")
        ],
    }


def _group_alarm_settings_section(model: RenderModel) -> Card | None:
    """Render selective common and typed-deadband bulk controls."""

    if not model.bulk_alarm_targets:
        return None
    editor_cards: list[Card] = [
        {
            "type": "markdown",
            "content": (
                "Choose where the changes should go, then switch on only the "
                "settings you want to replace. Review the result before applying."
            ),
            "grid_options": {"columns": "full"},
        },
        {
            "type": "entities",
            "title": "1. Choose target",
            "show_header_toggle": False,
            "grid_options": {"columns": "full"},
            "entities": [
                {
                    "entity": model.entities["bulk_timing_target"],
                    "name": "Apply changes to",
                },
                {
                    "entity": model.entities["bulk_target_count"],
                    "name": "Measurements affected",
                },
            ],
        },
        {
            "type": "entities",
            "title": "2. Choose settings and values",
            "show_header_toggle": False,
            "grid_options": {"columns": "full"},
            "entities": [
                {
                    "type": "section",
                    "label": "Only switched-on settings will be applied",
                },
                {
                    "entity": model.entities[
                        "bulk_apply_required_danger_percent"
                    ],
                    "name": "Change required danger",
                },
                _conditional_value_row(
                    model.entities["bulk_apply_required_danger_percent"],
                    model.entities["bulk_required_danger_percent"],
                    "New required danger",
                ),
                {
                    "entity": model.entities[
                        "bulk_apply_observation_window_seconds"
                    ],
                    "name": "Change observation window",
                },
                _conditional_value_row(
                    model.entities["bulk_apply_observation_window_seconds"],
                    model.entities["bulk_observation_window_seconds"],
                    "New observation window",
                ),
                {
                    "entity": model.entities[
                        "bulk_apply_required_recovery_seconds"
                    ],
                    "name": "Change required recovery",
                },
                _conditional_value_row(
                    model.entities["bulk_apply_required_recovery_seconds"],
                    model.entities["bulk_required_recovery_seconds"],
                    "New required recovery",
                ),
            ],
        },
    ]
    # Show only deadband families present in the currently selected target.
    for target in model.bulk_alarm_targets:
        deadband_rows: list[Card] = [
            {
                "type": "section",
                "label": "Deadbands available for this target",
            }
        ]
        for group in target.deadband_groups:
            count = len(group.measurement_keys)
            noun = "measurement" if count == 1 else "measurements"
            unit = f" ({group.unit})" if group.unit else ""
            deadband_rows.extend(
                [
                    {
                        "entity": group.apply_entity,
                        "name": (
                            f"Change {group.label.lower()} deadband "
                            f"({count} {noun})"
                        ),
                    },
                    _conditional_value_row(
                        group.apply_entity,
                        group.value_entity,
                        f"New {group.label.lower()} deadband{unit}",
                    ),
                ]
            )
        editor_cards.append(
            {
                "type": "conditional",
                "conditions": [
                    {
                        "entity": model.entities["bulk_timing_target"],
                        "state": target.option,
                    }
                ],
                "grid_options": {"columns": "full"},
                "card": {
                    "type": "entities",
                    "show_header_toggle": False,
                    "entities": deadband_rows,
                },
            }
        )
    editor_cards.extend(_bulk_review_and_apply_cards(model))
    expanded_entity = model.entities["bulk_editor_expanded"]
    return {
        "type": "grid",
        "column_span": 2,
        "cards": [
            heading_card("Group Alarm Settings", "mdi:tune-vertical", "title"),
            _bulk_editor_toggle(expanded_entity, expanded=False),
            _bulk_editor_toggle(expanded_entity, expanded=True),
            {
                "type": "conditional",
                "conditions": [{"entity": expanded_entity, "state": "on"}],
                "grid_options": {"columns": "full"},
                "card": vertical_stack(editor_cards),
            },
        ],
    }


def _bulk_editor_toggle(entity: str, *, expanded: bool) -> Card:
    """Return the native Open or Close control for the group editor."""

    visible_state = "on" if expanded else "off"
    service = "input_boolean.turn_off" if expanded else "input_boolean.turn_on"
    return {
        "type": "conditional",
        "conditions": [{"entity": entity, "state": visible_state}],
        "grid_options": {"columns": "full"},
        "card": {
            "type": "tile",
            "entity": entity,
            "name": (
                "Close group alarm settings"
                if expanded
                else "Configure group alarm settings"
            ),
            "icon": "mdi:close" if expanded else "mdi:tune-variant",
            "hide_state": True,
            "tap_action": {
                "action": "perform-action",
                "perform_action": service,
                "target": {"entity_id": entity},
            },
            "icon_tap_action": {"action": "none"},
        },
    }


def _conditional_value_row(
    apply_entity: str, value_entity: str, name: str
) -> Card:
    """Show one bulk value row only while its apply switch is on."""

    return {
        "type": "conditional",
        "conditions": [{"entity": apply_entity, "state": "on"}],
        "row": {"entity": value_entity, "name": name},
    }


def _bulk_review_and_apply_cards(model: RenderModel) -> list[Card]:
    """Return the exact native Markdown review and conditional Apply controls."""

    target_entity = model.entities["bulk_timing_target"]
    count_entity = model.entities["bulk_target_count"]
    lines = [
        "## 3. Review changes",
        f"{{% set target = states('{target_entity}') %}}",
        f"**Target:** {{{{ target }}}} ({{{{ states('{count_entity}') }}}} measurements)",
        "",
        (
            "{% if is_state('"
            + model.entities["bulk_apply_required_danger_percent"]
            + "', 'on') %}- Required danger: **{{ states('"
            + model.entities["bulk_required_danger_percent"]
            + "') }}%** → {{ states('"
            + count_entity
            + "') }} measurements{% endif %}"
        ),
        (
            "{% if is_state('"
            + model.entities["bulk_apply_observation_window_seconds"]
            + "', 'on') %}- Observation window: **{{ states('"
            + model.entities["bulk_observation_window_seconds"]
            + "') }} s** → {{ states('"
            + count_entity
            + "') }} measurements{% endif %}"
        ),
        (
            "{% if is_state('"
            + model.entities["bulk_apply_required_recovery_seconds"]
            + "', 'on') %}- Required recovery: **{{ states('"
            + model.entities["bulk_required_recovery_seconds"]
            + "') }} s** → {{ states('"
            + count_entity
            + "') }} measurements{% endif %}"
        ),
    ]
    for target in model.bulk_alarm_targets:
        for group in target.deadband_groups:
            unit = f" {group.unit}" if group.unit else ""
            lines.append(
                "{% if target == "
                + repr(target.option)
                + " and is_state('"
                + group.apply_entity
                + "', 'on') %}- "
                + group.label
                + " deadband: **{{ states('"
                + group.value_entity
                + "') }}"
                + unit
                + "** → "
                + str(len(group.measurement_keys))
                + " measurements{% endif %}"
            )
    lines.extend(
        [
            "{% if is_state('"
            + model.entities["bulk_changes_selected"]
            + "', 'off') %}",
            "**Nothing will be changed.**",
            "{% endif %}",
        ]
    )
    return [
        {
            "type": "markdown",
            "content": "\n".join(lines),
            "grid_options": {"columns": "full"},
        },
        {
            "type": "conditional",
            "conditions": [
                {"entity": model.entities["bulk_changes_selected"], "state": "off"}
            ],
            "grid_options": {"columns": "full"},
            "card": _read_only_tile(
                model.entities["bulk_changes_selected"],
                "Apply unavailable — select at least one change",
                "mdi:checkbox-blank-off-outline",
                "full",
            ),
        },
        {
            "type": "conditional",
            "conditions": [
                {"entity": model.entities["bulk_changes_selected"], "state": "on"}
            ],
            "grid_options": {"columns": "full"},
            "card": {
                "type": "tile",
                "entity": model.entities["bulk_apply_settings_script"],
                "name": "4. Apply selected changes",
                "icon": "mdi:check-bold",
                "hide_state": True,
                "tap_action": {
                    "action": "perform-action",
                    "perform_action": model.entities["bulk_apply_settings_script"],
                    "confirmation": {
                        "text": "Apply exactly the changes shown in the review above?"
                    },
                },
                "icon_tap_action": {"action": "none"},
            },
        },
    ]


def _alarm_navigation_section(model: RenderModel, seed: CardSeed) -> Card | None:
    """Render one native setup row per active logical setup."""

    # Pair every setup link with its notification-mute controls.
    rows: list[Card] = []
    for setup in model.setups:
        summary = _read_only_tile(
            setup.muted_entity,
            f"{setup.label} — {setup.measurement_count} measurements",
            setup.icon,
            4,
        )
        # Hide the raw muted flag because "off" actually means notifications are on.
        summary["hide_state"] = True
        rows.append(
            {
                "type": "grid",
                "columns": 3,
                "square": False,
                "grid_options": {"columns": "full"},
                "cards": [
                    summary,
                    vertical_stack(_setup_mute_cards(setup, seed)),
                    _navigation_tile(
                        setup.muted_entity,
                        "Configure",
                        "mdi:tune-variant",
                        setup_alarm_path(setup.setup_id),
                    ),
                ],
            }
        )

    # Append power after the logical setup rows because it has no setup mute.
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
    # Omit the navigation block when no setup or power editors exist.
    if not rows:
        return None
    return {
        "type": "grid",
        "column_span": 3,
        "cards": [heading_card("Configure Alarms", "mdi:tune-variant", "title")]
        + rows,
    }


def _navigation_tile(
    entity: str,
    name: str,
    icon: str,
    destination_path: str,
) -> Card:
    """Return a state-hidden tile whose body and icon open the same subview."""

    # Use the same absolute destination for body and icon actions.
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
    items: tuple[ConfiguredMeasurement, ...],
    index: DashboardIndex,
) -> tuple[ConfiguredMeasurement, ...]:
    """Exclude power measurements governed by the dedicated power lifecycle."""

    # Keep only measurements governed by the ordinary threshold alarm system.
    return tuple(
        item for item in items if index.services[item.key.service_name].power is None
    )


def _alarm_measurement_sections(
    items: tuple[ConfiguredMeasurement, ...],
    index: DashboardIndex,
    seed: CardSeed,
    setup: SetupAlarmModel,
) -> list[Card]:
    """Return a setup header followed by one native row section per measurement."""

    sections: list[Card] = [
        _setup_header_section(setup, seed, mobile=False),
        _setup_header_section(setup, seed, mobile=True),
    ]
    for item in items:
        measurement = index.measurements[item.key]
        sections.extend(
            [
                _measurement_row_section(measurement, seed, mobile=False),
                _measurement_row_section(measurement, seed, mobile=True),
            ]
        )
    return sections


def _setup_header_section(
    setup: SetupAlarmModel, seed: CardSeed, *, mobile: bool
) -> Card:
    """Render the setup name, positive notification state, and mute action."""

    columns: int | str = "full" if mobile else 12
    heading = heading_card(setup.label, setup.icon, "title")
    heading["grid_options"] = {"columns": columns}
    return {
        "type": "grid",
        "column_span": 3,
        "visibility": [_screen_condition(mobile)],
        "cards": [
            heading,
            *_setup_notification_status_cards(setup, columns),
            *_setup_header_mute_cards(setup, seed, columns),
        ],
    }


def _setup_notification_status_cards(
    setup: SetupAlarmModel, columns: int | str
) -> list[Card]:
    """Describe notification state positively instead of exposing a mute flag."""

    cards: list[Card] = []
    for muted, name, icon in (
        (False, "Notifications active", "mdi:bell-ring-outline"),
        (True, "Notifications muted", "mdi:bell-off-outline"),
    ):
        cards.append(
            {
                "type": "conditional",
                "conditions": [
                    {
                        "entity": setup.muted_entity,
                        "state": "on" if muted else "off",
                    }
                ],
                "grid_options": {"columns": columns},
                "card": {
                    "type": "tile",
                    "entity": setup.muted_entity,
                    "name": name,
                    "icon": icon,
                    "hide_state": True,
                    "tap_action": {"action": "none"},
                    "hold_action": {"action": "none"},
                    "double_tap_action": {"action": "none"},
                    "icon_tap_action": {"action": "none"},
                },
            }
        )
    return cards


def _setup_mute_cards(setup: SetupAlarmModel, seed: CardSeed) -> list[Card]:
    """Render a direct mute or the warning-aware shared-measurement pair."""

    # Select the direct or warning-aware mute controls for this setup.
    rules = seed["alarm_setup_sections"]
    context = {"setup": setup}
    if not setup.shared_measurement_labels:
        return [
            expand_template(rules["setup_mute_off"], context),
            expand_template(rules["setup_mute_on"], context),
        ]
    return [
        expand_template(rules["shared_setup_mute_off"], context),
        expand_template(rules["shared_setup_mute_on"], context),
    ]


def _setup_header_mute_cards(
    setup: SetupAlarmModel,
    seed: CardSeed,
    columns: int | str,
) -> list[Card]:
    """Size setup mute actions for the active responsive header."""

    cards = _setup_mute_cards(setup, seed)
    for card in cards:
        card["grid_options"] = {"columns": columns}
    return cards


def _measurement_row_section(
    measurement: MeasurementModel, seed: CardSeed, *, mobile: bool
) -> Card:
    """Render one explicitly sized desktop or mobile measurement row."""

    rules = seed["alarm_setup_sections"]
    context = {"measurement": measurement}
    names = (
        "measurement_tile",
        "alarm_state_tile",
        "minimum_tile",
        "maximum_tile",
        "measurement_mute_off",
        "measurement_mute_on",
        "configure_closed_tile",
        "configure_open_tile",
    )
    cards = [expand_template(rules[name], context) for name in names]
    columns: tuple[int | str, ...] = (
        ("full", "full", 4, 4, 4, 4, "full", "full")
        if mobile
        else (6, 6, 6, 6, 6, 6, 6, 6)
    )
    for card, width in zip(cards, columns, strict=True):
        card["grid_options"] = {"columns": width}
    cards.append(_measurement_editor_card(measurement, mobile=mobile))
    return {
        "type": "grid",
        "column_span": 3,
        "visibility": [_screen_condition(mobile)],
        "cards": cards,
    }


def _measurement_editor_card(
    measurement: MeasurementModel, *, mobile: bool
) -> Card:
    """Return the two-part alarm form and compact live status block."""

    behavior = {
        "type": "entities",
        "title": f"{measurement.label}: Alarm behaviour",
        "show_header_toggle": False,
        "entities": [
            {"entity": measurement.entities["alarm_mode"], "name": "Alarm mode"},
            {
                "entity": measurement.entities["alarm_muted"],
                "name": "Measurement notifications muted",
            },
            {
                "entity": measurement.entities["minimum_threshold"],
                "name": "Minimum threshold",
            },
            {
                "entity": measurement.entities["maximum_threshold"],
                "name": "Maximum threshold",
            },
            {
                "entity": measurement.entities["recovery_deadband"],
                "name": "Recovery deadband",
            },
        ],
    }
    timing = {
        "type": "entities",
        "title": "Confirmation timing",
        "show_header_toggle": False,
        "entities": [
            {
                "entity": measurement.entities["required_danger_percent"],
                "name": "Required danger",
            },
            {
                "entity": measurement.entities["observation_window_seconds"],
                "name": "Observation window",
            },
            {
                "entity": measurement.entities["required_recovery_seconds"],
                "name": "Required recovery",
            },
        ],
    }
    status = {
        "type": "entities",
        "title": "Live status",
        "show_header_toggle": False,
        "entities": [
            {"entity": measurement.mqtt_entity.entity_id, "name": "Current value"},
            {"entity": measurement.entities["alarm_state"], "name": "Alarm state"},
            {
                "entity": measurement.entities["observed_danger_percent"],
                "name": "Observed danger",
            },
            {"entity": measurement.entities["danger_zone"], "name": "Danger zone"},
            {
                "entity": measurement.entities["recovery_zone"],
                "name": "Recovery zone",
            },
            {
                "entity": measurement.entities["sensor_fault_zone"],
                "name": "Sensor fault",
            },
            {
                "type": "button",
                "entity": measurement.entities["alarm_controls_expanded"],
                "name": "Close editor",
                "icon": "mdi:close",
                "action_name": "Close",
                "tap_action": {
                    "action": "perform-action",
                    "perform_action": "input_boolean.turn_off",
                    "target": {
                        "entity_id": measurement.entities[
                            "alarm_controls_expanded"
                        ]
                    },
                },
            },
        ],
    }
    form: Card = (
        vertical_stack([behavior, timing, status])
        if mobile
        else vertical_stack(
            [
                {
                    "type": "grid",
                    "columns": 2,
                    "square": False,
                    "cards": [behavior, timing],
                },
                status,
            ]
        )
    )
    return {
        "type": "conditional",
        "conditions": [
            {
                "entity": measurement.entities["alarm_controls_expanded"],
                "state": "on",
            }
        ],
        "grid_options": {"columns": "full"},
        "card": form,
    }


def _screen_condition(mobile: bool) -> Card:
    """Return the native screen condition for one responsive projection."""

    return {
        "condition": "screen",
        "media_query": MOBILE_MEDIA_QUERY if mobile else DESKTOP_MEDIA_QUERY,
    }


def _read_only_tile(
    entity: str, name: str, icon: str, columns: int | str
) -> Card:
    """Return a state tile whose body and icon cannot open or edit anything."""

    return {
        "type": "tile",
        "entity": entity,
        "name": name,
        "icon": icon,
        "grid_options": {"columns": columns},
        "tap_action": {"action": "none"},
        "hold_action": {"action": "none"},
        "double_tap_action": {"action": "none"},
        "icon_tap_action": {"action": "none"},
    }


def _power_alarm_section(service: ServiceModel, seed: CardSeed) -> Card:
    """Render dedicated power lifecycle controls for one power service."""

    # Get the power model and expand its dedicated settings card.
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
