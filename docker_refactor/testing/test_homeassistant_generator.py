from pathlib import Path
import json
import os
import sys
import uuid

import yaml


sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.mqtt_contracts import SMS_ALERT_PAYLOAD_FIELDS, SMS_SEND_TOPIC
import labpulse_homeassistant.cli as homeassistant_cli
from labpulse_homeassistant.cli import main as generate_homeassistant
from labpulse_homeassistant.dashboard import replace_entity_references
from labpulse_homeassistant.data_models import GeneratorPaths
from labpulse_homeassistant.entity_registry import RegistryEntry, RegistrySnapshot


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
                    },
                    {
                        "name": "temperature",
                        "label": "Temperature",
                        "unit": "°C",
                    },
                ],
            }
        }
    }


def sample_alarm_defaults(config: dict[str, object]) -> dict[str, object]:
    """Return complete defaults for the ordinary readings in a test config."""

    services: dict[str, object] = {}
    for service_name, service in config["services"].items():
        if service.get("power_detection") is not None:
            continue
        services[service_name] = {
            reading["name"]: {
                "minimum": 1.0,
                "maximum": 20.0,
                "deadband": 0.5,
            }
            for reading in service.get("readings", [])
        }

    pressure_monitor = services.get("pressure_monitor")
    if pressure_monitor is not None:
        if "pressure" in pressure_monitor:
            pressure_monitor["pressure"] = {
                "minimum": 2.5,
                "maximum": 8.5,
                "deadband": 0.4,
            }
        if "temperature" in pressure_monitor:
            pressure_monitor["temperature"] = {
                "minimum": 10.0,
                "maximum": 30.0,
                "deadband": 1.5,
            }

    return {"services": services}


def render_into(
    temp_dir: Path,
    reset_dashboard: bool,
    config: dict[str, object] | None = None,
) -> GeneratorPaths:
    """Render sample Home Assistant files into a temporary directory."""

    temp_dir.mkdir(parents=True, exist_ok=True)
    config_path = temp_dir / "config.yaml"
    rendered_config = config or sample_config()
    config_path.write_text(
        yaml.safe_dump(rendered_config, sort_keys=False),
        encoding="utf-8",
    )
    (temp_dir / "alarm_defaults.json").write_text(
        json.dumps(sample_alarm_defaults(rendered_config), indent=2) + "\n",
        encoding="utf-8",
    )
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
    assert "labpulse_pressure_monitor_required_danger_percent" in package["input_number"]
    assert "labpulse_pressure_monitor_observation_window_seconds" in package["input_number"]
    assert "labpulse_pressure_monitor_required_recovery_seconds" in package["input_number"]
    assert "labpulse_pressure_monitor_maximum_reading_age_seconds" not in package["input_number"]
    assert "labpulse_pressure_monitor_pressure_minimum_threshold" in package["input_number"]
    assert "labpulse_pressure_monitor_pressure_maximum_threshold" in package["input_number"]
    assert "labpulse_pressure_monitor_pressure_recovery_deadband" in package["input_number"]
    assert "labpulse_pressure_monitor_pressure_alarm_state" in package["input_select"]
    assert "labpulse_pressure_monitor_pressure_alarm_mode" in package["input_select"]
    assert "labpulse_pressure_monitor_pressure_alarm_controls_expanded" in package["input_boolean"]
    assert "labpulse_pressure_monitor_temperature_alarm_controls_expanded" in package["input_boolean"]
    if "labpulse_pressure_monitor_alarm_controls_expanded" in package["input_boolean"]:
        raise AssertionError("service-level alarm controls toggle should not be generated")
    assert "labpulse_pressure_monitor_pressure_alarm_muted" in package["input_boolean"]
    assert "labpulse_global_notifications_muted" in package["input_boolean"]
    assert "labpulse_notification_test_mode" in package["input_boolean"]
    assert "labpulse_pressure_monitor_alarm_defaults_initialized" in package["input_boolean"]
    reading_default_markers = [
        helper_id
        for helper_id in package["input_boolean"]
        if helper_id.startswith(
            "labpulse_pressure_monitor_pressure_alarm_defaults_initialized_"
        )
    ]
    assert_equal(len(reading_default_markers), 1, "versioned pressure defaults marker")
    for helper_type in ("input_number", "input_select", "input_boolean"):
        for helper_id, helper in package[helper_type].items():
            if "initial" in helper:
                raise AssertionError(f"persistent helper {helper_type}.{helper_id} must not set initial")
    assert_equal(
        package["input_select"]["labpulse_pressure_monitor_pressure_alarm_state"]["options"],
        ["Normal", "Danger", "Sensor Fault"],
        "alarm state options",
    )
    automation_aliases = {item.get("alias") for item in package["automation"]}
    assert "LabPulse Air Pressure Sensor Hub Initialize Alarm Defaults" in automation_aliases
    assert "LabPulse Pressure Initialize Alarm Defaults" in automation_aliases
    pressure_defaults_automation = next(
        automation
        for automation in package["automation"]
        if automation.get("alias") == "LabPulse Pressure Initialize Alarm Defaults"
    )
    seeded_values = [
        action["data"]["value"]
        for action in pressure_defaults_automation["action"][:3]
    ]
    assert_equal(seeded_values, [2.5, 8.5, 0.4], "JSON threshold seeds")
    history_sensor = package["sensor"][0]
    assert_equal(history_sensor["platform"], "history_stats", "history stats platform")
    assert_equal(history_sensor["type"], "ratio", "history stats ratio")
    assert_equal(
        history_sensor["entity_id"],
        "binary_sensor.labpulse_pressure_monitor_pressure_danger_zone",
        "history stats source",
    )
    if "observation_window_seconds" not in history_sensor["start"]:
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
    if "last_updated" in zone_sensors[2]["state"]:
        raise AssertionError("fault zone still mistakes an unchanged value for a missing sample")
    if "unavailable" not in zone_sensors[2]["state"]:
        raise AssertionError("fault zone does not consume MQTT expiry state")
    if "reconnecting" in zone_sensors[2]["state"] or "disconnected" in zone_sensors[2]["state"]:
        raise AssertionError("reconnect states should use reading age as a grace period")
    if "'error'" not in zone_sensors[2]["state"]:
        raise AssertionError("explicit service errors should remain immediate sensor faults")

    automations = package["automation"]
    automation_by_alias = {automation["alias"]: automation for automation in automations}
    transition_aliases = [
        automation["alias"]
        for automation in automations
        if automation["alias"] in {
            "LabPulse Pressure Danger",
            "LabPulse Pressure Recovery",
            "LabPulse Pressure Sensor Fault",
            "LabPulse Pressure Sensor Recovery",
        }
    ]
    assert_equal(
        transition_aliases,
        [
            "LabPulse Pressure Danger",
            "LabPulse Pressure Recovery",
            "LabPulse Pressure Sensor Fault",
            "LabPulse Pressure Sensor Recovery",
        ],
        "alarm automation order",
    )
    for alias in transition_aliases:
        transition_yaml = yaml.safe_dump(automation_by_alias[alias], sort_keys=False)
        if "input_boolean.labpulse_global_notifications_muted" not in transition_yaml:
            raise AssertionError(f"{alias} bypasses global mute")
        if "input_boolean.labpulse_notification_test_mode" not in transition_yaml:
            raise AssertionError(f"{alias} bypasses test mode")
        if "[TEST]" not in transition_yaml:
            raise AssertionError(f"{alias} lacks a visible test prefix")
    fault_automation = automation_by_alias["LabPulse Pressure Sensor Fault"]
    assert_equal(
        fault_automation["trigger"][0]["entity_id"],
        "binary_sensor.labpulse_pressure_monitor_pressure_sensor_fault_zone",
        "sensor fault trigger entity",
    )
    assert_equal(
        fault_automation["mode"],
        "restart",
        "sensor fault confirmation mode",
    )
    assert_equal(
        fault_automation["action"][0]["delay"]["seconds"],
        15,
        "sensor fault startup grace",
    )
    assert_equal(
        fault_automation["action"][1]["entity_id"],
        "binary_sensor.labpulse_pressure_monitor_pressure_sensor_fault_zone",
        "sensor fault recheck after startup grace",
    )
    assert_equal(
        fault_automation["action"][3]["service"],
        "input_select.select_option",
        "fault selects alarm state",
    )
    assert_equal(
        fault_automation["action"][3]["data"]["option"],
        "Sensor Fault",
        "fault option",
    )
    danger_automation = automation_by_alias["LabPulse Pressure Danger"]
    if "observed_danger_percent" not in danger_automation["trigger"][0]["value_template"]:
        raise AssertionError("danger transition should use observed danger percentage")
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
    if "states('sensor.labpulse_pressure_monitor_pressure')" not in sms_payload:
        raise AssertionError("SMS payload should preserve current reading Jinja")
    if "| to_json" not in sms_payload:
        raise AssertionError("SMS payload should be safely JSON encoded by Home Assistant")
    mute_condition = danger_automation["action"][1]["choose"][0]["conditions"][0]
    assert_equal(
        mute_condition["entity_id"],
        "input_boolean.labpulse_pressure_monitor_pressure_alarm_muted",
        "mute condition entity",
    )
    assert_equal(mute_condition["state"], "off", "mute condition state")
    global_mute_condition = danger_automation["action"][1]["choose"][0]["conditions"][1]
    assert_equal(
        global_mute_condition["entity_id"],
        "input_boolean.labpulse_global_notifications_muted",
        "global mute condition entity",
    )
    if '"test_mode": is_state(' not in sms_payload or "[TEST]" not in sms_payload:
        raise AssertionError("SMS payload does not carry test-mode routing and prefix")
    if "Danger threshold:" not in sms_payload or "Evidence:" not in sms_payload:
        raise AssertionError("danger SMS lacks threshold and duration evidence")
    if '"current_reading"' not in sms_payload:
        raise AssertionError("SMS payload does not use Current Reading terminology")

    recovery_automation = automation_by_alias["LabPulse Pressure Recovery"]
    assert_equal(recovery_automation["trigger"][0]["platform"], "template", "recovery trigger platform")
    if "recovery_zone" not in recovery_automation["trigger"][0]["value_template"]:
        raise AssertionError("recovery trigger should watch the recovery zone template")
    assert_equal(
        recovery_automation["trigger"][0]["for"]["seconds"],
        "{{ states('input_number.labpulse_pressure_monitor_required_recovery_seconds') | int(120) }}",
        "recovery uses templated for",
    )
    assert_equal(recovery_automation["action"][0]["data"]["option"], "Normal", "recovery option")

    sensor_recovery = automation_by_alias["LabPulse Pressure Sensor Recovery"]
    sensor_recovery_yaml = yaml.safe_dump(sensor_recovery, sort_keys=False)
    if "persistent_notification.create" not in sensor_recovery_yaml:
        raise AssertionError("sensor recovery should create a Home Assistant notification")
    if "mqtt.publish" not in sensor_recovery_yaml:
        raise AssertionError("sensor recovery should publish an SMS request")
    sensor_recovery_sms = sensor_recovery["action"][1]["choose"][0]["sequence"][1]
    assert_equal(sensor_recovery_sms["data"]["topic"], SMS_SEND_TOPIC, "sensor recovery SMS topic")
    if '"event": "recovery"' not in sensor_recovery_sms["data"]["payload"]:
        raise AssertionError("sensor recovery SMS does not use the validated recovery event")
    assert_equal(sensor_recovery["trigger"][0]["from"], "on", "recovery requires a real fault")
    if "sensor restored" not in sensor_recovery_yaml:
        raise AssertionError("sensor recovery notification has unclear wording")
    fault_yaml = yaml.safe_dump(fault_automation, sort_keys=False)
    if "Reason:" not in fault_yaml or "service status" not in fault_yaml:
        raise AssertionError("sensor fault notification does not explain its evidence")

    assert_equal(
        entity_map["pressure_monitor"]["pressure"]["effective_entity_id"],
        "sensor.labpulse_pressure_monitor_pressure",
        "entity map sensor",
    )
    assert_equal(
        entity_map["pressure_monitor"]["pressure"]["alarm_state"],
        "input_select.labpulse_pressure_monitor_pressure_alarm_state",
        "entity map alarm state",
    )
    assert_equal(
        entity_map["pressure_monitor"]["pressure"]["observed_danger_percent"],
        "sensor.labpulse_pressure_monitor_pressure_observed_danger_percent",
        "entity map observed danger",
    )
    assert_equal(
        entity_map["pressure_monitor"]["pressure"]["recovery_deadband"],
        "input_number.labpulse_pressure_monitor_pressure_recovery_deadband",
        "entity map recovery deadband",
    )
    assert_equal(
        entity_map["pressure_monitor"]["pressure"]["alarm_controls_expanded"],
        "input_boolean.labpulse_pressure_monitor_pressure_alarm_controls_expanded",
        "entity map reading alarm controls toggle",
    )


def test_changed_json_defaults_get_a_new_initializer() -> None:
    """Check a JSON edit is applied once without resetting the dashboard."""

    temp_root = REFACTOR_DIR / "testing" / "tmp"
    temp_dir = temp_root / f"generator-{uuid.uuid4().hex}"
    paths = render_into(temp_dir, reset_dashboard=True)
    first_package = yaml.safe_load(paths.package_path.read_text(encoding="utf-8"))
    prefix = "labpulse_pressure_monitor_pressure_alarm_defaults_initialized_"
    first_marker = next(
        helper_id for helper_id in first_package["input_boolean"]
        if helper_id.startswith(prefix)
    )

    defaults = sample_alarm_defaults(sample_config())
    defaults["services"]["pressure_monitor"]["pressure"]["minimum"] = 3.0
    paths.alarm_defaults_path.write_text(
        json.dumps(defaults, indent=2) + "\n",
        encoding="utf-8",
    )
    result = generate_homeassistant(
        [
            "generator",
            str(paths.config_path),
            str(paths.ha_config_dir),
            "0",
        ]
    )
    assert_equal(result, 0, "generator result after JSON edit")

    second_package = yaml.safe_load(paths.package_path.read_text(encoding="utf-8"))
    second_marker = next(
        helper_id for helper_id in second_package["input_boolean"]
        if helper_id.startswith(prefix)
    )
    if second_marker == first_marker:
        raise AssertionError("changed JSON defaults should create a new initializer")
    automation = next(
        item for item in second_package["automation"]
        if item.get("alias") == "LabPulse Pressure Initialize Alarm Defaults"
    )
    assert_equal(
        automation["action"][0]["data"]["value"],
        3.0,
        "updated JSON minimum seed",
    )


def test_missing_json_defaults_are_rejected() -> None:
    """Check enabled ordinary readings cannot silently lose alarm defaults."""

    temp_root = REFACTOR_DIR / "testing" / "tmp"
    temp_dir = temp_root / f"generator-{uuid.uuid4().hex}"
    temp_dir.mkdir(parents=True)
    config_path = temp_dir / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(sample_config(), sort_keys=False),
        encoding="utf-8",
    )
    (temp_dir / "alarm_defaults.json").write_text(
        json.dumps({"services": {"pressure_monitor": {}}}) + "\n",
        encoding="utf-8",
    )
    try:
        generate_homeassistant(
            [
                "generator",
                str(config_path),
                str(temp_dir / "homeassistant" / "config"),
                "0",
            ]
        )
    except ValueError as error:
        message = str(error)
        if "pressure_monitor.pressure" not in message:
            raise AssertionError(f"missing-reading error lacks context: {message}")
    else:
        raise AssertionError("generator accepted incomplete alarm_defaults.json")


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
    pressure_cards = views[0]["sections"][0]["cards"]
    assert_equal(
        pressure_cards[1]["heading"],
        "Air Pressure Sensor Hub",
        "single-service device subheading",
    )
    reading_list = pressure_cards[3]
    assert_equal(reading_list["type"], "entities", "reading list card type")
    assert_equal(reading_list["show_header_toggle"], False, "reading list header toggle")
    assert_equal(reading_list["grid_options"]["columns"], "full", "reading list width")
    assert_equal(
        reading_list["entities"][0]["entity"],
        "sensor.labpulse_pressure_monitor_pressure",
        "reading list entity",
    )
    assert_equal(
        reading_list["entities"][0],
        {
            "entity": "sensor.labpulse_pressure_monitor_pressure",
            "name": "Pressure",
        },
        "reading row uses short configured name without overriding icon",
    )
    if any("alarm_state" in item.get("entity", "") for item in reading_list["entities"]):
        raise AssertionError("Monitor reading list should not include alarm state")
    if any("muted" in item.get("entity", "") for item in reading_list["entities"]):
        raise AssertionError("Monitor reading list should not include mute controls")
    global_cards = views[1]["sections"][0]["cards"]
    assert_equal(global_cards[0]["heading"], "Notification Controls", "global controls heading")
    assert_equal(
        [row["entity"] for row in global_cards[1]["entities"]],
        [
            "input_boolean.labpulse_global_notifications_muted",
            "input_boolean.labpulse_notification_test_mode",
        ],
        "global notification controls",
    )
    setup_cards = views[1]["sections"][1]["cards"]
    assert_equal(setup_cards[1]["type"], "entities", "service timing card type")
    assert_equal(setup_cards[1]["title"], "Air Pressure Sensor Hub Timing", "service timing card title")
    assert_equal(
        setup_cards[2]["entity"],
        "input_boolean.labpulse_pressure_monitor_pressure_alarm_controls_expanded",
        "reading controls toggle entity",
    )
    assert_equal(setup_cards[2]["name"], "Pressure: Show Controls", "reading controls toggle name")
    assert_equal(setup_cards[3]["type"], "conditional", "reading settings conditional type")
    assert_equal(
        setup_cards[3]["conditions"][0]["entity"],
        "input_boolean.labpulse_pressure_monitor_pressure_alarm_controls_expanded",
        "reading settings condition entity",
    )
    assert_equal(setup_cards[3]["conditions"][0]["state"], "on", "reading settings condition state")
    assert_equal(setup_cards[3]["card"]["title"], "Pressure Alarm", "reading settings card title")
    setup_entities = setup_cards[3]["card"]["entities"]
    if not any(item.get("entity") == "input_boolean.labpulse_pressure_monitor_pressure_alarm_muted" for item in setup_entities):
        raise AssertionError("Alarm Setup should expose the reading mute control")
    if not any(item.get("entity") == "input_number.labpulse_pressure_monitor_pressure_recovery_deadband" for item in setup_entities):
        raise AssertionError("setup dashboard should expose recovery deadband helper")
    assert_equal(
        setup_cards[4]["entity"],
        "input_boolean.labpulse_pressure_monitor_temperature_alarm_controls_expanded",
        "second reading controls toggle entity",
    )
    assert_equal(setup_cards[5]["type"], "conditional", "second reading settings card type")
    assert_equal(
        setup_cards[5]["conditions"][0]["entity"],
        "input_boolean.labpulse_pressure_monitor_temperature_alarm_controls_expanded",
        "second reading settings condition entity",
    )

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


def test_dashboard_reset_uses_registered_overview_storage() -> None:
    """Check reset follows Home Assistant's named Overview dashboard key."""

    temp_root = REFACTOR_DIR / "testing" / "tmp"
    temp_root.mkdir(exist_ok=True)
    temp_dir = temp_root / f"generator-{uuid.uuid4().hex}"
    storage_dir = temp_dir / "homeassistant" / "config" / ".storage"
    storage_dir.mkdir(parents=True)
    registry = {
        "version": 1,
        "minor_version": 1,
        "key": "lovelace_dashboards",
        "data": {
            "items": [
                {
                    "id": "lovelace",
                    "url_path": "lovelace",
                    "mode": "storage",
                }
            ]
        },
    }
    (storage_dir / "lovelace_dashboards").write_text(
        json.dumps(registry), encoding="utf-8"
    )

    paths = render_into(temp_dir, reset_dashboard=True)
    assert_equal(paths.lovelace_path.name, "lovelace.lovelace", "named Overview path")
    dashboard = json.loads(paths.lovelace_path.read_text(encoding="utf-8"))
    assert_equal(dashboard["key"], "lovelace.lovelace", "named Overview storage key")


def test_dashboard_groups_services_by_section() -> None:
    """Check services sharing a section render under one location heading."""

    config = {
        "mqtt": {"broker": "mosquitto"},
        "services": {
            "turbo_pump": {
                "driver": "serial",
                "parser": "water",
                "serial_port": "/tmp/labpulse-fake-serial/turbo_pump",
                "device_name": "Turbo Pump Hub",
                "display": {
                    "section": "Cryogenics Room",
                    "icon": "mdi:snowflake-alert",
                    "order": 30,
                },
                "readings": [{"name": "flow1", "label": "Flow 1", "unit": "L/min"}],
            },
            "room_environment": {
                "driver": "gpio",
                "gpio_sensor": "dht11",
                "gpio_pin": "D4",
                "device_name": "Cryogenics Room Environment Sensor",
                "display": {
                    "section": "Cryogenics Room",
                    "icon": "mdi:home-thermometer",
                    "order": 50,
                },
                "readings": [
                    {"name": "temperature", "label": "Temperature", "unit": "Â°C"}
                ],
            },
        },
    }
    temp_root = REFACTOR_DIR / "testing" / "tmp"
    paths = render_into(
        temp_root / f"generator-{uuid.uuid4().hex}",
        reset_dashboard=True,
        config=config,
    )
    dashboard = json.loads(paths.lovelace_path.read_text(encoding="utf-8"))
    monitor_sections = dashboard["data"]["config"]["views"][0]["sections"]
    setup_sections = dashboard["data"]["config"]["views"][1]["sections"]

    assert_equal(len(monitor_sections), 1, "one shared location without system health")
    cards = monitor_sections[0]["cards"]
    assert_equal(cards[0]["heading"], "Cryogenics Room", "shared location heading")
    assert_equal(cards[0]["icon"], "mdi:snowflake-alert", "first service section icon")
    assert_equal(cards[1]["heading"], "Turbo Pump Hub", "first service subgroup")
    assert_equal(
        cards[4]["heading"],
        "Cryogenics Room Environment Sensor",
        "second service subgroup",
    )
    assert_equal(len(setup_sections), 3, "global controls plus per-service setup")


def test_dashboard_groups_readings_with_room_environment_last() -> None:
    """Check reading groups render in config order with room stats at the bottom."""

    config = {
        "mqtt": {"broker": "mosquitto"},
        "services": {
            "pump_room": {
                "driver": "serial",
                "parser": "water",
                "serial_port": "/tmp/labpulse-fake-serial/pump_room",
                "device_name": "Pump Room Sensor Hub",
                "display": {
                    "section": "Pump Room",
                    "icon": "mdi:water-pump",
                    "order": 20,
                },
                "readings": [
                    {"name": "flow1", "label": "Flow 1", "unit": "L/min", "group": "Flow Sensors"},
                    {"name": "temp0", "label": "Temperature 0", "unit": "C", "group": "Water Temperature Sensors"},
                    {"name": "press1", "label": "Pressure 1", "unit": "bar", "group": "Pressure Sensors"},
                    {"name": "roomtemp", "label": "Room Temperature", "unit": "C", "group": "Room Environment Sensor"},
                    {"name": "roomhum", "label": "Room Humidity", "unit": "%", "group": "Room Environment Sensor"},
                ],
            }
        },
    }
    temp_root = REFACTOR_DIR / "testing" / "tmp"
    paths = render_into(
        temp_root / f"generator-{uuid.uuid4().hex}",
        reset_dashboard=True,
        config=config,
    )
    dashboard = json.loads(paths.lovelace_path.read_text(encoding="utf-8"))
    cards = dashboard["data"]["config"]["views"][0]["sections"][0]["cards"]

    sensor_cards = [card for card in cards if card.get("type") == "entities"]
    assert_equal(
        len(sensor_cards),
        4,
        "one compact card per sensor group",
    )
    if any("title" in card for card in sensor_cards):
        raise AssertionError("Monitor sensor cards should not have large titles")
    assert_equal(
        [entity["entity"] for entity in cards[-1]["entities"]],
        [
            "sensor.labpulse_pump_room_roomtemp",
            "sensor.labpulse_pump_room_roomhum",
        ],
        "room environment readings in final list",
    )


def test_starter_dashboard_preserves_monitor_layout() -> None:
    """Check the starter config retains the agreed room/hub/sensor hierarchy."""

    config = yaml.safe_load((REFACTOR_DIR / "config.yaml").read_text(encoding="utf-8"))
    temp_root = REFACTOR_DIR / "testing" / "tmp"
    paths = render_into(
        temp_root / f"generator-{uuid.uuid4().hex}",
        reset_dashboard=True,
        config=config,
    )
    dashboard = json.loads(paths.lovelace_path.read_text(encoding="utf-8"))
    sections = dashboard["data"]["config"]["views"][0]["sections"]

    assert_equal(
        [section["cards"][0]["heading"] for section in sections],
        ["Pump Room", "Cryogenics Room", "Air Pressure"],
        "monitor room columns",
    )
    pump_cards = sections[0]["cards"]
    assert_equal(pump_cards[1]["heading"], "Pump Room Sensor Hub", "pump hub heading")
    pump_sensor_cards = [
        card for card in pump_cards if card.get("type") == "entities"
    ]
    assert_equal(
        len(pump_sensor_cards),
        4,
        "pump sensor cards",
    )
    if any("title" in card for card in pump_sensor_cards):
        raise AssertionError("Pump sensor cards should remain untitled")
    assert_equal(
        [item["entity"] for item in pump_sensor_cards[-1]["entities"]],
        [
            "sensor.labpulse_pump_room_roomtemp",
            "sensor.labpulse_pump_room_roomhum",
        ],
        "pump room sensor remains last",
    )
    assert_equal(
        [item["name"] for item in pump_sensor_cards[-1]["entities"]],
        ["Room Temperature", "Room Humidity"],
        "pump room reading prefixes",
    )

    cryogenics_cards = sections[1]["cards"]
    assert_equal(
        [
            card["heading"]
            for card in cryogenics_cards
            if card.get("heading_style") == "subtitle"
        ],
        ["Turbo Pump Hub", "Cryogenics Room Environment Sensor"],
        "cryogenics hub headings",
    )
    assert_equal(
        [item["entity"] for item in cryogenics_cards[-1]["entities"]],
        [
            "sensor.labpulse_room_environment_temperature",
            "sensor.labpulse_room_environment_humidity",
        ],
        "cryogenics room sensor last",
    )
    assert_equal(
        [item["name"] for item in cryogenics_cards[-1]["entities"]],
        ["Room Temperature", "Room Humidity"],
        "cryogenics room reading prefixes",
    )
    if "title" in cryogenics_cards[-1]:
        raise AssertionError("Cryogenics room sensor card should remain untitled")

    air_cards = sections[2]["cards"]
    assert_equal(
        air_cards[-1]["entities"],
        [
            {
                "entity": "sensor.labpulse_pressure_monitor_pressure",
                "name": "Pressure",
            }
        ],
        "air pressure sensor ownership",
    )


def test_dashboard_entity_sync_is_surgical() -> None:
    """Check sync changes complete entity references but preserves other content."""

    original = {
        "entity": "sensor.labpulse_pressure_monitor_pressure",
        "entities": ["sensor.labpulse_pressure_monitor_pressure"],
        "title": "Keep sensor.labpulse_pressure_monitor_pressure in this title",
        "nested": {"user_setting": True},
    }
    updated, count = replace_entity_references(
        original,
        {
            "sensor.labpulse_pressure_monitor_pressure":
                "sensor.user_renamed_pressure"
        },
    )

    assert_equal(count, 2, "replacement count")
    assert_equal(updated["entity"], "sensor.user_renamed_pressure", "card entity")
    assert_equal(updated["entities"], ["sensor.user_renamed_pressure"], "entity list")
    assert_equal(
        updated["title"],
        "Keep sensor.labpulse_pressure_monitor_pressure in this title",
        "embedded text preserved",
    )
    assert_equal(updated["nested"], {"user_setting": True}, "user content preserved")


def test_generator_resolves_and_syncs_entities() -> None:
    """Check the CLI applies registry IDs to YAML and an existing dashboard."""

    temp_root = REFACTOR_DIR / "testing" / "tmp"
    temp_dir = temp_root / f"generator-{uuid.uuid4().hex}"
    paths = render_into(temp_dir, reset_dashboard=True)
    snapshot = RegistrySnapshot(
        entries=[
            RegistryEntry(
                entity_id="sensor.renamed_pressure_monitor_status",
                platform="mqtt",
                unique_id="labpulse_pressure_monitor_status",
            ),
            RegistryEntry(
                entity_id="sensor.renamed_pressure",
                platform="mqtt",
                unique_id="labpulse_pressure_monitor_pressure",
            ),
            RegistryEntry(
                entity_id="sensor.labpulse_pressure_monitor_temperature",
                platform="mqtt",
                unique_id="labpulse_pressure_monitor_temperature",
            ),
        ],
        home_assistant_version="2026.7.1",
    )
    original_fetch = homeassistant_cli.fetch_entity_registry
    old_token = os.environ.get("LABPULSE_HA_TOKEN")
    homeassistant_cli.fetch_entity_registry = lambda url, token: snapshot
    os.environ["LABPULSE_HA_TOKEN"] = "test-token"
    try:
        result = generate_homeassistant(
            [
                "generator",
                str(paths.config_path),
                str(paths.ha_config_dir),
                "0",
                "1",
                "1",
                "http://127.0.0.1:8123",
            ]
        )
    finally:
        homeassistant_cli.fetch_entity_registry = original_fetch
        if old_token is None:
            os.environ.pop("LABPULSE_HA_TOKEN", None)
        else:
            os.environ["LABPULSE_HA_TOKEN"] = old_token

    assert_equal(result, 0, "resolved generator result")
    entity_map = yaml.safe_load(paths.entity_map_path.read_text(encoding="utf-8"))
    assert_equal(
        entity_map["pressure_monitor"]["pressure"]["effective_entity_id"],
        "sensor.renamed_pressure",
        "resolved entity map ID",
    )
    dashboard = json.loads(paths.lovelace_path.read_text(encoding="utf-8"))
    views = dashboard["data"]["config"]["views"]
    assert_equal(
        views[0]["sections"][0]["cards"][3]["entities"][0]["entity"],
        "sensor.renamed_pressure",
        "resolved monitor card entity",
    )
    assert_equal(
        views[1]["sections"][1]["cards"][3]["card"]["entities"][0]["entity"],
        "sensor.renamed_pressure",
        "resolved alarm setup entity",
    )


TESTS = [
    ("generated package and entity map", test_generated_package_and_entity_map),
    ("changed JSON defaults get a new initializer", test_changed_json_defaults_get_a_new_initializer),
    ("missing JSON defaults are rejected", test_missing_json_defaults_are_rejected),
    ("dashboard reset and preserve", test_dashboard_reset_and_preserve),
    ("dashboard reset uses registered Overview", test_dashboard_reset_uses_registered_overview_storage),
    ("dashboard groups services by section", test_dashboard_groups_services_by_section),
    ("dashboard groups readings with room environment last", test_dashboard_groups_readings_with_room_environment_last),
    ("starter dashboard preserves monitor layout", test_starter_dashboard_preserves_monitor_layout),
    ("dashboard entity sync is surgical", test_dashboard_entity_sync_is_surgical),
    ("generator resolves and syncs entities", test_generator_resolves_and_syncs_entities),
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
