"""Focused contracts for the generated Home Assistant YAML dashboard."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Callable
from uuid import uuid4

import yaml


REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_homeassistant.cli import main as generate_homeassistant
from labpulse_homeassistant.paths import GeneratorPaths


SIM_CONFIG = REFACTOR_DIR / "testing" / "ups_test_pi_config.yaml"


def dashboard_config() -> dict[str, object]:
    """Return a two-hub config covering every setup-membership projection."""

    return {
        "mqtt": {"broker": "mosquitto"},
        "setups": {
            "room_conditions": {"label": "Room Conditions", "order": 5},
            "beta_setup": {"label": "Beta Setup", "order": 20},
            "alpha_setup": {"label": "Alpha Setup", "order": 10},
            "empty_setup": {"label": "Empty Setup", "order": 30},
        },
        "services": {
            "hub_a": {
                "driver": "serial",
                "parser": "water",
                "serial_port": "/tmp/hub-a",
                "device_name": "Hub A",
                "measurements": [
                    {
                        "name": "alpha_general",
                        "label": "General",
                        "setups": ["alpha_setup"],
                        "unit": "bar",
                        "device_class": "pressure",
                    },
                    {
                        "name": "alpha_only",
                        "label": "Alpha Only",
                        "subcategory": "Cooling Water",
                        "setups": ["alpha_setup"],
                        "unit": "°C",
                        "device_class": "temperature",
                    },
                    {
                        "name": "shared",
                        "label": "Shared Supply",
                        "subcategory": "Cooling Water",
                        "setups": ["beta_setup", "alpha_setup"],
                        "unit": "°C",
                        "device_class": "temperature",
                    },
                    {
                        "name": "beta_only",
                        "label": "Beta Only",
                        "subcategory": "Vacuum",
                        "setups": ["beta_setup"],
                        "unit": "%",
                        "device_class": "humidity",
                    },
                    {
                        "name": "global_room",
                        "label": "Room Temperature",
                        "subcategory": "Ambient Sensors",
                        "setups": ["room_conditions"],
                        "unit": "°C",
                        "device_class": "temperature",
                    },
                ],
            },
            "hub_b": {
                "driver": "gpio",
                "gpio_sensor": "dht11",
                "gpio_pin": "D4",
                "device_name": "Hub B",
                "measurements": [
                    {
                        "name": "alpha_other_hub",
                        "label": "Alpha From Hub B",
                        "subcategory": "Cooling Water",
                        "setups": ["alpha_setup"],
                        "unit": "°F",
                        "device_class": "temperature",
                    }
                ],
            },
            "disabled_hub": {
                "enabled": False,
                "driver": "serial",
                "parser": "pressure",
                "serial_port": "/tmp/disabled",
                "device_name": "Disabled Hub",
                "measurements": [{"name": "ignored", "setups": ["alpha_setup"]}],
            },
        },
    }


def generate(
    config: dict[str, object] | None = None,
    config_path: Path | None = None,
) -> tuple[GeneratorPaths, dict[str, object], str]:
    """Run normal offline generation and return parsed dashboard output."""

    temp = REFACTOR_DIR / "testing" / "tmp" / f"yaml-dashboard-{uuid4().hex}"
    temp.mkdir(parents=True)
    selected_config = config or dashboard_config()
    selected_path = config_path or (temp / "config.yaml")
    if config_path is None:
        selected_path.write_text(
            yaml.safe_dump(selected_config, sort_keys=False), encoding="utf-8"
        )
    else:
        selected_path = temp / "config.yaml"
        selected_path.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")

    ha_dir = temp / "homeassistant" / "config"
    storage = ha_dir / ".storage"
    storage.mkdir(parents=True)
    sentinel = storage / "lovelace"
    sentinel.write_text('{"user_owned": true}\n', encoding="utf-8")
    registry = storage / "lovelace_dashboards"
    registry.write_text('{"registry_owned": true}\n', encoding="utf-8")

    result = generate_homeassistant(
        ["generator", str(selected_path), str(ha_dir)]
    )
    if result != 0:
        raise AssertionError(f"generator returned {result}")
    if sentinel.read_text(encoding="utf-8") != '{"user_owned": true}\n':
        raise AssertionError("normal generation modified the storage dashboard")
    if registry.read_text(encoding="utf-8") != '{"registry_owned": true}\n':
        raise AssertionError("normal generation modified the dashboard registry")

    paths = GeneratorPaths(config_path=selected_path, ha_config_dir=ha_dir)
    text = paths.dashboard_path.read_text(encoding="utf-8")
    return paths, yaml.safe_load(text), text


def headings(view: dict[str, object], style: str = "title") -> list[str]:
    """Return ordered heading text from one dashboard view."""

    containers = view.get("sections", view.get("cards", []))
    return [
        card["heading"]
        for container in containers
        for card in container.get("cards", [])
        if card.get("type") == "heading" and card.get("heading_style") == style
    ]


def entity_occurrences(value: object, entity_id: str) -> int:
    """Count exact entity-ID values recursively in a dashboard fragment."""

    if isinstance(value, dict):
        return sum(entity_occurrences(child, entity_id) for child in value.values())
    if isinstance(value, list):
        return sum(entity_occurrences(child, entity_id) for child in value)
    return int(value == entity_id)


def walk_dashboard(value: object):
    """Yield every nested dashboard value for focused action assertions."""

    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk_dashboard(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dashboard(child)


def card_types(value: object) -> set[str]:
    """Collect every native card or row type in a dashboard document."""

    result: set[str] = set()
    if isinstance(value, dict):
        card_type = value.get("type")
        if isinstance(card_type, str):
            result.add(card_type)
        for child in value.values():
            result.update(card_types(child))
    elif isinstance(value, list):
        for child in value:
            result.update(card_types(child))
    return result


def view_by_path(dashboard: dict[str, object], path: str) -> dict[str, object]:
    """Return one generated dashboard view by its stable path."""

    return next(view for view in dashboard["views"] if view.get("path") == path)


def test_plain_yaml_and_registration() -> None:
    """Generate a warned plain Lovelace document registered in YAML mode."""

    paths, dashboard, text = generate()
    if not text.startswith("# GENERATED BY LABPULSE."):
        raise AssertionError("generated dashboard warning is missing")
    if any(key in dashboard for key in ("version", "minor_version", "key", "data")):
        raise AssertionError("storage wrapper keys remain in the YAML dashboard")
    visible_views = [view for view in dashboard["views"] if not view.get("subview")]
    if [view["title"] for view in visible_views] != [
        "Monitor",
        "Alarm Setup",
        "Diagnostics",
    ]:
        raise AssertionError("visible dashboard view order is incorrect")
    subviews = [view for view in dashboard["views"] if view.get("subview")]
    if [view["path"] for view in subviews] != [
        "alarm-setup-room_conditions",
        "alarm-setup-alpha_setup",
        "alarm-setup-beta_setup",
    ]:
        raise AssertionError("setup alarm subview order is incorrect")
    if any(view.get("back_path") != "/labpulse-monitor/alarm-setup" for view in subviews):
        raise AssertionError("an alarm subview does not return to Alarm Setup")
    configuration = paths.configuration_path.read_text(encoding="utf-8")
    for fragment in (
        "labpulse-monitor:",
        "mode: yaml",
        "filename: labpulse-dashboard.yaml",
        "title: LabPulse",
        "icon: mdi:flask-outline",
        "show_in_sidebar: true",
    ):
        if fragment not in configuration:
            raise AssertionError(f"dashboard registration is missing: {fragment}")
    allowed = {
        "sections",
        "grid",
        "heading",
        "markdown",
        "entities",
        "entity-filter",
        "tile",
        "conditional",
        "button",
        "divider",
        "gauge",
        "vertical-stack",
        "toggle",
        "numeric-input",
        "select-options",
        "section",
    }
    unsupported = card_types(dashboard).difference(allowed)
    if unsupported:
        raise AssertionError(f"non-native card types were generated: {unsupported}")
    if "resources" in dashboard:
        raise AssertionError("custom frontend resources were generated")


def test_monitor_setup_and_subcategory_projections() -> None:
    """Project explicit single and shared measurements without new identities."""

    _, dashboard, _ = generate()
    monitor = view_by_path(dashboard, "monitor")
    if monitor.get("type") == "sections" or "sections" in monitor:
        raise AssertionError("Monitor did not retain the compact masonry layout")
    if any(card.get("type") != "vertical-stack" for card in monitor["cards"]):
        raise AssertionError("one Monitor column is not a vertical stack")
    mute_banner = monitor["cards"][0]["cards"][0]
    if mute_banner.get("type") != "conditional":
        raise AssertionError("Monitor global-mute banner is not conditional")
    if mute_banner.get("conditions") != [
        {
            "condition": "state",
            "entity": "input_boolean.labpulse_global_notifications_muted",
            "state": "on",
        }
    ]:
        raise AssertionError("Monitor global-mute banner uses the wrong condition")
    banner_text = mute_banner.get("card", {}).get("content", "")
    if "Global Mute Applied" not in banner_text:
        raise AssertionError("Monitor global-mute banner lacks its warning")
    if "/labpulse-monitor/alarm-setup" not in banner_text:
        raise AssertionError("Monitor global-mute banner lacks an Alarm Setup link")
    test_banner = monitor["cards"][0]["cards"][1]
    if test_banner.get("conditions") != [
        {
            "condition": "state",
            "entity": "input_boolean.labpulse_notification_test_mode",
            "state": "on",
        }
    ]:
        raise AssertionError("Monitor test-mode banner uses the wrong condition")
    test_banner_text = test_banner.get("card", {}).get("content", "")
    if "Test Mode Applied" not in test_banner_text:
        raise AssertionError("Monitor test-mode banner lacks its warning")
    if "/labpulse-monitor/alarm-setup" not in test_banner_text:
        raise AssertionError("Monitor test-mode banner lacks an Alarm Setup link")
    problems = monitor["cards"][0]["cards"][2]
    if problems.get("type") != "entity-filter" or problems.get("show_empty") is not False:
        raise AssertionError("Monitor problems card does not hide itself when healthy")
    if problems.get("card", {}).get("title") != "Active Problems":
        raise AssertionError("Monitor problems card is not clearly labelled")
    expected_problem_conditions = [
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
    ]
    if problems.get("conditions") != expected_problem_conditions:
        raise AssertionError("Monitor problems card does not use confirmed lifecycle states")
    if headings(monitor) != [
        "Room Conditions",
        "Alpha Setup",
        "Beta Setup",
        "Empty Setup",
    ]:
        raise AssertionError(f"unexpected Monitor order: {headings(monitor)!r}")
    if headings(monitor, "subtitle"):
        raise AssertionError("physical sensor headings leaked into logical Monitor groups")
    rendered = yaml.safe_dump(monitor, sort_keys=False)
    for hidden_subcategory in ("Ambient Sensors", "Other Measurements", "Cooling Water", "Vacuum"):
        if hidden_subcategory in rendered:
            raise AssertionError(f"subcategory label leaked into Monitor: {hidden_subcategory}")

    shared = "sensor.labpulse_hub_a_shared"
    global_measurement = "sensor.labpulse_hub_a_global_room"
    if entity_occurrences(monitor, shared) != 2:
        raise AssertionError("selected shared measurement was not referenced in both setups")
    if entity_occurrences(monitor, global_measurement) != 1:
        raise AssertionError("global measurement was rendered as a full card more than once")
    if entity_occurrences(monitor, "sensor.labpulse_hub_a_alpha_general") != 1:
        raise AssertionError("single-setup measurement projection is incorrect")
    if entity_occurrences(monitor, "sensor.labpulse_hub_a_alpha_only") != 1:
        raise AssertionError("single-setup measurement projection is incorrect")
    if entity_occurrences(monitor, "sensor.labpulse_hub_b_alpha_other_hub") != 1:
        raise AssertionError("one setup did not receive measurements from both hubs")
    if "Shared with" not in rendered:
        raise AssertionError("shared measurement context is not visible")
    if "All setups" in rendered:
        raise AssertionError("removed all-membership wording remains visible")
    problem_entities = {
        entity["entity"] for entity in problems.get("entities", [])
    }
    expected_problem_entities = {
        "input_boolean.labpulse_hub_a_service_fault_active",
        "input_boolean.labpulse_hub_b_service_fault_active",
    }
    for service, measurement in (
        ("hub_a", "alpha_general"),
        ("hub_a", "alpha_only"),
        ("hub_a", "shared"),
        ("hub_a", "beta_only"),
        ("hub_a", "global_room"),
        ("hub_b", "alpha_other_hub"),
    ):
        expected_problem_entities.add(
            f"input_select.labpulse_{service}_{measurement}_alarm_state"
        )
    if problem_entities != expected_problem_entities:
        raise AssertionError("Monitor problems do not cover the canonical fault sources")
    measurement_problem_rows = [
        entity
        for entity in problems.get("entities", [])
        if str(entity.get("entity", "")).endswith("_alarm_state")
    ]
    if len(measurement_problem_rows) != 6:
        raise AssertionError("Monitor problems do not contain each ordinary measurement once")
    setup_mutes_by_measurement = {
        "hub_a_alpha_general": ["alpha_setup"],
        "hub_a_alpha_only": ["alpha_setup"],
        "hub_a_shared": ["alpha_setup", "beta_setup"],
        "hub_a_beta_only": ["beta_setup"],
        "hub_a_global_room": ["room_conditions"],
        "hub_b_alpha_other_hub": ["alpha_setup"],
    }
    for row in measurement_problem_rows:
        alarm_state_entity = row["entity"]
        muted_entity = alarm_state_entity.replace(
            "input_select.", "input_boolean."
        ).replace("_alarm_state", "_alarm_muted")
        measurement_id = alarm_state_entity.removeprefix(
            "input_select.labpulse_"
        ).removesuffix("_alarm_state")
        setup_state_conditions = [
            {
                "condition": "state",
                "entity": f"input_boolean.labpulse_setup_{setup_id}_notifications_muted",
                "state": "off",
            }
            for setup_id in setup_mutes_by_measurement[measurement_id]
        ]
        if len(setup_state_conditions) == 1:
            setup_conditions = setup_state_conditions
        else:
            setup_conditions = [
                {"condition": "or", "conditions": setup_state_conditions}
            ]
        if row.get("conditions") != [
            {
                "condition": "state",
                "state": ["Danger", "Sensor Fault"],
            },
            {
                "condition": "state",
                "entity": muted_entity,
                "state": "off",
            },
        ] + setup_conditions:
            raise AssertionError(
                f"measurement or setup mute can leak into Monitor problems: {alarm_state_entity}"
            )
        if "input_boolean.labpulse_global_notifications_muted" in yaml.safe_dump(
            row, sort_keys=False
        ):
            raise AssertionError("global mute incorrectly conceals Monitor problems")


def test_alarm_controls_are_grouped_by_setup() -> None:
    """Render the native landing sections and one compact row per measurement."""

    _, dashboard, _ = generate()
    landing = view_by_path(dashboard, "alarm-setup")
    setup_views = [
        view
        for view in dashboard["views"]
        if str(view.get("path", "")).startswith("alarm-setup-")
    ]
    if landing.get("type") != "sections" or landing.get("max_columns") != 3:
        raise AssertionError("Alarm Setup is not a three-column Sections view")
    if headings(landing) != [
        "Configure Alarms",
        "Notification Controls",
        "Group Alarm Settings",
    ]:
        raise AssertionError(f"unexpected Alarm Setup sections: {headings(landing)!r}")
    if [section.get("column_span") for section in landing["sections"]] != [3, 1, 2]:
        raise AssertionError("landing section widths do not follow the native layout")
    landing_rendered = yaml.safe_dump(landing, sort_keys=False)
    if "_alarm_controls_expanded" in landing_rendered:
        raise AssertionError("measurement editors leaked onto the landing page")
    if "alarm-setup-empty_setup" in landing_rendered:
        raise AssertionError("empty setup gained an alarm navigation row")
    for setup_id in ("room_conditions", "alpha_setup", "beta_setup"):
        if f"/labpulse-monitor/alarm-setup-{setup_id}" not in landing_rendered:
            raise AssertionError(f"setup Configure action is missing: {setup_id}")

    # Every subview has explicit desktop and mobile projections of each row.
    expected_rows = {
        "alarm-setup-room_conditions": 1,
        "alarm-setup-alpha_setup": 4,
        "alarm-setup-beta_setup": 2,
    }
    for view in setup_views:
        if view.get("type") != "sections" or view.get("max_columns") != 3:
            raise AssertionError("a setup editor does not use the wide Sections grid")
        if view.get("dense_section_placement") is not False:
            raise AssertionError("a setup editor can reorder its measurement rows")
        header_sections = view["sections"][:2]
        if any(section.get("column_span") != 3 for section in header_sections):
            raise AssertionError("a responsive setup header does not span the view")
        header_rendered = yaml.safe_dump(header_sections, sort_keys=False)
        for label in ("Notifications active", "Notifications muted"):
            if label not in header_rendered:
                raise AssertionError(f"setup header is missing {label}")
        measurement_sections = view["sections"][2:]
        if len(measurement_sections) != expected_rows[view["path"]] * 2:
            raise AssertionError(f"wrong measurement-row count: {view['path']}")
        for desktop, mobile in zip(
            measurement_sections[::2], measurement_sections[1::2], strict=True
        ):
            if desktop.get("type") != "grid" or mobile.get("type") != "grid":
                raise AssertionError("a measurement row is not a grid section")
            if "background" in desktop or "background" in mobile:
                raise AssertionError("a closed measurement row has a grey background")
            if desktop.get("column_span") != 3 or mobile.get("column_span") != 3:
                raise AssertionError("a measurement row does not span the wide view")
            if desktop.get("visibility") != [
                {"condition": "screen", "media_query": "(min-width: 900px)"}
            ]:
                raise AssertionError("desktop measurement visibility is incorrect")
            if mobile.get("visibility") != [
                {"condition": "screen", "media_query": "(max-width: 899px)"}
            ]:
                raise AssertionError("mobile measurement visibility is incorrect")
            desktop_spans = [
                card.get("grid_options", {}).get("columns")
                for card in desktop["cards"]
            ]
            if desktop_spans != [6, 6, 6, 6, 6, 6, 6, 6, "full"]:
                raise AssertionError(f"desktop row grid is incorrect: {desktop_spans!r}")
            mobile_spans = [
                card.get("grid_options", {}).get("columns")
                for card in mobile["cards"]
            ]
            if mobile_spans != [
                "full", "full", 4, 4, 4, 4, "full", "full", "full"
            ]:
                raise AssertionError(f"mobile row grid is incorrect: {mobile_spans!r}")
            names = str(
                [
                    item.get("name")
                    for item in walk_dashboard(desktop)
                    if isinstance(item, dict)
                ]
            )
            if "Configure" not in names or "Close" not in names:
                raise AssertionError("measurement row lacks labelled Configure/Close actions")
            if desktop["cards"][6].get("type") != "conditional":
                raise AssertionError("Configure is not on the right of the summary row")

    # Summary values stay read-only while mute is an explicit state-aware action.
    for view in setup_views:
        for section in view["sections"][2:]:
            for tile in section["cards"][:4]:
                for action in (
                    "tap_action",
                    "hold_action",
                    "double_tap_action",
                    "icon_tap_action",
                ):
                    if tile.get(action) != {"action": "none"}:
                        raise AssertionError(f"display-only tile permits {action}")
            mute_cards = section["cards"][4:6]
            mute_rendered = yaml.safe_dump(mute_cards, sort_keys=False)
            for label in ("Notifications active", "Notifications muted"):
                if label not in mute_rendered:
                    raise AssertionError(f"measurement row is missing {label}")
            for action in ("input_boolean.turn_on", "input_boolean.turn_off"):
                if action not in mute_rendered:
                    raise AssertionError(f"measurement mute is missing {action}")
            if "_recovery_deadband" in mute_rendered:
                raise AssertionError("deadband still occupies the measurement summary row")
            editor = yaml.safe_dump(section["cards"][-1], sort_keys=False)
            for suffix in (
                "_alarm_mode", "_alarm_muted", "_minimum_threshold",
                "_maximum_threshold", "_recovery_deadband", "_required_danger_percent",
                "_observation_window_seconds", "_required_recovery_seconds",
                "_alarm_state", "_observed_danger_percent", "_danger_zone",
                "_recovery_zone", "_sensor_fault_zone",
            ):
                if suffix not in editor:
                    raise AssertionError(f"inline editor is missing {suffix}")

    if "script.labpulse_apply_bulk_alarm_settings" not in landing_rendered:
        raise AssertionError("selective group Apply action is missing")
    if "Nothing will be changed" not in landing_rendered:
        raise AssertionError("group review lacks its empty-selection message")
    group_rendered = yaml.safe_dump(landing["sections"][2], sort_keys=False)
    if "features:" in group_rendered:
        raise AssertionError("group settings still use oversized tile features")
    if (
        "1. Choose target" not in group_rendered
        or "2. Choose settings and values" not in group_rendered
    ):
        raise AssertionError("group settings do not present a clear workflow")
    if "input_boolean.labpulse_bulk_alarm_editor_expanded" not in group_rendered:
        raise AssertionError("group settings are not collapsible")
    for action in ("input_boolean.turn_on", "input_boolean.turn_off"):
        if action not in group_rendered:
            raise AssertionError(f"group editor is missing {action}")
    conditional_values = {
        item["row"]["entity"]
        for item in walk_dashboard(landing["sections"][2])
        if isinstance(item, dict)
        and item.get("type") == "conditional"
        and isinstance(item.get("row"), dict)
        and str(item["row"].get("entity", "")).startswith("input_number.")
    }
    expected_conditional_values = {
        "input_number.labpulse_bulk_required_danger_percent",
        "input_number.labpulse_bulk_observation_window_seconds",
        "input_number.labpulse_bulk_required_recovery_seconds",
        "input_number.labpulse_bulk_deadband_pressure_bar",
        "input_number.labpulse_bulk_deadband_temperature_c",
        "input_number.labpulse_bulk_deadband_temperature_f",
        "input_number.labpulse_bulk_deadband_humidity",
    }
    if conditional_values != expected_conditional_values:
        raise AssertionError(
            f"bulk values are not individually conditional: {conditional_values!r}"
        )
    for section in (view["sections"][1:] for view in setup_views):
        for row in section:
            if row["cards"][0].get("icon") == "mdi:gauge":
                raise AssertionError("measurement tiles still force the pressure icon")
    if "name: Mute\n" in landing_rendered or "name: Unmute\n" in landing_rendered:
        raise AssertionError("setup mute actions still use ambiguous labels")


def test_setup_mute_controls_warn_only_for_shared_measurements() -> None:
    """Confirm cross-setup impact before muting, but not before unmuting."""

    _, dashboard, _ = generate()
    landing = view_by_path(dashboard, "alarm-setup")
    room = view_by_path(dashboard, "alarm-setup-room_conditions")
    room_mute = "input_boolean.labpulse_setup_room_conditions_notifications_muted"
    if not entity_occurrences(landing, room_mute):
        raise AssertionError("exclusive setup mute is missing from the landing page")
    if not entity_occurrences(room, room_mute):
        raise AssertionError("exclusive setup mute is missing from its subview")
    if "confirmation" in yaml.safe_dump(room, sort_keys=False):
        raise AssertionError("exclusive setup gained an unnecessary warning")

    for title, setup_id in (("Alpha Setup", "alpha_setup"), ("Beta Setup", "beta_setup")):
        shared = view_by_path(dashboard, f"alarm-setup-{setup_id}")
        setup_mute = f"input_boolean.labpulse_setup_{setup_id}_notifications_muted"
        if not entity_occurrences(landing, setup_mute):
            raise AssertionError(f"{title} shared mute is missing from the landing page")
        rendered = yaml.safe_dump(shared, sort_keys=False)
        if not entity_occurrences(shared, setup_mute):
            raise AssertionError(f"{title} shared mute is missing from its subview")
        if "Shared Supply" not in rendered or "will remain unmuted" not in rendered:
            raise AssertionError(f"{title} warning does not identify shared impact")
        if "perform_action: input_boolean.turn_on" not in rendered:
            raise AssertionError(f"{title} confirmed mute action is missing")
        if "perform_action: input_boolean.turn_off" not in rendered:
            raise AssertionError(f"{title} direct unmute action is missing")
        confirmations = [
            value
            for value in walk_dashboard(shared)
            if isinstance(value, dict) and "confirmation" in value
        ]
        if len(confirmations) != 2:
            raise AssertionError(f"{title} should warn in both responsive headers")

    empty_mute = "input_boolean.labpulse_setup_empty_setup_notifications_muted"
    if entity_occurrences(dashboard, empty_mute):
        raise AssertionError("empty setup generated a mute control")


def test_bulk_alarm_targets_use_logical_setups() -> None:
    """Apply only selected common or compatible deadband values."""

    paths, _, _ = generate()
    package = yaml.safe_load(paths.package_path.read_text(encoding="utf-8"))
    options = package["input_select"]["labpulse_bulk_alarm_timing_target"]["options"]
    if options != [
        "All measurements",
        "Room Conditions (room_conditions)",
        "Alpha Setup (alpha_setup)",
        "Beta Setup (beta_setup)",
    ]:
        raise AssertionError(f"unexpected bulk target options: {options!r}")

    for helper_id in (
        "labpulse_bulk_apply_required_danger_percent",
        "labpulse_bulk_apply_observation_window_seconds",
        "labpulse_bulk_apply_required_recovery_seconds",
        "labpulse_bulk_alarm_editor_expanded",
        "labpulse_bulk_apply_deadband_pressure_bar",
        "labpulse_bulk_apply_deadband_temperature_c",
        "labpulse_bulk_apply_deadband_temperature_f",
        "labpulse_bulk_apply_deadband_humidity",
    ):
        if package["input_boolean"][helper_id].get("initial") is not False:
            raise AssertionError(f"bulk apply flag does not start off: {helper_id}")

    script = package["script"]["labpulse_apply_bulk_alarm_settings"]
    choices = script["sequence"][2]["choose"]
    danger_targets = {
        choice["conditions"][0]["value_template"]:
        choice["sequence"][0]["then"][0]["target"]["entity_id"]
        for choice in choices
    }
    expected = {
        '{{ selected_target == "Room Conditions (room_conditions)" }}': [
            "input_number.labpulse_hub_a_global_room_required_danger_percent"
        ],
        '{{ selected_target == "Alpha Setup (alpha_setup)" }}': [
            "input_number.labpulse_hub_a_alpha_general_required_danger_percent",
            "input_number.labpulse_hub_a_alpha_only_required_danger_percent",
            "input_number.labpulse_hub_a_shared_required_danger_percent",
            "input_number.labpulse_hub_b_alpha_other_hub_required_danger_percent",
        ],
        '{{ selected_target == "Beta Setup (beta_setup)" }}': [
            "input_number.labpulse_hub_a_shared_required_danger_percent",
            "input_number.labpulse_hub_a_beta_only_required_danger_percent",
        ],
    }
    for condition, targets in expected.items():
        if danger_targets.get(condition) != targets:
            raise AssertionError(f"wrong bulk targets for {condition}: {danger_targets.get(condition)!r}")
    if len(danger_targets['{{ selected_target == "All measurements" }}']) != 6:
        raise AssertionError("all-measurements bulk target does not cover each physical measurement once")
    # Every write is guarded by its snapshotted apply flag.
    for choice in choices:
        for action in choice["sequence"]:
            if "if" not in action or "then" not in action:
                raise AssertionError("a bulk helper write is not independently guarded")
    alpha = next(
        choice for choice in choices
        if "Alpha Setup" in choice["conditions"][0]["value_template"]
    )
    deadband_targets = {
        action["if"][0]["value_template"]: action["then"][0]["target"]["entity_id"]
        for action in alpha["sequence"][3:]
    }
    if deadband_targets.get("{{ apply_deadband_temperature_c }}") != [
        "input_number.labpulse_hub_a_alpha_only_recovery_deadband",
        "input_number.labpulse_hub_a_shared_recovery_deadband",
    ]:
        raise AssertionError("Celsius deadband target is not type-safe")
    if deadband_targets.get("{{ apply_deadband_temperature_f }}") != [
        "input_number.labpulse_hub_b_alpha_other_hub_recovery_deadband"
    ]:
        raise AssertionError("different temperature units were combined")
    rendered_script = yaml.safe_dump(script, sort_keys=False)
    for forbidden in ("minimum_threshold", "maximum_threshold", "alarm_mode", "alarm_muted"):
        if forbidden in rendered_script:
            raise AssertionError(f"unsafe setting entered bulk apply: {forbidden}")
    if script["sequence"][-1] != {"service": "script.labpulse_clear_bulk_alarm_selection"}:
        raise AssertionError("successful bulk apply does not clear its selection")
    reset = next(
        item for item in package["automation"]
        if item.get("id") == "labpulse_clear_bulk_alarm_selection_on_target_change"
    )
    if reset["action"] != [{"service": "script.labpulse_clear_bulk_alarm_selection"}]:
        raise AssertionError("target changes do not clear hidden apply flags")


def test_diagnostics_use_physical_ownership() -> None:
    """Render responsive physical-service sections with canonical measurements."""

    _, dashboard, _ = generate()
    diagnostics = view_by_path(dashboard, "diagnostics")
    if diagnostics.get("type") != "sections" or diagnostics.get("max_columns") != 3:
        raise AssertionError("Diagnostics is not a native three-column Sections view")
    if diagnostics.get("dense_section_placement") is not False:
        raise AssertionError("Diagnostics can reorder physical services")
    if headings(diagnostics) != ["Hub A", "Hub B"]:
        raise AssertionError("Diagnostics did not follow physical service order")
    service_sections = diagnostics.get("sections", [])
    if len(service_sections) != 2 or any(
        section.get("type") != "grid" or section.get("column_span") != 1
        for section in service_sections
    ):
        raise AssertionError("Diagnostics does not have one section per service")
    health_grids = [
        card
        for section in service_sections
        for card in section["cards"]
        if card.get("type") == "grid" and card.get("columns") == 2
    ]
    if len(health_grids) != 2 or any(
        len(grid.get("cards", [])) != 2 for grid in health_grids
    ):
        raise AssertionError("service health indicators are not paired compactly")
    rendered = yaml.safe_dump(diagnostics, sort_keys=False)
    if "Latest measurements" not in rendered or "Physical Measurements" in rendered:
        raise AssertionError("Diagnostics measurement-card presentation is stale")
    if "name: Service Health" not in rendered or "name: Service unhealthy" in rendered:
        raise AssertionError("Diagnostics uses misleading service-health wording")
    if "name: Confirmed service fault" not in rendered:
        raise AssertionError("Diagnostics does not distinguish confirmed service faults")
    for service, measurements in {
        "hub_a": ("alpha_general", "alpha_only", "shared", "beta_only", "global_room"),
        "hub_b": ("alpha_other_hub",),
    }.items():
        for measurement in measurements:
            entity_id = f"sensor.labpulse_{service}_{measurement}"
            if entity_occurrences(diagnostics, entity_id) != 1:
                raise AssertionError(f"physical measurement ownership is wrong: {entity_id}")
            for alarm_entity in (
                f"input_select.labpulse_{service}_{measurement}_alarm_state",
                f"sensor.labpulse_{service}_{measurement}_observed_danger_percent",
                f"binary_sensor.labpulse_{service}_{measurement}_danger_zone",
                f"binary_sensor.labpulse_{service}_{measurement}_recovery_zone",
                f"binary_sensor.labpulse_{service}_{measurement}_sensor_fault_zone",
            ):
                if entity_occurrences(diagnostics, alarm_entity) != 0:
                    raise AssertionError(
                        f"alarm state leaked into physical Diagnostics: {alarm_entity}"
                    )
    if "Disabled Hub" in rendered:
        raise AssertionError("disabled service entered Diagnostics")


def test_power_dashboard_remains_represented() -> None:
    """Keep raw UPS measurements, lifecycle diagnostics, and controls in YAML mode."""

    _, dashboard, _ = generate(config_path=SIM_CONFIG)
    monitor = view_by_path(dashboard, "monitor")
    alarm_setup = view_by_path(dashboard, "alarm-setup")
    power_setup = view_by_path(dashboard, "alarm-power-ups_monitor")
    diagnostics = view_by_path(dashboard, "diagnostics")
    if "UPS Power" not in headings(monitor):
        raise AssertionError("dedicated UPS Monitor column is missing")
    if headings(monitor) != ["UPS Power"]:
        raise AssertionError("power-only config leaked into a logical Monitor section")
    gauges = [
        card
        for column in monitor["cards"]
        for card in column.get("cards", [])
        if card.get("type") == "gauge"
    ]
    if [card.get("entity") for card in gauges] != [
        "sensor.labpulse_ups_monitor_battery_level"
    ]:
        raise AssertionError("UPS battery gauge is missing from Monitor")
    for entity_id in (
        "sensor.labpulse_ups_monitor_voltage",
        "sensor.labpulse_ups_monitor_battery_level",
        "binary_sensor.labpulse_ups_monitor_power_mains_present",
    ):
        if entity_occurrences(monitor, entity_id) != 1:
            raise AssertionError(f"power entity is not canonical in Monitor: {entity_id}")
    problems = next(
        card
        for card in monitor["cards"][0]["cards"]
        if card.get("type") == "entity-filter"
    )
    if entity_occurrences(
        problems, "input_select.labpulse_ups_monitor_power_state"
    ) != 1:
        raise AssertionError("persistent power state is missing from Monitor problems")
    if "binary_sensor.labpulse_ups_monitor_voltage_danger_zone" in yaml.safe_dump(
        monitor, sort_keys=False
    ):
        raise AssertionError("dedicated power measurements leaked into ordinary problem rules")
    if "/labpulse-monitor/alarm-power-ups_monitor" not in yaml.safe_dump(
        alarm_setup, sort_keys=False
    ):
        raise AssertionError("dedicated power navigation is missing")
    if "Power Monitoring" not in headings(power_setup):
        raise AssertionError("dedicated power controls are missing from their subview")
    if power_setup.get("back_path") != "/labpulse-monitor/alarm-setup":
        raise AssertionError("power controls do not return to Alarm Setup")
    rendered = yaml.safe_dump(diagnostics, sort_keys=False)
    for entity_id in (
        "sensor.labpulse_ups_monitor_voltage",
        "sensor.labpulse_ups_monitor_battery_level",
        "sensor.labpulse_ups_monitor_mains_present",
        "input_select.labpulse_ups_monitor_power_state",
        "binary_sensor.labpulse_ups_monitor_power_sensor_fault",
    ):
        if entity_id not in rendered:
            raise AssertionError(f"power dashboard entity is missing: {entity_id}")


def test_starter_keeps_cryogenics_setup_measurements() -> None:
    """Show cryogenics measurements in their explicit logical setup."""

    _, dashboard, _ = generate(config_path=REFACTOR_DIR / "config.yaml")
    monitor = view_by_path(dashboard, "monitor")
    if "Cryogenics Room" not in headings(monitor):
        raise AssertionError("cryogenics setup is missing")
    for entity_id in (
        "sensor.labpulse_room_environment_temperature",
        "sensor.labpulse_room_environment_humidity",
    ):
        if entity_occurrences(monitor, entity_id) != 1:
            raise AssertionError(f"global cryogenics measurement is missing: {entity_id}")


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("plain YAML and registration", test_plain_yaml_and_registration),
    ("Monitor projections", test_monitor_setup_and_subcategory_projections),
    ("setup-grouped alarm controls", test_alarm_controls_are_grouped_by_setup),
    ("shared setup mute warning", test_setup_mute_controls_warn_only_for_shared_measurements),
    ("selective bulk alarm targets", test_bulk_alarm_targets_use_logical_setups),
    ("physical Diagnostics", test_diagnostics_use_physical_ownership),
    ("power dashboard", test_power_dashboard_remains_represented),
    ("cryogenics setup measurements", test_starter_keeps_cryogenics_setup_measurements),
]


def main() -> None:
    """Run focused YAML-dashboard tests."""

    print("Running YAML dashboard tests")
    passed = 0
    for name, test in TESTS:
        try:
            test()
        except Exception as error:
            print(f"[FAIL] {name}: {type(error).__name__}: {error}")
        else:
            print(f"[PASS] {name}")
            passed += 1
    print(f"Summary: {passed}/{len(TESTS)} passed")
    if passed != len(TESTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
