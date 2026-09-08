"""Behavioral contracts for the generated Home Assistant dashboard."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import yaml

from labpulse.homeassistant.generator import main as generate_homeassistant


REPOSITORY = Path(__file__).resolve().parents[1]


def dashboard_config() -> dict[str, object]:
    """Return a compact config covering ordering, sharing, and two hubs."""

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
                "label": "Hub A",
                "driver": {"type": "labpulse.serial_pipe", "options": {"port": "/tmp/hub-a"}},
                "measurements": {
                    "alpha_general": {
                        "label": "General", "setups": ["alpha_setup"],
                        "unit": "bar", "device_class": "pressure",
                    },
                    "alpha_only": {
                        "label": "Alpha Setup Temperature", "short_label": "Temperature",
                        "group": "Cooling Water", "setups": ["alpha_setup"],
                        "unit": "°C", "device_class": "temperature",
                    },
                    "shared": {
                        "label": "Shared Supply Sensor", "short_label": "Shared Supply",
                        "group": "Cooling Water", "setups": ["beta_setup", "alpha_setup"],
                        "unit": "°C", "device_class": "temperature",
                    },
                    "beta_only": {
                        "label": "Beta Only", "group": "Vacuum",
                        "setups": ["beta_setup"], "unit": "%", "device_class": "humidity",
                    },
                    "global_room": {
                        "label": "Room Temperature", "setups": ["room_conditions"],
                        "unit": "°C", "device_class": "temperature",
                    },
                },
            },
            "hub_b": {
                "label": "Hub B",
                "driver": {"type": "labpulse.dht11", "options": {"pin": "D4"}},
                "measurements": {
                    "alpha_other_hub": {
                        "label": "Alpha From Hub B", "setups": ["alpha_setup"],
                        "unit": "°F", "device_class": "temperature",
                    }
                },
            },
            "disabled_hub": {
                "enabled": False,
                "label": "Disabled Hub",
                "driver": {"type": "labpulse.serial_pipe", "options": {"port": "/tmp/disabled"}},
                "measurements": {"ignored": {"setups": ["alpha_setup"]}},
            },
        },
    }


def generate(
    config: dict[str, object] | None = None,
    config_path: Path | None = None,
) -> tuple[SimpleNamespace, dict[str, object], str]:
    """Generate into an isolated directory and return parsed artifacts."""

    root = REPOSITORY / "testing" / "tmp" / f"dashboard-{uuid4().hex}"
    root.mkdir(parents=True)
    selected_path = root / "config.yaml"
    if config_path is None:
        selected_path.write_text(
            yaml.safe_dump(config or dashboard_config(), sort_keys=False), encoding="utf-8"
        )
    else:
        selected_path.write_text(config_path.read_text(encoding="utf-8"), encoding="utf-8")

    ha_dir = root / "homeassistant" / "config"
    storage = ha_dir / ".storage"
    storage.mkdir(parents=True)
    sentinel = storage / "lovelace"
    sentinel.write_text('{"user_owned": true}\n', encoding="utf-8")
    if generate_homeassistant([str(selected_path), str(ha_dir)]) != 0:
        raise AssertionError("Home Assistant generation failed")
    assert sentinel.read_text(encoding="utf-8") == '{"user_owned": true}\n'

    paths = SimpleNamespace(
        dashboard=ha_dir / "labpulse-dashboard.yaml",
        configuration=ha_dir / "configuration.yaml",
        package=ha_dir / "packages" / "labpulse_generated.yaml",
    )
    text = paths.dashboard.read_text(encoding="utf-8")
    return paths, yaml.safe_load(text), text


def walk(value: object):
    """Yield every nested dashboard object."""

    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def view(dashboard: dict[str, object], path: str) -> dict[str, object]:
    """Return a view by stable path."""

    return next(item for item in dashboard["views"] if item.get("path") == path)


def occurrences(value: object, entity: str) -> int:
    """Count exact entity references recursively."""

    if isinstance(value, dict):
        return sum(occurrences(child, entity) for child in value.values())
    if isinstance(value, list):
        return sum(occurrences(child, entity) for child in value)
    return int(value == entity)


def headings(value: object, style: str = "title") -> list[str]:
    """Return headings of one style in document order."""

    return [
        item["heading"]
        for item in walk(value)
        if isinstance(item, dict)
        and item.get("type") == "heading"
        and item.get("heading_style") == style
    ]


def test_generated_dashboard_uses_native_yaml_and_preserves_storage() -> None:
    """Generate a registered YAML dashboard without custom frontend cards."""

    paths, dashboard, text = generate()
    assert text.startswith("# GENERATED BY LABPULSE.")
    visible = [item["title"] for item in dashboard["views"] if not item.get("subview")]
    assert visible == ["Monitor", "Alarm Setup", "Diagnostics"]
    assert {item["path"] for item in dashboard["views"] if item.get("subview")} == {
        "alarm-setup-room_conditions", "alarm-setup-alpha_setup", "alarm-setup-beta_setup",
    }
    assert "labpulse-monitor:" in paths.configuration.read_text(encoding="utf-8")
    assert "resources" not in dashboard


def test_dashboard_assignment_and_alarm_navigation_include_dashboard_context() -> None:
    """Group setup tabs by dashboard and distinguish duplicate setup names."""

    config = dashboard_config()
    config["dashboards"] = {
        "experiments": {"label": "Experiments", "order": 10, "icon": "mdi:test-tube"},
        "room": {"label": "Room Overview", "order": 20},
        "spare": {"label": "Spare Dashboard", "order": 30},
    }
    config["setups"]["room_conditions"]["dashboard"] = "room"  # type: ignore[index]
    config["setups"]["alpha_setup"].update(  # type: ignore[index]
        {"label": "Shared Name", "icon": "mdi:flask-outline"}
    )
    config["setups"]["beta_setup"].update(  # type: ignore[index]
        {"label": "Shared Name", "icon": "mdi:flask-outline", "dashboard": "experiments"}
    )

    _, dashboard, _ = generate(config)
    visible = [item["title"] for item in dashboard["views"] if not item.get("subview")]
    assert visible == [
        "Monitor", "Experiments", "Room Overview", "Spare Dashboard",
        "Alarm Setup", "Diagnostics",
    ]
    assert headings(view(dashboard, "dashboard-experiments")) == ["Shared Name"]
    assert headings(view(dashboard, "dashboard-room")) == ["Room Conditions"]
    landing = view(dashboard, "alarm-setup")
    assert headings(landing, "subtitle") == ["Monitor", "Experiments", "Room Overview"]
    assert view(dashboard, "alarm-setup-alpha_setup")["title"] == "Monitor — Shared Name"
    assert view(dashboard, "alarm-setup-beta_setup")["title"] == "Experiments — Shared Name"


def test_monitor_projects_measurements_and_keeps_problem_states_read_only() -> None:
    """Project logical membership while exposing canonical read-only faults."""

    _, dashboard, _ = generate()
    monitor = view(dashboard, "monitor")
    assert headings(monitor) == ["Room Conditions", "Alpha Setup", "Beta Setup", "Empty Setup"]
    assert occurrences(monitor, "sensor.labpulse_hub_a_shared") == 2
    assert occurrences(monitor, "sensor.labpulse_hub_a_alpha_only") == 1
    assert occurrences(monitor, "sensor.labpulse_hub_b_alpha_other_hub") == 1
    problems = next(
        item for item in walk(monitor)
        if isinstance(item, dict) and item.get("type") == "entity-filter"
        and item.get("card", {}).get("title") == "Active Problems"
    )
    alarm_rows = [
        row for row in problems["entities"]
        if str(row.get("entity", "")).endswith("_alarm_state")
    ]
    assert len(alarm_rows) == 6
    for row in alarm_rows:
        assert row.get("type") == "simple-entity"
        assert all(row.get(action) == {"action": "none"} for action in (
            "tap_action", "hold_action", "double_tap_action"
        ))


def test_alarm_setup_measurements_open_history_and_status_is_read_only() -> None:
    """Keep readings clickable while preventing dashboard alarm-state edits."""

    _, dashboard, _ = generate()
    setup_views = [item for item in dashboard["views"] if item.get("subview")]
    measurement_tiles = [
        item for setup in setup_views for item in walk(setup)
        if isinstance(item, dict)
        and str(item.get("entity", "")).startswith("sensor.labpulse_")
        and item.get("tap_action") == {"action": "more-info"}
    ]
    assert measurement_tiles
    assert all(tile.get("icon_tap_action") == {"action": "more-info"} for tile in measurement_tiles)
    rendered = yaml.safe_dump(setup_views, sort_keys=False)
    assert "input_boolean.turn_on" in rendered
    assert "input_boolean.turn_off" in rendered
    for suffix in ("_alarm_mode", "_minimum_threshold", "_maximum_threshold", "_recovery_deadband"):
        assert suffix in rendered
    state_rows = [
        item for setup in setup_views for item in walk(setup)
        if isinstance(item, dict)
        and str(item.get("entity", "")).endswith("_alarm_state")
        and item.get("type") == "simple-entity"
    ]
    assert state_rows
    for row in state_rows:
        assert all(row.get(action) == {"action": "none"} for action in (
            "tap_action", "hold_action", "double_tap_action"
        ))


def test_alarm_mode_disables_irrelevant_threshold_inputs() -> None:
    """Render inactive threshold controls as read-only values."""

    _, dashboard, _ = generate()
    editors = [
        item for item in walk(view(dashboard, "alarm-setup-alpha_setup"))
        if isinstance(item, dict) and item.get("type") == "entities"
        and str(item.get("title", "")).endswith(": Alarm behaviour")
    ]
    assert editors
    expected_modes = {
        "minimum_threshold": ["Low Only", "Range"],
        "maximum_threshold": ["High Only", "Range"],
        "recovery_deadband": ["Low Only", "High Only", "Range"],
    }
    for editor in editors:
        conditionals = [row for row in editor["entities"] if row.get("type") == "conditional"]
        for suffix, active_modes in expected_modes.items():
            matches = [
                row for row in conditionals
                if str(row.get("row", {}).get("entity", "")).endswith(suffix)
            ]
            assert len(matches) == 2
            editable = next(row for row in matches if "state" in row["conditions"][0])
            disabled = next(row for row in matches if "state_not" in row["conditions"][0])
            assert editable["conditions"][0]["state"] == active_modes
            assert disabled["conditions"][0]["state_not"] == active_modes
            assert disabled["row"].get("type") == "simple-entity"


def test_non_alarmed_measurements_keep_telemetry_without_alarm_helpers() -> None:
    """Alarm opt-out must not hide raw monitoring or diagnostics."""

    config = dashboard_config()
    config["services"]["hub_a"]["measurements"]["alpha_general"]["alarmed"] = False  # type: ignore[index]
    paths, dashboard, _ = generate(config)
    sensor = "sensor.labpulse_hub_a_alpha_general"
    assert occurrences(view(dashboard, "monitor"), sensor) == 1
    assert occurrences(view(dashboard, "diagnostics"), sensor) == 1
    assert "labpulse_hub_a_alpha_general_alarm_state" not in paths.package.read_text(encoding="utf-8")


def test_controlled_outputs_are_operator_visible() -> None:
    """Show enabled outputs on Monitor and Diagnostics only."""

    config = dashboard_config()
    config["outputs"] = {
        "cooling_valve": {
            "label": "Cooling Valve",
            "driver": {"type": "labpulse.gpio_output", "options": {"gpio_line": 18}},
        },
        "disabled": {
            "enabled": False,
            "label": "Disabled Output",
            "driver": {"type": "labpulse.gpio_output", "options": {"gpio_line": 19}},
        },
    }
    _, dashboard, _ = generate(config)
    assert occurrences(dashboard, "switch.labpulse_output_cooling_valve") == 2
    assert occurrences(dashboard, "switch.labpulse_output_disabled") == 0


def test_alarm_bulk_targets_are_logical_setups() -> None:
    """Apply bulk alarm settings to setup membership, not physical hubs."""

    paths, dashboard, _ = generate()
    rendered = yaml.safe_dump(view(dashboard, "alarm-setup"), sort_keys=False)
    assert "script.labpulse_apply_bulk_alarm_settings" in rendered
    assert "input_select.labpulse_bulk_alarm_timing_target" in rendered
    package = paths.package.read_text(encoding="utf-8")
    assert "labpulse_apply_bulk_alarm_settings:" in package
    assert "Alpha Setup (alpha_setup)" in package
    assert "Hub A (hub_a)" not in package


def test_diagnostics_follow_physical_service_ownership() -> None:
    """Diagnostics show each raw sensor once and omit logical alarm helpers."""

    _, dashboard, _ = generate()
    diagnostics = view(dashboard, "diagnostics")
    for service, measurements in {
        "hub_a": ("alpha_general", "alpha_only", "shared", "beta_only", "global_room"),
        "hub_b": ("alpha_other_hub",),
    }.items():
        for measurement in measurements:
            assert occurrences(diagnostics, f"sensor.labpulse_{service}_{measurement}") == 1
            assert occurrences(
                diagnostics, f"input_select.labpulse_{service}_{measurement}_alarm_state"
            ) == 0
    assert "disabled_hub" not in yaml.safe_dump(diagnostics, sort_keys=False)
