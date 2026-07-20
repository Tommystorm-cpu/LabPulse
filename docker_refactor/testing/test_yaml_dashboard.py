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
                    {"name": "alpha_general", "label": "General", "setups": ["alpha_setup"]},
                    {
                        "name": "alpha_only",
                        "label": "Alpha Only",
                        "subcategory": "Cooling Water",
                        "setups": ["alpha_setup"],
                    },
                    {
                        "name": "shared",
                        "label": "Shared Supply",
                        "subcategory": "Cooling Water",
                        "setups": ["beta_setup", "alpha_setup"],
                    },
                    {
                        "name": "beta_only",
                        "label": "Beta Only",
                        "subcategory": "Vacuum",
                        "setups": ["beta_setup"],
                    },
                    {
                        "name": "global_room",
                        "label": "Room Temperature",
                        "subcategory": "Ambient Sensors",
                        "setups": ["room_conditions"],
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
    problems = monitor["cards"][0]["cards"][0]
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
        setup_conditions = [
            {
                "condition": "state",
                "entity": f"input_boolean.labpulse_setup_{setup_id}_notifications_muted",
                "state": "off",
            }
            for setup_id in setup_mutes_by_measurement[measurement_id]
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
    """Render setup-grouped controls with per-measurement and bulk timing."""

    _, dashboard, _ = generate()
    alarm_setup = view_by_path(dashboard, "alarm-setup")
    setup_views = [
        view
        for view in dashboard["views"]
        if str(view.get("path", "")).startswith("alarm-setup-")
    ]
    if "type" in alarm_setup or "sections" in alarm_setup or "max_columns" in alarm_setup:
        raise AssertionError("Alarm Setup landing page is not native masonry")
    if not alarm_setup.get("cards"):
        raise AssertionError("Alarm Setup masonry cards are missing")
    if any(
        card.get("type") != "vertical-stack" for card in alarm_setup["cards"]
    ):
        raise AssertionError("an Alarm Setup landing block can split across masonry cells")
    landing_rendered = yaml.safe_dump(alarm_setup, sort_keys=False)
    if "_alarm_controls_expanded" in landing_rendered:
        raise AssertionError("measurement controls leaked onto the Alarm Setup landing page")
    for setup_id in ("room_conditions", "alpha_setup", "beta_setup"):
        destination = f"/labpulse-monitor/alarm-setup-{setup_id}"
        if landing_rendered.count(destination) != 2:
            raise AssertionError(f"setup navigation tile is incomplete: {setup_id}")
    if "alarm-setup-empty_setup" in landing_rendered:
        raise AssertionError("empty setup gained an alarm navigation tile")
    if any(view.get("max_columns") != 3 for view in setup_views):
        raise AssertionError("a setup editor does not use the three-column layout")
    expected_column_headings = ["Measurements", "Alarm Settings", "Live Alarm Status"]
    for view in setup_views:
        if headings(view) != expected_column_headings:
            raise AssertionError(
                f"setup editor columns are incorrect: {headings(view)!r}"
            )

    for service, measurement in (
        ("hub_a", "alpha_general"),
        ("hub_a", "alpha_only"),
        ("hub_a", "shared"),
        ("hub_a", "beta_only"),
        ("hub_a", "global_room"),
        ("hub_b", "alpha_other_hub"),
    ):
        toggle = f"input_boolean.labpulse_{service}_{measurement}_alarm_controls_expanded"
        expected = 6 if measurement == "shared" else 3
        if entity_occurrences(setup_views, toggle) != expected:
            raise AssertionError(
                f"{service}.{measurement} is not projected into the correct setup groups"
            )
        timing = f"input_number.labpulse_{service}_{measurement}_required_danger_percent"
        expected_timing = 2 if measurement == "shared" else 1
        if entity_occurrences(setup_views, timing) != expected_timing:
            raise AssertionError(f"per-measurement timing projection is wrong for {service}.{measurement}")
        live_status = f"sensor.labpulse_{service}_{measurement}_observed_danger_percent"
        if entity_occurrences(setup_views, live_status) != expected_timing:
            raise AssertionError(
                f"live alarm status projection is wrong for {service}.{measurement}"
            )
    rendered = yaml.safe_dump(setup_views, sort_keys=False)
    if any(headings(view, "subtitle") for view in setup_views) or "Sensor Hub Timing" in rendered:
        raise AssertionError("physical sensor-hub grouping leaked into Alarm Setup")
    if headings(alarm_setup) != [
        "Notification Controls",
        "Bulk Timing",
        "Configure Alarms",
    ]:
        raise AssertionError(f"unexpected Alarm Setup landing groups: {headings(alarm_setup)!r}")
    navigation = next(
        card
        for card in alarm_setup["cards"]
        if "Configure Alarms" in headings({"cards": [card]})
    )
    setup_rows = [
        card
        for card in navigation["cards"]
        if card.get("type") == "grid" and card.get("columns") == 2
    ]
    if len(setup_rows) != 3:
        raise AssertionError("Configure Alarms does not contain one row per active setup")
    if any(
        len(row.get("cards", [])) != 2
        or row["cards"][1].get("type") != "vertical-stack"
        for row in setup_rows
    ):
        raise AssertionError("setup navigation and mute controls are not paired in two columns")
    if entity_occurrences(alarm_setup, "input_select.labpulse_bulk_alarm_timing_target") != 1:
        raise AssertionError("bulk timing target selector is missing")
    if entity_occurrences(alarm_setup, "script.labpulse_apply_bulk_alarm_timing") != 2:
        raise AssertionError("bulk timing apply action is missing")
    measurement_conditionals = [
        card
        for view in setup_views
        for section in view["sections"]
        for card in section["cards"]
        if card.get("type") == "conditional"
        and card.get("conditions", [{}])[0].get("entity", "").endswith(
            "_alarm_controls_expanded"
        )
    ]
    if len(measurement_conditionals) != 14:
        raise AssertionError("settings and status projections are incomplete")
    if any(card["conditions"][0]["state"] != "on" for card in measurement_conditionals):
        raise AssertionError("native conditional expansion semantics changed")
    launcher_grids = [
        card
        for view in setup_views
        for section in view["sections"]
        for card in section["cards"]
        if card.get("type") == "grid" and card.get("columns") == 2
    ]
    if len(launcher_grids) != 3:
        raise AssertionError("each setup does not have one compact measurement launcher grid")
    launchers = [card for grid in launcher_grids for card in grid["cards"]]
    if any(not card.get("hide_state") for card in launchers):
        raise AssertionError("a collapsed measurement launcher exposes presentation state")
    if any("Show Controls" in str(card.get("name", "")) for card in launchers):
        raise AssertionError("awkward Show Controls wording remains")
    for view in setup_views:
        settings_rendered = yaml.safe_dump(view["sections"][1], sort_keys=False)
        status_rendered = yaml.safe_dump(view["sections"][2], sort_keys=False)
        for derived_suffix in (
            "_observed_danger_percent",
            "_danger_zone",
            "_recovery_zone",
            "_sensor_fault_zone",
        ):
            if derived_suffix in settings_rendered:
                raise AssertionError(
                    f"derived state leaked into editable settings: {derived_suffix}"
                )
            if derived_suffix not in status_rendered:
                raise AssertionError(
                    f"derived state is missing from live status: {derived_suffix}"
                )


def test_setup_mute_controls_warn_only_for_shared_measurements() -> None:
    """Confirm cross-setup impact before muting, but not before unmuting."""

    _, dashboard, _ = generate()
    landing = view_by_path(dashboard, "alarm-setup")
    room = view_by_path(dashboard, "alarm-setup-room_conditions")
    room_mute = "input_boolean.labpulse_setup_room_conditions_notifications_muted"
    if entity_occurrences(landing, room_mute) != 2:
        raise AssertionError("exclusive setup mute is missing from the landing page")
    if entity_occurrences(room, room_mute) != 1:
        raise AssertionError("exclusive setup did not get one direct mute tile")
    if "confirmation" in yaml.safe_dump(room, sort_keys=False):
        raise AssertionError("exclusive setup gained an unnecessary warning")

    for title, setup_id in (("Alpha Setup", "alpha_setup"), ("Beta Setup", "beta_setup")):
        shared = view_by_path(dashboard, f"alarm-setup-{setup_id}")
        setup_mute = f"input_boolean.labpulse_setup_{setup_id}_notifications_muted"
        if entity_occurrences(landing, setup_mute) != 7:
            raise AssertionError(f"{title} shared mute is incomplete on the landing page")
        rendered = yaml.safe_dump(shared, sort_keys=False)
        if entity_occurrences(shared, setup_mute) != 6:
            raise AssertionError(f"{title} shared mute states are incomplete")
        if "Shared Supply" not in rendered or "shared with other setups" not in rendered:
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
        if len(confirmations) != 1:
            raise AssertionError(f"{title} should warn only while enabling mute")

    empty_mute = "input_boolean.labpulse_setup_empty_setup_notifications_muted"
    if entity_occurrences(dashboard, empty_mute):
        raise AssertionError("empty setup generated a mute control")


def test_bulk_timing_targets_use_logical_setups() -> None:
    """Apply bulk values to all measurements or one setup without hub grouping."""

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

    script = package["script"]["labpulse_apply_bulk_alarm_timing"]
    choices = script["sequence"][1]["choose"]
    danger_targets = {
        choice["conditions"][0]["value_template"]: choice["sequence"][0]["target"][
            "entity_id"
        ]
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
    if any(len(choice["sequence"]) != 3 for choice in choices):
        raise AssertionError("bulk timing does not apply all three timing values")


def test_diagnostics_use_physical_ownership() -> None:
    """Render compact physical-service columns with canonical measurements."""

    _, dashboard, _ = generate()
    diagnostics = view_by_path(dashboard, "diagnostics")
    if "type" in diagnostics or "sections" in diagnostics or "max_columns" in diagnostics:
        raise AssertionError("Diagnostics is not native masonry")
    if headings(diagnostics) != ["Hub A", "Hub B"]:
        raise AssertionError("Diagnostics did not follow physical service order")
    service_columns = diagnostics.get("cards", [])
    if len(service_columns) != 2 or any(
        card.get("type") != "vertical-stack" for card in service_columns
    ):
        raise AssertionError("Diagnostics does not have one compact column per service")
    health_grids = [
        card
        for column in service_columns
        for card in column["cards"]
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
    problems = monitor["cards"][0]["cards"][0]
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
    ("logical bulk timing targets", test_bulk_timing_targets_use_logical_setups),
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
