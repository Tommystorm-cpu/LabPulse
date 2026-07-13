from pathlib import Path
import json
import sys
import uuid

import yaml


sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.mqtt_contracts import SMS_ALERT_PAYLOAD_FIELDS, SMS_SEND_TOPIC
from labpulse_homeassistant.cli import main as generate_homeassistant
from labpulse_homeassistant.data_models import GeneratorPaths


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise AssertionError when two values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def sample_config() -> dict[str, object]:
    """Return a minimal LabPulse config with one enabled service."""

    return {
        "mqtt": {"broker": "mosquitto"},
        "services": {
            "pressure_monitor": {
                "enabled": True,
                "driver": "serial",
                "parser": "pressure",
                "serial_port": "/tmp/labpulse-fake-serial/pressure",
                "device_name": "Air Pressure Sensor Hub",
                "display": {"section": "Air Pressure", "icon": "mdi:gauge", "order": 40},
                "readings": [
                    {
                        "name": "pressure",
                        "label": "Pressure",
                        "unit": "bar",
                    }
                ],
            }
        }
    }


def render_into(temp_dir: Path, reset_dashboard: bool) -> GeneratorPaths:
    """Render sample Home Assistant files into a temporary directory."""

    temp_dir.mkdir(parents=True, exist_ok=True)
    config_path = temp_dir / "config.yaml"
    config_path.write_text(yaml.safe_dump(sample_config(), sort_keys=False), encoding="utf-8")
    ha_config_dir = temp_dir / "homeassistant" / "config"
    paths = GeneratorPaths(config_path=config_path, ha_config_dir=ha_config_dir)
    result = generate_homeassistant(
        [
            "generator",
            str(config_path),
            str(ha_config_dir),
            "1" if reset_dashboard else "0",
        ]
    )
    assert_equal(result, 0, "generator result")
    return paths


def test_generated_package_and_entity_map() -> None:
    """Check generated YAML contains stable entities and binary alarm sensors."""

    temp_root = REFACTOR_DIR / "testing" / "tmp"
    temp_root.mkdir(exist_ok=True)
    paths = render_into(temp_root / f"generator-{uuid.uuid4().hex}", reset_dashboard=True)
    package_text = paths.package_path.read_text(encoding="utf-8")
    entity_map_text = paths.entity_map_path.read_text(encoding="utf-8")
    dashboard_text = paths.lovelace_path.read_text(encoding="utf-8")
    package = yaml.safe_load(package_text)
    entity_map = yaml.safe_load(entity_map_text)
    configuration = paths.configuration_path.read_text(encoding="utf-8")

    for label, generated_text in (
        ("package", package_text),
        ("entity map", entity_map_text),
        ("dashboard", dashboard_text),
    ):
        if "[[" in generated_text or "]]" in generated_text:
            raise AssertionError(f"{label} contains an unexpanded LabPulse placeholder")

    assert "automation: !include automations.yaml" in configuration
    assert "script: !include scripts.yaml" in configuration
    assert "scene: !include scenes.yaml" in configuration
    assert_equal(paths.ui_automations_path.read_text(encoding="utf-8"), "[]\n", "empty UI automations")
    assert_equal(paths.ui_scripts_path.read_text(encoding="utf-8"), "[]\n", "empty UI scripts")
    assert_equal(paths.ui_scenes_path.read_text(encoding="utf-8"), "[]\n", "empty UI scenes")
    assert "labpulse_pressure_monitor_danger_ratio_percent" in package["input_number"]
    assert "labpulse_pressure_monitor_danger_window_seconds" in package["input_number"]
    assert "labpulse_pressure_monitor_recovery_seconds" in package["input_number"]
    assert "labpulse_pressure_monitor_stale_timeout_seconds" in package["input_number"]
    assert "labpulse_pressure_monitor_pressure_minimum_threshold" in package["input_number"]
    assert "labpulse_pressure_monitor_pressure_maximum_threshold" in package["input_number"]
    assert "labpulse_pressure_monitor_pressure_recovery_deadband" in package["input_number"]
    assert "labpulse_pressure_monitor_pressure_alarm_state" in package["input_select"]
    assert "labpulse_pressure_monitor_pressure_alarm_mode" in package["input_select"]
    assert "labpulse_pressure_monitor_alarm_controls_expanded" in package["input_boolean"]
    assert "labpulse_pressure_monitor_pressure_alarm_muted" in package["input_boolean"]
    assert_equal(
        package["input_number"]["labpulse_pressure_monitor_pressure_minimum_threshold"]["initial"],
        1,
        "minimum threshold initial",
    )
    assert_equal(
        package["input_number"]["labpulse_pressure_monitor_pressure_recovery_deadband"]["initial"],
        0.1,
        "recovery deadband initial",
    )
    assert_equal(
        package["input_select"]["labpulse_pressure_monitor_pressure_alarm_state"]["options"],
        ["Normal", "Danger", "Sensor Fault"],
        "alarm state options",
    )
    assert_equal(
        package["input_select"]["labpulse_pressure_monitor_pressure_alarm_mode"]["initial"],
        "Low Only",
        "pressure default alarm mode",
    )
    history_sensor = package["sensor"][0]
    assert_equal(history_sensor["platform"], "history_stats", "history stats platform")
    assert_equal(history_sensor["type"], "ratio", "history stats ratio")
    assert_equal(
        history_sensor["entity_id"],
        "binary_sensor.labpulse_pressure_monitor_pressure_danger_zone",
        "history stats source",
    )
    if "danger_window_seconds" not in history_sensor["start"]:
        raise AssertionError("history stats start should use editable window helper")

    zone_sensors = package["template"][0]["binary_sensor"]
    assert_equal(zone_sensors[0]["name"], "labpulse_pressure_monitor_pressure_danger_zone", "danger zone")
    assert_equal(zone_sensors[1]["name"], "labpulse_pressure_monitor_pressure_recovery_zone", "recovery zone")
    assert_equal(zone_sensors[2]["name"], "labpulse_pressure_monitor_pressure_sensor_fault_zone", "fault zone")
    if "alarm_mode" not in zone_sensors[0]["state"]:
        raise AssertionError("danger zone should use alarm mode helper")
    if "recovery_deadband" not in zone_sensors[1]["state"]:
        raise AssertionError("recovery zone should use recovery deadband helper")
    if "recovery_minimum" not in zone_sensors[1]["state"] or "recovery_maximum" not in zone_sensors[1]["state"]:
        raise AssertionError("recovery zone should derive deadband recovery thresholds")
    if "stale_timeout_seconds" not in zone_sensors[2]["state"]:
        raise AssertionError("fault zone should use stale timeout helper")
    if "reconnecting" not in zone_sensors[2]["state"]:
        raise AssertionError("fault zone should treat reconnecting services as sensor faults")

    assert_equal(
        package["automation"][0]["trigger"][0]["entity_id"],
        "binary_sensor.labpulse_pressure_monitor_pressure_sensor_fault_zone",
        "sensor fault trigger entity",
    )
    assert_equal(
        package["automation"][0]["action"][0]["service"],
        "input_select.select_option",
        "fault selects alarm state",
    )
    assert_equal(package["automation"][0]["action"][0]["data"]["option"], "Sensor Fault", "fault option")
    danger_automation = package["automation"][1]
    if "danger_ratio" not in danger_automation["trigger"][0]["value_template"]:
        raise AssertionError("danger transition should use history_stats ratio")
    assert_equal(
        danger_automation["action"][0]["data"]["option"],
        "Danger",
        "danger option",
    )
    sms_action = danger_automation["action"][1]["choose"][0]["sequence"][1]
    assert_equal(sms_action["service"], "mqtt.publish", "alert publishes SMS MQTT")
    assert_equal(sms_action["data"]["topic"], SMS_SEND_TOPIC, "SMS MQTT topic")
    sms_payload = sms_action["data"]["payload"]
    for field in SMS_ALERT_PAYLOAD_FIELDS:
        if f'"{field}"' not in sms_payload:
            raise AssertionError(f"SMS payload is missing contract field {field!r}")
    sms_payload = sms_action["data"]["payload"]
    if '"service": "pressure_monitor"' not in sms_payload:
        raise AssertionError("SMS payload should include service key")
    if '"reading": "pressure"' not in sms_payload:
        raise AssertionError("SMS payload should include reading key")
    if '"state": "Danger"' not in sms_payload:
        raise AssertionError("SMS payload should include alarm state")
    if "{{ states(" not in sms_payload:
        raise AssertionError("SMS payload should preserve current reading Jinja")
    mute_condition = danger_automation["action"][1]["choose"][0]["conditions"][0]
    assert_equal(
        mute_condition["entity_id"],
        "input_boolean.labpulse_pressure_monitor_pressure_alarm_muted",
        "mute condition entity",
    )
    assert_equal(mute_condition["state"], "off", "mute condition state")

    recovery_automation = package["automation"][2]
    assert_equal(recovery_automation["trigger"][0]["platform"], "template", "recovery trigger platform")
    if "recovery_zone" not in recovery_automation["trigger"][0]["value_template"]:
        raise AssertionError("recovery trigger should watch the recovery zone template")
    assert_equal(
        recovery_automation["trigger"][0]["for"]["seconds"],
        "{{ states('input_number.labpulse_pressure_monitor_recovery_seconds') | int(120) }}",
        "recovery uses templated for",
    )
    assert_equal(recovery_automation["action"][0]["data"]["option"], "Normal", "recovery option")

    sensor_fault_clear = package["automation"][3]
    clear_yaml = yaml.safe_dump(sensor_fault_clear, sort_keys=False)
    if "persistent_notification.create" in clear_yaml or "mqtt.publish" in clear_yaml:
        raise AssertionError("sensor fault clear should update state without per-reading notifications")
    if "sensor_restored" in clear_yaml or "recovered from sensor fault" in clear_yaml:
        raise AssertionError("sensor fault clear should not emit restored/recovered messages")

    assert_equal(
        entity_map["pressure_monitor"]["pressure"]["expected_entity_id"],
        "sensor.labpulse_pressure_monitor_pressure",
        "entity map sensor",
    )
    assert_equal(
        entity_map["pressure_monitor"]["pressure"]["alarm_state"],
        "input_select.labpulse_pressure_monitor_pressure_alarm_state",
        "entity map alarm state",
    )
    assert_equal(
        entity_map["pressure_monitor"]["pressure"]["danger_ratio"],
        "sensor.labpulse_pressure_monitor_pressure_danger_ratio",
        "entity map danger ratio",
    )
    assert_equal(
        entity_map["pressure_monitor"]["pressure"]["recovery_deadband"],
        "input_number.labpulse_pressure_monitor_pressure_recovery_deadband",
        "entity map recovery deadband",
    )
    assert_equal(
        entity_map["pressure_monitor"]["alarm_controls_expanded"],
        "input_boolean.labpulse_pressure_monitor_alarm_controls_expanded",
        "entity map service alarm controls toggle",
    )


def test_dashboard_reset_and_preserve() -> None:
    """Check no-flag rendering preserves dashboard storage exactly."""

    temp_root = REFACTOR_DIR / "testing" / "tmp"
    temp_root.mkdir(exist_ok=True)
    temp_dir = temp_root / f"generator-{uuid.uuid4().hex}"
    paths = render_into(temp_dir, reset_dashboard=True)
    first_dashboard = json.loads(paths.lovelace_path.read_text(encoding="utf-8"))
    views = first_dashboard["data"]["config"]["views"]
    assert_equal(views[0]["title"], "LabPulse Monitor", "monitor dashboard title")
    assert_equal(views[1]["title"], "LabPulse Alarm Setup", "setup dashboard title")
    pressure_cards = views[0]["sections"][1]["cards"]
    assert_equal(pressure_cards[2]["name"], "Pressure", "short reading tile name")
    assert_equal(pressure_cards[2]["grid_options"]["columns"], 4, "reading third width")
    assert_equal(pressure_cards[3]["name"], "State", "state tile name")
    assert_equal(pressure_cards[4]["name"], "Muted", "mute tile name")
    setup_cards = views[1]["sections"][0]["cards"]
    assert_equal(
        setup_cards[1]["entity"],
        "input_boolean.labpulse_pressure_monitor_alarm_controls_expanded",
        "setup toggle entity",
    )
    assert_equal(setup_cards[1]["name"], "Show controls", "setup toggle name")
    assert_equal(setup_cards[2]["type"], "conditional", "service tuning conditional type")
    assert_equal(
        setup_cards[2]["conditions"][0]["entity"],
        "input_boolean.labpulse_pressure_monitor_alarm_controls_expanded",
        "service tuning condition entity",
    )
    assert_equal(setup_cards[2]["conditions"][0]["state"], "on", "service tuning condition state")
    assert_equal(setup_cards[2]["card"]["title"], "Air Pressure Sensor Hub Timing", "service tuning card title")
    assert_equal(setup_cards[3]["type"], "conditional", "reading settings conditional type")
    assert_equal(
        setup_cards[3]["conditions"][0]["entity"],
        "input_boolean.labpulse_pressure_monitor_alarm_controls_expanded",
        "reading settings condition entity",
    )
    assert_equal(setup_cards[3]["card"]["title"], "Pressure Alarm", "reading settings card title")
    setup_entities = setup_cards[3]["card"]["entities"]
    if not any(item.get("entity") == "input_number.labpulse_pressure_monitor_pressure_recovery_deadband" for item in setup_entities):
        raise AssertionError("setup dashboard should expose recovery deadband helper")

    edited_dashboard = '{"edited": true}'
    paths.lovelace_path.write_text(edited_dashboard, encoding="utf-8")
    paths.ui_automations_path.write_text("- id: user_automation\n", encoding="utf-8")
    render_into(temp_dir, reset_dashboard=False)
    assert_equal(paths.lovelace_path.read_text(encoding="utf-8"), edited_dashboard, "preserved dashboard")
    assert_equal(
        paths.ui_automations_path.read_text(encoding="utf-8"),
        "- id: user_automation\n",
        "preserved UI automations",
    )

    render_into(temp_dir, reset_dashboard=True)
    reset_dashboard = json.loads(paths.lovelace_path.read_text(encoding="utf-8"))
    assert_equal(reset_dashboard["key"], "lovelace", "reset dashboard")


TESTS = [
    ("generated package and entity map", test_generated_package_and_entity_map),
    ("dashboard reset and preserve", test_dashboard_reset_and_preserve),
]


def main() -> None:
    """Run Home Assistant generator tests."""

    print("Running Home Assistant generator tests")
    print(f"Refactor dir: {REFACTOR_DIR}")
    print()

    passed_count = 0

    for name, test_func in TESTS:
        try:
            test_func()
        except Exception as error:
            print(f"[FAIL] {name}")
            print(f"  error: {type(error).__name__}: {error}")
            print()
            continue

        print(f"[PASS] {name}")
        print()
        passed_count += 1

    total = len(TESTS)
    failed_count = total - passed_count

    print(f"Summary: {passed_count}/{total} passed, {failed_count} failed")

    if failed_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
