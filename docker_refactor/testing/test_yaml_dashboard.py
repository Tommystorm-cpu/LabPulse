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
                "readings": [
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
                "readings": [
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
                "readings": [{"name": "ignored", "setups": ["alpha_setup"]}],
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
        for card in container["cards"]
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


def test_plain_yaml_and_registration() -> None:
    """Generate a warned plain Lovelace document registered in YAML mode."""

    paths, dashboard, text = generate()
    if not text.startswith("# GENERATED BY LABPULSE."):
        raise AssertionError("generated dashboard warning is missing")
    if any(key in dashboard for key in ("version", "minor_version", "key", "data")):
        raise AssertionError("storage wrapper keys remain in the YAML dashboard")
    if [view["title"] for view in dashboard["views"]] != [
        "Monitor",
        "Alarm Setup",
        "Diagnostics",
    ]:
        raise AssertionError("dashboard view order is incorrect")
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
    """Project explicit single and shared readings without new identities."""

    _, dashboard, _ = generate()
    monitor = dashboard["views"][0]
    if monitor.get("type") == "sections" or "sections" in monitor:
        raise AssertionError("Monitor did not retain the compact masonry layout")
    if any(card.get("type") != "vertical-stack" for card in monitor["cards"]):
        raise AssertionError("one Monitor column is not a vertical stack")
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
    for hidden_subcategory in ("Ambient Sensors", "Other Readings", "Cooling Water", "Vacuum"):
        if hidden_subcategory in rendered:
            raise AssertionError(f"subcategory label leaked into Monitor: {hidden_subcategory}")

    shared = "sensor.labpulse_hub_a_shared"
    global_reading = "sensor.labpulse_hub_a_global_room"
    if entity_occurrences(monitor, shared) != 2:
        raise AssertionError("selected shared reading was not referenced in both setups")
    if entity_occurrences(monitor, global_reading) != 1:
        raise AssertionError("global reading was rendered as a full card more than once")
    if entity_occurrences(monitor, "sensor.labpulse_hub_a_alpha_general") != 1:
        raise AssertionError("single-setup reading projection is incorrect")
    if entity_occurrences(monitor, "sensor.labpulse_hub_a_alpha_only") != 1:
        raise AssertionError("single-setup reading projection is incorrect")
    if entity_occurrences(monitor, "sensor.labpulse_hub_b_alpha_other_hub") != 1:
        raise AssertionError("one setup did not receive readings from both hubs")
    if "Shared with" not in rendered:
        raise AssertionError("shared reading context is not visible")
    if "All setups" in rendered:
        raise AssertionError("removed all-membership wording remains visible")


def test_alarm_controls_are_grouped_by_setup() -> None:
    """Render setup-grouped controls with per-reading and bulk timing."""

    _, dashboard, _ = generate()
    alarm_setup = dashboard["views"][1]
    for service, reading in (
        ("hub_a", "alpha_general"),
        ("hub_a", "alpha_only"),
        ("hub_a", "shared"),
        ("hub_a", "beta_only"),
        ("hub_a", "global_room"),
        ("hub_b", "alpha_other_hub"),
    ):
        toggle = f"input_boolean.labpulse_{service}_{reading}_alarm_controls_expanded"
        expected = 4 if reading == "shared" else 2
        if entity_occurrences(alarm_setup, toggle) != expected:
            raise AssertionError(
                f"{service}.{reading} is not projected into the correct setup groups"
            )
        timing = f"input_number.labpulse_{service}_{reading}_required_danger_percent"
        expected_timing = 2 if reading == "shared" else 1
        if entity_occurrences(alarm_setup, timing) != expected_timing:
            raise AssertionError(f"per-reading timing projection is wrong for {service}.{reading}")
    rendered = yaml.safe_dump(alarm_setup, sort_keys=False)
    if headings(alarm_setup, "subtitle") or "Sensor Hub Timing" in rendered:
        raise AssertionError("physical sensor-hub grouping leaked into Alarm Setup")
    if headings(alarm_setup) != [
        "Notification Controls",
        "Bulk Timing",
        "Room Conditions",
        "Alpha Setup",
        "Beta Setup",
    ]:
        raise AssertionError(f"unexpected Alarm Setup grouping: {headings(alarm_setup)!r}")
    if entity_occurrences(alarm_setup, "input_select.labpulse_bulk_alarm_timing_target") != 1:
        raise AssertionError("bulk timing target selector is missing")
    if entity_occurrences(alarm_setup, "script.labpulse_apply_bulk_alarm_timing") != 2:
        raise AssertionError("bulk timing apply action is missing")
    reading_conditionals = [
        card
        for section in alarm_setup["sections"]
        for card in section["cards"]
        if card.get("type") == "conditional"
        and card.get("conditions", [{}])[0].get("entity", "").endswith(
            "_alarm_controls_expanded"
        )
    ]
    if len(reading_conditionals) != 7:
        raise AssertionError("setup projections did not duplicate only the shared reading")
    if any(card["conditions"][0]["state"] != "on" for card in reading_conditionals):
        raise AssertionError("native conditional expansion semantics changed")


def test_setup_mute_controls_warn_only_for_shared_readings() -> None:
    """Confirm cross-setup impact before muting, but not before unmuting."""

    _, dashboard, _ = generate()
    sections = dashboard["views"][1]["sections"]

    def section(title: str) -> dict[str, object]:
        return next(
            item
            for item in sections
            if any(card.get("heading") == title for card in item["cards"])
        )

    room = section("Room Conditions")
    room_mute = "input_boolean.labpulse_setup_room_conditions_notifications_muted"
    if entity_occurrences(room, room_mute) != 1:
        raise AssertionError("exclusive setup did not get one direct mute tile")
    if "confirmation" in yaml.safe_dump(room, sort_keys=False):
        raise AssertionError("exclusive setup gained an unnecessary warning")

    for title, setup_id in (("Alpha Setup", "alpha_setup"), ("Beta Setup", "beta_setup")):
        shared = section(title)
        setup_mute = f"input_boolean.labpulse_setup_{setup_id}_notifications_muted"
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
    if entity_occurrences(dashboard["views"][1], empty_mute):
        raise AssertionError("empty setup generated a mute control")


def test_bulk_timing_targets_use_logical_setups() -> None:
    """Apply bulk values to all readings or one setup without hub grouping."""

    paths, _, _ = generate()
    package = yaml.safe_load(paths.package_path.read_text(encoding="utf-8"))
    options = package["input_select"]["labpulse_bulk_alarm_timing_target"]["options"]
    if options != [
        "All readings",
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
    if len(danger_targets['{{ selected_target == "All readings" }}']) != 6:
        raise AssertionError("all-readings bulk target does not cover each physical reading once")
    if any(len(choice["sequence"]) != 3 for choice in choices):
        raise AssertionError("bulk timing does not apply all three timing values")


def test_diagnostics_use_physical_ownership() -> None:
    """List enabled readings once under config-ordered physical services."""

    _, dashboard, _ = generate()
    diagnostics = dashboard["views"][2]
    if headings(diagnostics) != ["Hub A", "Hub B"]:
        raise AssertionError("Diagnostics did not follow physical service order")
    for service, readings in {
        "hub_a": ("alpha_general", "alpha_only", "shared", "beta_only", "global_room"),
        "hub_b": ("alpha_other_hub",),
    }.items():
        for reading in readings:
            entity_id = f"sensor.labpulse_{service}_{reading}"
            if entity_occurrences(diagnostics, entity_id) != 1:
                raise AssertionError(f"physical reading ownership is wrong: {entity_id}")
    if "Disabled Hub" in yaml.safe_dump(diagnostics, sort_keys=False):
        raise AssertionError("disabled service entered Diagnostics")


def test_power_dashboard_remains_represented() -> None:
    """Keep raw UPS readings, lifecycle diagnostics, and controls in YAML mode."""

    _, dashboard, _ = generate(config_path=SIM_CONFIG)
    monitor = dashboard["views"][0]
    alarm_setup = dashboard["views"][1]
    diagnostics = dashboard["views"][2]
    if "UPS Power" not in headings(monitor):
        raise AssertionError("dedicated UPS Monitor column is missing")
    if headings(monitor) != ["UPS Power"]:
        raise AssertionError("power-only config leaked into a logical Monitor section")
    gauges = [
        card
        for column in monitor["cards"]
        for card in column["cards"]
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
    if "Power Monitoring" not in headings(alarm_setup):
        raise AssertionError("dedicated power controls are missing")
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


def test_starter_keeps_cryogenics_setup_readings() -> None:
    """Show cryogenics readings in their explicit logical setup."""

    _, dashboard, _ = generate(config_path=REFACTOR_DIR / "config.yaml")
    monitor = dashboard["views"][0]
    if "Cryogenics Room" not in headings(monitor):
        raise AssertionError("cryogenics setup is missing")
    for entity_id in (
        "sensor.labpulse_room_environment_temperature",
        "sensor.labpulse_room_environment_humidity",
    ):
        if entity_occurrences(monitor, entity_id) != 1:
            raise AssertionError(f"global cryogenics reading is missing: {entity_id}")


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("plain YAML and registration", test_plain_yaml_and_registration),
    ("Monitor projections", test_monitor_setup_and_subcategory_projections),
    ("setup-grouped alarm controls", test_alarm_controls_are_grouped_by_setup),
    ("shared setup mute warning", test_setup_mute_controls_warn_only_for_shared_readings),
    ("logical bulk timing targets", test_bulk_timing_targets_use_logical_setups),
    ("physical Diagnostics", test_diagnostics_use_physical_ownership),
    ("power dashboard", test_power_dashboard_remains_represented),
    ("cryogenics setup readings", test_starter_keeps_cryogenics_setup_readings),
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
