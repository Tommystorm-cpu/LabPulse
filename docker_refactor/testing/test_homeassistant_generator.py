"""Focused integration tests for generated Home Assistant YAML and identities."""

from collections.abc import Callable, Iterable
from pathlib import Path
import sys
from uuid import uuid4

import yaml


sys.dont_write_bytecode = True
REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.mqtt_contracts import SMS_ALERT_PAYLOAD_FIELDS, SMS_SEND_TOPIC
from labpulse_homeassistant.cli import main as generate_homeassistant
from labpulse_homeassistant.paths import GeneratorPaths


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
                "driver": "serial",
                "parser": "pressure",
                "serial_port": "/tmp/labpulse-fake-serial/pressure",
                "device_name": "Air Pressure Sensor Hub",
                "measurements": [
                    {
                        "name": "pressure",
                        "label": "Pressure",
                        "setups": ["air_pressure"],
                        "unit": "bar",
                        "device_class": "pressure",
                    },
                    {
                        "name": "temperature",
                        "label": "Temperature",
                        "setups": ["air_pressure"],
                        "unit": "°C",
                        "device_class": "temperature",
                    },
                ],
            }
        },
    }


def render_into(temp_dir: Path) -> GeneratorPaths:
    """Render the sample configuration into an isolated directory."""

    temp_dir.mkdir(parents=True, exist_ok=True)
    config_path = temp_dir / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(sample_config(), sort_keys=False), encoding="utf-8"
    )
    paths = GeneratorPaths(
        config_path=config_path,
        ha_config_dir=temp_dir / "homeassistant" / "config",
    )
    result = generate_homeassistant(
        ["generator", str(paths.config_path), str(paths.ha_config_dir)]
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

    configuration = paths.configuration_path.read_text(encoding="utf-8")
    if "labpulse-monitor:" not in configuration:
        raise AssertionError("configuration does not register LabPulse dashboard")
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


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("generated package", test_generated_package),
    ("thresholds need no defaults file", test_thresholds_need_no_defaults_file),
    ("first installation starts globally muted once", test_first_install_starts_globally_muted_once),
]


def main() -> None:
    """Run Home Assistant generator tests."""

    print("Running Home Assistant generator tests")
    print(f"Refactor dir: {REFACTOR_DIR}\n")
    passed = 0
    for name, test in TESTS:
        try:
            test()
        except Exception as error:
            print(f"[FAIL] {name}")
            print(f"  error: {type(error).__name__}: {error}\n")
        else:
            print(f"[PASS] {name}\n")
            passed += 1
    failed = len(TESTS) - passed
    print(f"Summary: {passed}/{len(TESTS)} passed, {failed} failed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
