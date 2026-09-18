"""Behavioral contracts for the generated Home Assistant dashboard."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml
from pydantic import ValidationError

from labpulse.common.config import LabPulseConfig
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
                        "setups": ["alpha_setup"],
                        "unit": "°C", "device_class": "temperature",
                    },
                    "shared": {
                        "label": "Shared Supply Sensor", "short_label": "Shared Supply",
                        "setups": ["beta_setup", "alpha_setup"],
                        "unit": "°C", "device_class": "temperature",
                    },
                    "beta_only": {
                        "label": "Beta Only",
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
    assert visible == ["Monitor", "Alarm Setup", "System Status"]
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
        "Alarm Setup", "System Status",
    ]
    assert headings(view(dashboard, "dashboard-experiments")) == ["Shared Name"]
    assert headings(view(dashboard, "dashboard-room")) == ["Room Conditions"]
    landing = view(dashboard, "alarm-setup")
    assert headings(landing, "subtitle") == ["Monitor", "Experiments", "Room Overview"]
    assert view(dashboard, "alarm-setup-alpha_setup")["title"] == "Monitor — Shared Name"
    assert view(dashboard, "alarm-setup-beta_setup")["title"] == "Experiments — Shared Name"


def test_monitor_projects_measurements_and_links_problems_to_their_settings() -> None:
    """Project membership while linking read-only faults to useful detail views."""

    _, dashboard, _ = generate()
    monitor = view(dashboard, "monitor")
    assert headings(monitor) == ["Room Conditions", "Alpha Setup", "Beta Setup", "Empty Setup"]
    assert occurrences(monitor, "sensor.labpulse_hub_a_shared") == 2
    assert occurrences(monitor, "sensor.labpulse_hub_a_alpha_only") == 1
    assert occurrences(monitor, "sensor.labpulse_hub_b_alpha_other_hub") == 1
    measurement_cards = [
        item for item in walk(monitor)
        if isinstance(item, dict)
        and item.get("type") == "entities"
        and item.get("entities")
        and all(
            str(row.get("entity", "")).startswith("sensor.labpulse_")
            for row in item["entities"]
        )
    ]
    assert [
        [row["entity"] for row in card["entities"]]
        for card in measurement_cards
    ] == [
        ["sensor.labpulse_hub_a_global_room"],
        [
            "sensor.labpulse_hub_a_alpha_general",
            "sensor.labpulse_hub_a_alpha_only",
            "sensor.labpulse_hub_a_shared",
            "sensor.labpulse_hub_b_alpha_other_hub",
        ],
        ["sensor.labpulse_hub_a_shared", "sensor.labpulse_hub_a_beta_only"],
    ]
    assert not any(
        isinstance(item, dict)
        and str(item.get("name", "")).lower().endswith(" availability")
        for item in walk(monitor)
    )
    problems = next(
        item for item in walk(monitor)
        if isinstance(item, dict) and item.get("type") == "entity-filter"
        and item.get("card", {}).get("title") == "Current Problems"
    )
    alarm_rows = [
        row for row in problems["entities"]
        if str(row.get("entity", "")).endswith("_alarm_state")
    ]
    assert len(alarm_rows) == 6
    expected_paths = {
        "input_select.labpulse_hub_a_alpha_general_alarm_state": "/labpulse-monitor/alarm-setup-alpha_setup",
        "input_select.labpulse_hub_a_alpha_only_alarm_state": "/labpulse-monitor/alarm-setup-alpha_setup",
        "input_select.labpulse_hub_a_shared_alarm_state": "/labpulse-monitor/alarm-setup-alpha_setup",
        "input_select.labpulse_hub_a_beta_only_alarm_state": "/labpulse-monitor/alarm-setup-beta_setup",
        "input_select.labpulse_hub_a_global_room_alarm_state": "/labpulse-monitor/alarm-setup-room_conditions",
        "input_select.labpulse_hub_b_alpha_other_hub_alarm_state": "/labpulse-monitor/alarm-setup-alpha_setup",
    }
    for row in alarm_rows:
        assert row.get("type") == "simple-entity"
        assert row.get("tap_action") == {
            "action": "navigate",
            "navigation_path": expected_paths[row["entity"]],
        }
        assert row.get("hold_action") == {"action": "none"}
        assert row.get("double_tap_action") == {"action": "none"}
        mute_entity = row["entity"].replace("input_select.", "input_boolean.").replace(
            "_alarm_state", "_reading_notifications_muted"
        )
        assert {
            "condition": "state", "entity": mute_entity, "state": "off"
        } in row["conditions"]
        assert {"condition": "state", "state": "Danger"} in row["conditions"]
        setup_gate = next(
            condition for condition in row["conditions"]
            if condition.get("condition") == "or"
        )
        assert setup_gate["conditions"]
        assert all(
            condition.get("entity", "").endswith("_notifications_muted")
            and condition.get("state") == "off"
            for condition in setup_gate["conditions"]
        )

    service_rows = [
        row for row in problems["entities"]
        if str(row.get("entity", "")).endswith("_service_offline_incident_active")
    ]
    assert service_rows
    assert all(
        {"condition": "state", "state": "on"} in row.get("conditions", [])
        for row in service_rows
    )
    assert all(row.get("tap_action") == {
        "action": "navigate",
        "navigation_path": "/labpulse-monitor/system-status",
    } for row in service_rows)
    missing_reading_rows = [
        row for row in problems["entities"]
        if str(row.get("entity", "")).endswith("_missing_reading_incident_active")
    ]
    assert missing_reading_rows
    assert all(
        {"condition": "state", "state": "on"} in row.get("conditions", [])
        for row in missing_reading_rows
    )
    assert all(any(
        condition.get("entity", "").endswith("_reading_notifications_muted")
        and condition.get("state") == "off"
        for condition in row.get("conditions", [])
    ) for row in missing_reading_rows)
    setup_missing_reading_rows = [
        row for row in missing_reading_rows
        if row.get("tap_action", {}).get("navigation_path", "").startswith(
            "/labpulse-monitor/alarm-setup-"
        )
    ]
    assert setup_missing_reading_rows
    assert all(any(
        condition.get("condition") == "or"
        and any(
            setup_condition.get("entity", "").endswith("_notifications_muted")
            and setup_condition.get("state") == "off"
            for setup_condition in condition.get("conditions", [])
        )
        for condition in row.get("conditions", [])
    ) for row in setup_missing_reading_rows)


def test_optional_measurement_graphs_support_defaults_overrides_and_calculations() -> None:
    """Replace opted-in rows with graphs at their configured positions."""

    config = dashboard_config()
    hub_a = config["services"]["hub_a"]  # type: ignore[index]
    hub_a["measurement_defaults"] = {"show_graph": True}
    hub_a["measurements"]["alpha_general"]["show_graph"] = False
    config["custom_measurements"] = {
        "difference": {
            "setups": ["alpha_setup"],
            "inputs": {"left": "hub_a.alpha_only", "right": "hub_a.alpha_general"},
            "formula": "left - right",
            "show_graph": True,
        }
    }

    validated = LabPulseConfig.model_validate(config)
    assert validated.services["hub_a"].measurements["alpha_only"].show_graph is True
    assert validated.services["hub_a"].measurements["alpha_general"].show_graph is False
    assert validated.custom_measurements["difference"].show_graph is True

    _, dashboard, _ = generate(config)
    monitor = view(dashboard, "monitor")
    graph_cards = [
        item for item in walk(monitor)
        if isinstance(item, dict)
        and item.get("type") == "sensor"
        and item.get("graph") == "line"
    ]
    assert graph_cards
    assert all(card["hours_to_show"] == 24 and card["detail"] == 2 for card in graph_cards)
    graph_entities = [card["entity"] for card in graph_cards]
    assert "sensor.labpulse_hub_a_alpha_only" in graph_entities
    assert "sensor.labpulse_custom_difference" in graph_entities
    assert "sensor.labpulse_hub_a_alpha_general" not in graph_entities
    alpha_stack = next(
        card for card in monitor["cards"]
        if any(
            child.get("heading") == "Alpha Setup"
            for child in card.get("cards", [])
            if isinstance(child, dict)
        )
    )
    alpha_cards = alpha_stack["cards"]
    alpha_entities = [
        card.get("entity")
        if card.get("type") == "sensor"
        else [row["entity"] for row in card.get("entities", [])]
        for card in alpha_cards[1:]
    ]
    assert alpha_entities == [
        ["sensor.labpulse_hub_a_alpha_general"],
        "sensor.labpulse_hub_a_alpha_only",
        "sensor.labpulse_hub_a_shared",
        ["sensor.labpulse_hub_b_alpha_other_hub"],
        "sensor.labpulse_custom_difference",
    ]
    assert occurrences(monitor, "sensor.labpulse_hub_a_alpha_only") == 1
    assert occurrences(monitor, "sensor.labpulse_custom_difference") == 1
    assert occurrences(monitor, "sensor.labpulse_hub_a_alpha_general") == 1
    assert occurrences(monitor, "sensor.labpulse_hub_b_alpha_other_hub") == 1


@pytest.mark.parametrize("location", ["physical", "defaults", "custom"])
def test_show_graph_requires_a_boolean(location: str) -> None:
    """Reject string-like graph flags at every supported config location."""

    config = dashboard_config()
    if location == "physical":
        config["services"]["hub_a"]["measurements"]["alpha_general"]["show_graph"] = "true"  # type: ignore[index]
    elif location == "defaults":
        config["services"]["hub_a"]["measurement_defaults"] = {"show_graph": 1}  # type: ignore[index]
    else:
        config["custom_measurements"] = {
            "difference": {
                "setups": ["alpha_setup"],
                "inputs": {"left": "hub_a.alpha_only"},
                "formula": "left",
                "show_graph": "yes",
            }
        }
    with pytest.raises(ValidationError):
        LabPulseConfig.model_validate(deepcopy(config))


def test_power_problem_links_to_its_alarm_setup_page() -> None:
    """Open the matching power alarm configuration from Current Problems."""

    _, dashboard, _ = generate(config_path=REPOSITORY / "testing" / "fixtures" / "ups_serial.yaml")
    monitor = view(dashboard, "monitor")
    problems = next(
        item for item in walk(monitor)
        if isinstance(item, dict) and item.get("type") == "entity-filter"
        and item.get("card", {}).get("title") == "Current Problems"
    )
    power_row = next(
        row for row in problems["entities"]
        if str(row.get("entity", "")).endswith("_power_state")
    )
    assert power_row.get("tap_action") == {
        "action": "navigate",
        "navigation_path": "/labpulse-monitor/alarm-power-ups_monitor",
    }
    assert {"condition": "state", "state": "Running on battery"} in power_row["conditions"]
    assert "UPS Power" in headings(monitor)
    for suffix in ("battery_level", "voltage", "power_last_outage_started", "power_last_outage_duration"):
        assert occurrences(monitor, f"sensor.labpulse_ups_monitor_{suffix}") == 1
    assert any(
        isinstance(item, dict) and item.get("type") == "gauge"
        and item.get("entity") == "sensor.labpulse_ups_monitor_battery_level"
        for item in walk(monitor)
    )
    system_status = view(dashboard, "system-status")
    for suffix in ("status", "service_health"):
        entity = f"sensor.labpulse_ups_monitor_{suffix}"
        assert occurrences(monitor, entity) == 0
        assert occurrences(system_status, entity) > 0


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


def test_alarm_summary_tiles_explain_inactive_and_violated_limits() -> None:
    """Color danger red, inactive thresholds disabled, and violated limits red."""

    _, dashboard, _ = generate()
    setup = view(dashboard, "alarm-setup-alpha_setup")
    conditional_tiles = [
        item for item in walk(setup)
        if isinstance(item, dict) and item.get("type") == "conditional"
        and item.get("card", {}).get("type") == "tile"
    ]

    alarm_tiles = [
        item for item in conditional_tiles
        if str(item["card"].get("entity", "")).endswith("_alarm_state")
    ]
    assert alarm_tiles
    assert {item["card"].get("color") for item in alarm_tiles} == {None, "red"}
    assert all(
        item["conditions"][0].get("state") == "Danger"
        for item in alarm_tiles if item["card"].get("color") == "red"
    )
    assert all(
        item["conditions"][0].get("state_not") == "Danger"
        for item in alarm_tiles if item["card"].get("color") is None
    )

    for suffix, active_modes, comparison in (
        ("_minimum_threshold", ["Low Only", "Range"], "below"),
        ("_maximum_threshold", ["High Only", "Range"], "above"),
    ):
        threshold_tiles = [
            item for item in conditional_tiles
            if str(item["card"].get("entity", "")).endswith(suffix)
        ]
        assert threshold_tiles
        assert {item["card"].get("color") for item in threshold_tiles} == {
            None, "disabled", "red"
        }
        for item in threshold_tiles:
            color = item["card"].get("color")
            if color == "disabled":
                assert item["conditions"][0]["state_not"] == active_modes
            else:
                assert item["conditions"][0]["state"] == active_modes
                numeric_condition = (
                    item["conditions"][1]
                    if color == "red"
                    else item["conditions"][1]["conditions"][0]
                )
                assert numeric_condition["condition"] == "numeric_state"
                assert numeric_condition[comparison].endswith(suffix)


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
    """Alarm opt-out must not hide raw monitoring or System Status."""

    config = dashboard_config()
    config["services"]["hub_a"]["measurements"]["alpha_general"]["alarmed"] = False  # type: ignore[index]
    paths, dashboard, _ = generate(config)
    sensor = "sensor.labpulse_hub_a_alpha_general"
    assert occurrences(view(dashboard, "monitor"), sensor) == 1
    assert occurrences(view(dashboard, "system-status"), sensor) == 1
    assert "labpulse_hub_a_alpha_general_alarm_state" not in paths.package.read_text(encoding="utf-8")


def test_controlled_outputs_can_be_assigned_to_setups() -> None:
    """Place assigned outputs with their setup and retain global status."""

    config = dashboard_config()
    config["outputs"] = {
        "cooling_valve": {
            "label": "Cooling Valve",
            "setups": ["empty_setup"],
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
    monitor = view(dashboard, "monitor")
    system_status = view(dashboard, "system-status")
    assert occurrences(monitor, "switch.labpulse_output_cooling_valve") == 1
    assert occurrences(system_status, "switch.labpulse_output_cooling_valve") == 1
    controls = [
        item for item in walk(monitor)
        if isinstance(item, dict) and item.get("type") == "entities"
        and any(
            row.get("entity") == "switch.labpulse_output_cooling_valve"
            for row in item.get("entities", [])
        )
    ]
    assert len(controls) == 1
    assert "title" not in controls[0]
    assert controls[0]["entities"][0]["name"] == "Cooling Valve"
    assert not any(
        isinstance(item, dict)
        and item.get("content") == "No measurements or controls are currently assigned to this setup."
        for item in walk(monitor)
    )


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


def test_system_status_is_human_readable_and_follows_service_ownership() -> None:
    """Show clear service/readings while hiding internal alarm machinery."""

    paths, dashboard, _ = generate()
    system_status = view(dashboard, "system-status")
    assert headings(system_status)[:2] == ["Hub A", "Hub B"]
    for service, measurements in {
        "hub_a": ("alpha_general", "alpha_only", "shared", "beta_only", "global_room"),
        "hub_b": ("alpha_other_hub",),
    }.items():
        for measurement in measurements:
            assert occurrences(system_status, f"sensor.labpulse_{service}_{measurement}") == 1
            assert occurrences(
                system_status, f"input_select.labpulse_{service}_{measurement}_alarm_state"
            ) == 0
    rendered = yaml.safe_dump(system_status, sort_keys=False)
    assert "What needs attention" in rendered
    assert "No recent data" in rendered
    assert "availability" not in rendered.lower()
    assert "incident_active" not in rendered
    assert "notification_sent" not in rendered
    assert "sms_requested" not in rendered
    assert "condition_age_seconds" not in rendered
    assert "disabled_hub" not in rendered

    package = yaml.safe_load(paths.package.read_text(encoding="utf-8"))
    generated_ids = {
        sensor["unique_id"]
        for block in package["template"]
        for sensor in block.get("sensor", [])
    }
    assert not any(identifier.endswith("_availability") for identifier in generated_ids)
