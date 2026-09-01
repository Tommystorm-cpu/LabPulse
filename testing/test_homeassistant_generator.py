"""Focused integration tests for generated Home Assistant YAML and identities."""

from collections.abc import Callable, Iterable
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import yaml
from jinja2 import UndefinedError


REFACTOR_DIR = Path(__file__).resolve().parents[1]

from labpulse.common.mqtt_contracts import SMS_ALERT_PAYLOAD_FIELDS, SMS_SEND_TOPIC
from labpulse.common.config import load_config
import labpulse.homeassistant.generator as generator
from labpulse.homeassistant.generator import main as generate_homeassistant


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise a contextual assertion when values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def sample_config() -> dict[str, object]:
    """Return a minimal ordinary-measurement configuration."""

    return {
        "mqtt": {"broker": "mosquitto"},
        "setups": {"air_pressure": {"label": "Air Pressure"}},
        "services": {
            "pressure_monitor": {
                "label": "Air Pressure Sensor Hub",
                "driver": {
                    "type": "labpulse.serial_pipe",
                    "options": {"port": "/tmp/labpulse-fake-serial/pressure"},
                },
                "measurements": {
                    "pressure": {
                        "label": "Pressure",
                        "setups": ["air_pressure"],
                        "unit": "bar",
                        "device_class": "pressure",
                    },
                    "temperature": {
                        "label": "Temperature",
                        "setups": ["air_pressure"],
                        "unit": "°C",
                        "device_class": "temperature",
                    },
                },
            }
        },
    }


def render_into(temp_dir: Path) -> SimpleNamespace:
    """Render the sample configuration into an isolated directory."""

    temp_dir.mkdir(parents=True, exist_ok=True)
    config_path = temp_dir / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(sample_config(), sort_keys=False), encoding="utf-8"
    )
    ha_config_dir = temp_dir / "homeassistant" / "config"
    paths = SimpleNamespace(
        config_path=config_path,
        ha_config_dir=ha_config_dir,
        package_path=ha_config_dir / "packages" / "labpulse_generated.yaml",
        configuration_path=ha_config_dir / "configuration.yaml",
        dashboard_path=ha_config_dir / "labpulse-dashboard.yaml",
    )
    result = generate_homeassistant(
        [str(paths.config_path), str(paths.ha_config_dir)]
    )
    assert_equal(result, 0, "generator result")
    return paths


def walk(value: object) -> Iterable[object]:
    """Yield every nested generated YAML value."""

    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def test_generated_package() -> None:
    """Keep generated helpers, alarms, and package identities stable."""

    temp_root = REFACTOR_DIR / "testing" / "tmp"
    paths = render_into(temp_root / f"generator-{uuid4().hex}")
    package = yaml.safe_load(paths.package_path.read_text(encoding="utf-8"))

    expected_helpers = (
        ("input_number", "labpulse_pressure_monitor_pressure_minimum_threshold"),
        ("input_number", "labpulse_pressure_monitor_pressure_maximum_threshold"),
        ("input_number", "labpulse_pressure_monitor_pressure_recovery_deadband"),
        ("input_number", "labpulse_pressure_monitor_pressure_required_danger_percent"),
        ("input_number", "labpulse_pressure_monitor_pressure_observation_window_seconds"),
        ("input_number", "labpulse_pressure_monitor_pressure_required_recovery_seconds"),
        ("input_boolean", "labpulse_pressure_monitor_pressure_alarm_timing_initialized"),
        ("input_select", "labpulse_bulk_alarm_timing_target"),
        ("input_number", "labpulse_bulk_required_danger_percent"),
        ("script", "labpulse_apply_bulk_alarm_settings"),
        ("script", "labpulse_clear_bulk_alarm_selection"),
        ("input_boolean", "labpulse_bulk_apply_required_danger_percent"),
        ("input_boolean", "labpulse_bulk_apply_observation_window_seconds"),
        ("input_boolean", "labpulse_bulk_apply_required_recovery_seconds"),
        ("input_boolean", "labpulse_bulk_apply_deadband_pressure_bar"),
        ("input_boolean", "labpulse_bulk_apply_deadband_temperature_c"),
        ("input_number", "labpulse_bulk_deadband_pressure_bar"),
        ("input_number", "labpulse_bulk_deadband_temperature_c"),
        ("input_select", "labpulse_pressure_monitor_pressure_alarm_state"),
        ("input_select", "labpulse_pressure_monitor_pressure_alarm_mode"),
        ("input_boolean", "labpulse_pressure_monitor_pressure_alarm_muted"),
        (
            "input_boolean",
            "labpulse_pressure_monitor_pressure_alarm_controls_expanded",
        ),
        ("input_boolean", "labpulse_global_notifications_muted"),
        ("input_boolean", "labpulse_first_install_initialized"),
        ("input_boolean", "labpulse_notification_test_mode"),
    )
    for domain, helper_id in expected_helpers:
        if helper_id not in package[domain]:
            raise AssertionError(f"generated package lacks {domain}.{helper_id}")

    aliases = [item["alias"] for item in package["automation"]]
    for alias in (
        "LabPulse Pressure Danger",
        "LabPulse Pressure Recovery",
        "LabPulse Pressure Sensor Fault",
        "LabPulse Pressure Sensor Recovery",
    ):
        if aliases.count(alias) != 1:
            raise AssertionError(f"expected one canonical automation: {alias}")

    danger = next(
        item for item in package["automation"]
        if item["alias"] == "LabPulse Pressure Danger"
    )
    publish_actions = [
        item
        for item in walk(danger)
        if isinstance(item, dict) and item.get("service") == "mqtt.publish"
    ]
    assert_equal(len(publish_actions), 1, "danger SMS request count")
    assert_equal(
        publish_actions[0]["data"]["topic"], SMS_SEND_TOPIC, "danger SMS topic"
    )
    payload = str(publish_actions[0]["data"]["payload"])
    for field in SMS_ALERT_PAYLOAD_FIELDS:
        if f'"{field}"' not in payload:
            raise AssertionError(f"danger SMS payload lacks {field}")
    if "Affected setup: Air Pressure." not in payload:
        raise AssertionError("danger SMS lacks logical setup context")

    sensor_recovery = next(
        item
        for item in package["automation"]
        if item["alias"] == "LabPulse Pressure Sensor Recovery"
    )
    recovery_trigger = sensor_recovery["trigger"][0]
    assert_equal(
        recovery_trigger["platform"],
        "template",
        "sensor recovery reconciliation trigger",
    )
    recovery_template = str(recovery_trigger["value_template"])
    for required_fragment in (
        "input_select.labpulse_pressure_monitor_pressure_alarm_state",
        "binary_sensor.labpulse_pressure_monitor_pressure_sensor_fault_zone",
        "binary_sensor.labpulse_pressure_monitor_pressure_recovery_zone",
        "sensor.labpulse_pressure_monitor_pressure_observed_danger_percent",
        "input_number.labpulse_pressure_monitor_pressure_required_danger_percent",
    ):
        if required_fragment not in recovery_template:
            raise AssertionError(
                "sensor recovery reconciliation lacks " + required_fragment
            )
    if "'Sensor Fault'" not in recovery_template or "'off'" not in recovery_template:
        raise AssertionError("sensor recovery does not require a cleared fault")
    recovery_options = {
        item["data"]["option"]
        for item in walk(sensor_recovery["action"])
        if isinstance(item, dict)
        and item.get("service") == "input_select.select_option"
    }
    assert_equal(
        recovery_options,
        {"Danger", "Normal"},
        "sensor recovery classifications",
    )

    service_unhealthy = next(
        item
        for block in package["template"]
        for item in block.get("binary_sensor", [])
        if item.get("unique_id")
        == "labpulse_pressure_monitor_service_unhealthy"
    )
    service_unhealthy_state = str(service_unhealthy["state"])
    for required_fragment in (
        "sensor.labpulse_pressure_monitor_pressure",
        "sensor.labpulse_pressure_monitor_temperature",
        "not is_number",
        "status_unhealthy or",
    ):
        if required_fragment not in service_unhealthy_state:
            raise AssertionError(
                "service health does not aggregate total telemetry loss: "
                + required_fragment
            )

    sensor_fault = next(
        item
        for item in package["automation"]
        if item["alias"] == "LabPulse Pressure Sensor Fault"
    )
    post_delay_conditions = sensor_fault["action"][1:4]
    condition_entities = {
        item.get("entity_id")
        for item in post_delay_conditions
        if item.get("condition") == "state"
    }
    for required_entity in (
        "binary_sensor.labpulse_pressure_monitor_pressure_sensor_fault_zone",
        "binary_sensor.labpulse_pressure_monitor_service_unhealthy",
        "input_boolean.labpulse_pressure_monitor_service_fault_active",
    ):
        if required_entity not in condition_entities:
            raise AssertionError(
                "sensor fault does not recheck service ownership: "
                + required_entity
            )

    service_fault = next(
        item
        for item in package["automation"]
        if item["alias"] == "LabPulse Air Pressure Sensor Hub Service Fault"
    )
    normalizations = [
        item
        for item in walk(service_fault["action"])
        if isinstance(item, dict)
        and item.get("service") == "input_select.select_option"
        and item.get("data", {}).get("option") == "Normal"
    ]
    assert_equal(len(normalizations), 1, "service fault subordinate reset count")
    assert_equal(
        set(normalizations[0]["target"]["entity_id"]),
        {
            "input_select.labpulse_pressure_monitor_pressure_alarm_state",
            "input_select.labpulse_pressure_monitor_temperature_alarm_state",
        },
        "service fault subordinate alarm states",
    )
    dismissals = [
        item
        for item in walk(service_fault["action"])
        if isinstance(item, dict)
        and item.get("service") == "persistent_notification.dismiss"
    ]
    assert_equal(len(dismissals), 1, "service fault subordinate dismissal action")
    repeated_ids = next(
        item["repeat"]["for_each"]
        for item in service_fault["action"]
        if "repeat" in item
    )
    assert_equal(
        set(repeated_ids),
        {
            "labpulse_pressure_monitor_pressure_status",
            "labpulse_pressure_monitor_temperature_status",
        },
        "service fault subordinate notification IDs",
    )

    configuration = paths.configuration_path.read_text(encoding="utf-8")
    if "labpulse-monitor:" not in configuration:
        raise AssertionError("configuration does not register LabPulse dashboard")
    if "unit_system:" in configuration:
        raise AssertionError("configuration unexpectedly forces unit conversion")
    dashboard = paths.dashboard_path.read_text(encoding="utf-8")
    if not dashboard.startswith("# GENERATED BY LABPULSE."):
        raise AssertionError("dashboard warning is missing")


def test_thresholds_need_no_defaults_file() -> None:
    """Generate editable thresholds without JSON values or seed automations."""

    temp_root = REFACTOR_DIR / "testing" / "tmp"
    paths = render_into(temp_root / f"generator-{uuid4().hex}")
    package = yaml.safe_load(paths.package_path.read_text(encoding="utf-8"))
    if paths.config_path.with_name("alarm_defaults.json").exists():
        raise AssertionError("generator created a threshold defaults file")
    for helper_id in (
        "labpulse_pressure_monitor_pressure_minimum_threshold",
        "labpulse_pressure_monitor_pressure_maximum_threshold",
        "labpulse_pressure_monitor_pressure_recovery_deadband",
    ):
        if "initial" in package["input_number"][helper_id]:
            raise AssertionError(f"threshold helper has a seeded value: {helper_id}")
    aliases = {item["alias"] for item in package["automation"]}
    if "LabPulse Pressure Initialize Alarm Defaults" in aliases:
        raise AssertionError("per-measurement threshold initializer remains")
    assert_equal(
        package["input_select"]["labpulse_pressure_monitor_pressure_alarm_mode"]["options"][0],
        "Disabled",
        "fresh alarm mode",
    )
    assert_equal(
        package["input_select"]["labpulse_pressure_monitor_pressure_alarm_state"]["options"][0],
        "Normal",
        "fresh alarm state",
    )


def test_first_install_starts_globally_muted_once() -> None:
    """Use one restore-state marker rather than muting every restart."""

    temp_root = REFACTOR_DIR / "testing" / "tmp"
    paths = render_into(temp_root / f"generator-{uuid4().hex}")
    package = yaml.safe_load(paths.package_path.read_text(encoding="utf-8"))
    for helper_id in (
        "labpulse_global_notifications_muted",
        "labpulse_first_install_initialized",
    ):
        if "initial" in package["input_boolean"][helper_id]:
            raise AssertionError(f"restore-state helper forces every restart: {helper_id}")
    initializer = next(
        item
        for item in package["automation"]
        if item["alias"] == "LabPulse Initialize First Installation"
    )
    assert_equal(
        initializer["condition"][0],
        {
            "condition": "state",
            "entity_id": "input_boolean.labpulse_first_install_initialized",
            "state": "off",
        },
        "first-install guard",
    )
    targets = initializer["action"][0]["target"]["entity_id"]
    assert_equal(
        targets,
        [
            "input_boolean.labpulse_global_notifications_muted",
            "input_boolean.labpulse_first_install_initialized",
        ],
        "first-install mute targets",
    )


def test_invalid_render_preserves_every_live_file() -> None:
    """Do not touch managed or UI-owned files when one render fails."""

    temp = REFACTOR_DIR / "testing" / "tmp" / f"generator-atomic-{uuid4().hex}"
    ha_dir = temp / "homeassistant" / "config"
    package = ha_dir / "packages" / "labpulse_generated.yaml"
    managed = (ha_dir / "configuration.yaml", package, ha_dir / "labpulse-dashboard.yaml")
    ui_files = tuple(ha_dir / name for name in ("automations.yaml", "scripts.yaml", "scenes.yaml"))
    for path in (*managed, *ui_files):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"sentinel:{path.name}\n", encoding="utf-8")
    config_path = temp / "config.yaml"
    config_path.write_text(yaml.safe_dump(sample_config(), sort_keys=False), encoding="utf-8")

    original = generator._render_dashboard
    generator._render_dashboard = lambda _context: (_ for _ in ()).throw(ValueError("bad dashboard"))
    try:
        try:
            generator.generate_homeassistant(load_config(config_path), ha_dir)
        except ValueError as error:
            if str(error) != "bad dashboard":
                raise
        else:
            raise AssertionError("invalid render unexpectedly installed output")
    finally:
        generator._render_dashboard = original
    for path in (*managed, *ui_files):
        assert_equal(path.read_text(encoding="utf-8"), f"sentinel:{path.name}\n", f"preserved {path.name}")


def test_strict_and_malformed_templates_fail() -> None:
    """Reject undefined generator values and malformed dashboard shapes."""

    try:
        generator._environment().from_string("[[ absent_value ]]").render()
    except UndefinedError:
        pass
    else:
        raise AssertionError("StrictUndefined was not active")
    for malformed in ("views: {}\n", "- not-a-mapping\n"):
        template = SimpleNamespace(render=lambda **_kwargs: malformed)
        environment = SimpleNamespace(get_template=lambda _name: template)
        with patch.object(generator, "_environment", return_value=environment):
            try:
                generator._render_dashboard(object())  # type: ignore[arg-type]
            except ValueError:
                pass
            else:
                raise AssertionError("malformed dashboard shape passed validation")
