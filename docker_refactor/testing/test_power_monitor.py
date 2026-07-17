"""End-to-end generation contracts for the dedicated UPS power lifecycle."""

import json
from pathlib import Path
import sys
from typing import Callable
from uuid import uuid4

import yaml
from pydantic import ValidationError

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.config import LabPulseConfig, ServiceConfig, load_config
from labpulse_common.fake_config import convert_power_service_to_fake_serial
from labpulse_homeassistant.cli import main as generate_homeassistant
from labpulse_homeassistant.data_models import build_render_model


SIM_CONFIG = REFACTOR_DIR / "testing" / "ups_test_pi_config.yaml"


def test_config_validation_and_stable_identity() -> None:
    """Require complete UPS config while keeping live/simulated entity IDs equal."""

    simulated = load_config(SIM_CONFIG)
    detection = simulated.services["ups_monitor"].power_detection
    if detection is None:
        raise AssertionError("simulator has no transition detection config")
    expected_detection = {
        "low_voltage_threshold": 4.05,
        "outage_drop_volts": 0.05,
        "recovery_rise_volts": 0.062,
        "transition_window_seconds": 5,
        "recovery_lockout_seconds": 17,
        "outage_confirm_seconds": 3,
        "restore_confirm_seconds": 15,
    }
    for field, expected in expected_detection.items():
        if getattr(detection, field) != expected:
            raise AssertionError(f"unexpected {field}: {getattr(detection, field)!r}")
    if detection.recovery_charge_rise_percent is not None:
        raise AssertionError("uncalibrated charge recovery should remain disabled")
    sim_model = build_render_model(simulated)
    sim_service = sim_model.services[0]
    if [reading.name for reading in sim_service.readings] != ["voltage", "battery_level"]:
        raise AssertionError("simulator readings are not normalized")

    live_data = yaml.safe_load(SIM_CONFIG.read_text(encoding="utf-8"))
    service = live_data["services"]["ups_monitor"]
    service.update(
        driver="i2c",
        i2c_sensor="max17043_ups",
        i2c_bus=1,
        i2c_address=0x36,
    )
    for key in ("parser", "serial_port", "baud_rate"):
        service.pop(key, None)
    live_model = build_render_model(LabPulseConfig.model_validate(live_data))
    live_service = live_model.services[0]
    sim_ids = [sim_service.status_unique_id] + [r.mqtt_unique_id for r in sim_service.readings]
    live_ids = [live_service.status_unique_id] + [r.mqtt_unique_id for r in live_service.readings]
    if sim_ids != live_ids:
        raise AssertionError(f"live/simulator identities differ: {sim_ids!r} != {live_ids!r}")

    invalid = dict(service)
    invalid["readings"] = [{"name": "voltage"}]
    try:
        ServiceConfig.model_validate(invalid)
    except ValidationError as error:
        if "power_detection requires readings named" not in str(error):
            raise AssertionError(f"unexpected validation failure: {error}")
    else:
        raise AssertionError("incomplete UPS readings passed validation")

    wrong_interval = dict(service)
    wrong_interval["read_interval_seconds"] = 2
    try:
        ServiceConfig.model_validate(wrong_interval)
    except ValidationError as error:
        if "requires read_interval_seconds: 1" not in str(error):
            raise AssertionError(f"unexpected interval validation failure: {error}")
    else:
        raise AssertionError("non-one-second MAX17043 power interval passed validation")


def test_fake_usb_conversion_preserves_power_identity_and_metadata() -> None:
    """Switch only power transport keys while retaining user configuration."""

    live_data = yaml.safe_load(SIM_CONFIG.read_text(encoding="utf-8"))
    service = live_data["services"]["ups_monitor"]
    service.update(
        driver="i2c",
        i2c_sensor="max17043_ups",
        i2c_bus=1,
        i2c_address=0x36,
    )
    for key in ("parser", "serial_port", "baud_rate"):
        service.pop(key, None)
    source = yaml.safe_dump(live_data, sort_keys=False)
    source = source.replace(
        "    section: UPS Power\n",
        "    section: UPS Power  # preserve manual dashboard metadata\n",
    )
    before = build_render_model(LabPulseConfig.model_validate(yaml.safe_load(source)))

    converted_text = convert_power_service_to_fake_serial(source)
    converted_data = yaml.safe_load(converted_text)
    converted = LabPulseConfig.model_validate(converted_data)
    fake_service = converted.services["ups_monitor"]
    if (
        fake_service.driver != "serial"
        or fake_service.parser != "ups_simulator"
        or fake_service.serial_port != "/tmp/labpulse-fake-serial/ups_monitor"
    ):
        raise AssertionError("-fake_usb did not select the UPS simulator transport")
    for removed in (
        "i2c_sensor",
        "i2c_bus",
        "i2c_address",
        "ina219_calibration",
        "ina219_config_register",
        "ina219_current_lsb_ma",
    ):
        if removed in converted_data["services"]["ups_monitor"]:
            raise AssertionError(f"fake power config retained live-only key: {removed}")
    if "# preserve manual dashboard metadata" not in converted_text:
        raise AssertionError("fake conversion discarded a manual dashboard comment")

    after = build_render_model(converted)
    before_service, after_service = before.services[0], after.services[0]
    if before_service.label != after_service.label or before_service.section != after_service.section:
        raise AssertionError("fake conversion changed power dashboard metadata")
    if [r.mqtt_unique_id for r in before_service.readings] != [
        r.mqtt_unique_id for r in after_service.readings
    ]:
        raise AssertionError("fake conversion changed stable power identities")


def test_fake_usb_adds_power_to_commented_starter_config() -> None:
    """Turn the starter's commented UPS example into an active fake service."""

    starter_text = (REFACTOR_DIR / "config.yaml").read_text(encoding="utf-8")
    if "ups_monitor" in (yaml.safe_load(starter_text)["services"]):
        raise AssertionError("starter UPS example unexpectedly became live configuration")

    converted_text = convert_power_service_to_fake_serial(starter_text)
    converted = LabPulseConfig.model_validate(yaml.safe_load(converted_text))
    if "ups_monitor" not in converted.services:
        raise AssertionError("-fake_usb did not activate a UPS simulator service")
    service = converted.services["ups_monitor"]
    if (
        service.driver != "serial"
        or service.parser != "ups_simulator"
        or service.serial_port != "/tmp/labpulse-fake-serial/ups_monitor"
    ):
        raise AssertionError("starter fake UPS transport is incorrect")
    if [reading.name for reading in service.readings] != [
        "voltage",
        "battery_level",
    ]:
        raise AssertionError("starter fake UPS readings are incomplete")
    if service.power_detection is None:
        raise AssertionError("starter fake UPS lacks the dedicated power lifecycle")
    if "# Live UPS example for the verified MAX17043-compatible gauge" not in converted_text:
        raise AssertionError("derived fake config removed the live hardware instructions")


def render_power() -> tuple[dict, dict, str]:
    temp = REFACTOR_DIR / "testing" / "tmp" / f"power-{uuid4().hex}"
    ha_dir = temp / "homeassistant" / "config"
    result = generate_homeassistant(["generator", str(SIM_CONFIG), str(ha_dir), "1"])
    if result != 0:
        raise AssertionError(f"generator returned {result}")
    package_text = (ha_dir / "packages" / "labpulse_generated.yaml").read_text(encoding="utf-8")
    package = yaml.safe_load(package_text)
    dashboard = json.loads((ha_dir / ".storage" / "lovelace").read_text(encoding="utf-8"))
    return package, dashboard, package_text


def test_dedicated_lifecycle_and_timing_semantics() -> None:
    """Check persistent deadlines replace generic aggregate and `for:` timers."""

    package, _, text = render_power()
    statistics = package["sensor"]
    if len(statistics) != 2 or any(item.get("platform") != "statistics" for item in statistics):
        raise AssertionError(f"power transition statistics are missing: {statistics!r}")
    statistics_by_id = {item["unique_id"]: item for item in statistics}
    voltage_change = statistics_by_id["labpulse_ups_monitor_power_voltage_change"]
    if voltage_change["state_characteristic"] != "change":
        raise AssertionError("UPS voltage statistic is not a signed change")
    if voltage_change["max_age"]["seconds"] != 5:
        raise AssertionError("UPS voltage statistic ignores characterized window")
    charge_change = statistics_by_id["labpulse_ups_monitor_power_charge_change"]
    if charge_change["max_age"]["seconds"] != 120:
        raise AssertionError("UPS charge statistic ignores configured trend window")
    if "history_stats" in text or "observed_danger_percent" in text:
        raise AssertionError("power lifecycle leaked into aggregate alarm machinery")
    if "for:" in text:
        raise AssertionError("power lifecycle relies on restart-unsafe for timers")
    if set(package["input_select"]["labpulse_ups_monitor_power_state"]["options"]) != {
        "Normal", "Possible On Battery", "Sensor Fault"
    }:
        raise AssertionError("power lifecycle has unexpected states")
    datetime_ids = set(package["input_datetime"])
    required = {
        "labpulse_ups_monitor_power_outage_candidate_started",
        "labpulse_ups_monitor_power_outage_candidate_deadline",
        "labpulse_ups_monitor_power_recovery_candidate_started",
        "labpulse_ups_monitor_power_recovery_candidate_deadline",
        "labpulse_ups_monitor_power_outage_started",
        "labpulse_ups_monitor_power_last_outage_started",
    }
    if not required.issubset(datetime_ids):
        raise AssertionError(f"missing persistent timestamps: {required - datetime_ids}")
    power_helpers = [
        package["input_select"]["labpulse_ups_monitor_power_state"],
        *package["input_number"].values(),
        *(
            helper
            for helper_id, helper in package["input_boolean"].items()
            if helper_id != "labpulse_notification_test_mode"
        ),
    ]
    if any("initial" in helper for helper in power_helpers):
        raise AssertionError("power lifecycle helpers would reset instead of restore after restart")
    timing_helpers = {
        "labpulse_ups_monitor_power_outage_confirm_seconds": 3,
        "labpulse_ups_monitor_power_restore_confirm_seconds": 15,
    }
    for helper_id, configured_default in timing_helpers.items():
        if helper_id not in package["input_number"]:
            raise AssertionError(f"missing editable timing helper: {helper_id}")
        if text.count(f"input_number.{helper_id}") < 2:
            raise AssertionError(f"timing helper is not used at runtime: {helper_id}")
        if f"value: {configured_default}" not in text:
            raise AssertionError(f"timing helper is not seeded from config: {helper_id}")
    if "labpulse_ups_monitor_power_timing_initialized" not in package["input_boolean"]:
        raise AssertionError("missing persistent one-time timing initialization marker")
    if "labpulse_ups_monitor_power_sensor_fault_confirmed" not in package["input_boolean"]:
        raise AssertionError("missing persistent confirmed-fault marker")
    if "labpulse_ups_monitor_power_maximum_reading_age_seconds" in package["input_number"]:
        raise AssertionError("MQTT expiry should not be duplicated as an ineffective helper")
    for fragment in (
        "recovery_start - outage_start",
        "automation_reloaded",
        "event: start",
        "seconds: /1",
    ):
        if fragment not in text:
            raise AssertionError(f"generated lifecycle missing timing/reconcile rule: {fragment}")


def test_candidates_fault_mute_and_sms_contract() -> None:
    """Check cancellation, stale fault priority, dedicated mute, and SMS payloads."""

    package, _, text = render_power()
    aliases = {automation["alias"]: automation for automation in package["automation"]}
    for suffix in (
        "Outage Candidate Start",
        "Outage Candidate Cancel",
        "Outage Confirm",
        "Recovery Candidate Start",
        "Recovery Candidate Cancel",
        "Recovery Confirm",
        "Power Sensor Fault",
        "Power Sensor Recovery",
        "Power Reconcile",
    ):
        expected = f"LabPulse UPS Monitor {suffix}"
        if expected not in aliases:
            raise AssertionError(f"missing automation: {expected}")
    for suffix in (
        "Outage Confirm",
        "Recovery Confirm",
        "Power Sensor Fault",
        "Power Sensor Recovery",
    ):
        notification_yaml = yaml.safe_dump(
            aliases[f"LabPulse UPS Monitor {suffix}"], sort_keys=False
        )
        if "input_boolean.labpulse_global_notifications_muted" not in notification_yaml:
            raise AssertionError(f"UPS {suffix} bypasses global mute")
        if "input_boolean.labpulse_notification_test_mode" not in notification_yaml:
            raise AssertionError(f"UPS {suffix} bypasses test mode")
        if "[TEST]" not in notification_yaml or 'test_mode' not in notification_yaml:
            raise AssertionError(f"UPS {suffix} lacks test marking/routing")
        if "current_reading" not in notification_yaml:
            raise AssertionError(f"UPS {suffix} lacks Current Reading data")
    if text.count("input_boolean.labpulse_ups_monitor_power_muted") < 3:
        raise AssertionError("power mute is not applied independently to notifications")
    outage_start_yaml = yaml.safe_dump(
        aliases["LabPulse UPS Monitor Outage Candidate Start"], sort_keys=False
    )
    if "binary_sensor.labpulse_ups_monitor_power_outage_transition" not in outage_start_yaml:
        raise AssertionError("sharp voltage drop cannot start an outage candidate")
    if "binary_sensor.labpulse_ups_monitor_power_low_voltage_evidence" not in outage_start_yaml:
        raise AssertionError("absolute low-voltage fallback was removed")
    outage_confirm_yaml = yaml.safe_dump(
        aliases["LabPulse UPS Monitor Outage Confirm"], sort_keys=False
    )
    if "power_outage_transition\n  state: 'on'" in outage_confirm_yaml:
        raise AssertionError("momentary outage evidence is not latched through confirmation")
    recovery_start_yaml = yaml.safe_dump(
        aliases["LabPulse UPS Monitor Recovery Candidate Start"], sort_keys=False
    )
    if "binary_sensor.labpulse_ups_monitor_power_recovery_transition" not in recovery_start_yaml:
        raise AssertionError("characterized voltage rise cannot start recovery")
    if "+ 17" not in recovery_start_yaml or "confirmation_deadline" not in recovery_start_yaml:
        raise AssertionError("recovery does not enforce confirmation and rebound lockout")
    recovery_confirm_yaml = yaml.safe_dump(
        aliases["LabPulse UPS Monitor Recovery Confirm"], sort_keys=False
    )
    if "power_recovery_transition\n  state: 'on'" in recovery_confirm_yaml:
        raise AssertionError("momentary recovery evidence is not latched")
    fault_automation = aliases["LabPulse UPS Monitor Power Sensor Fault"]
    fault_yaml = yaml.safe_dump(fault_automation, sort_keys=False)
    if "persistent_notification.create" not in fault_yaml:
        raise AssertionError("stale UPS evidence does not create a Home Assistant notification")
    if "Reason:" not in fault_yaml or "service status" not in fault_yaml:
        raise AssertionError("UPS fault notification does not explain its evidence")
    if fault_automation.get("mode") != "restart":
        raise AssertionError("UPS fault confirmation cannot cancel a transient fault")
    if "seconds: 15" not in fault_yaml:
        raise AssertionError("UPS fault lacks a restart-transient confirmation window")
    confirmed_entity = (
        "input_boolean.labpulse_ups_monitor_power_sensor_fault_confirmed"
    )
    if confirmed_entity not in fault_yaml:
        raise AssertionError("UPS fault does not persist confirmed incident state")
    sensor_recovery = aliases["LabPulse UPS Monitor Power Sensor Recovery"]
    sensor_recovery_yaml = yaml.safe_dump(sensor_recovery, sort_keys=False)
    if "persistent_notification.create" not in sensor_recovery_yaml:
        raise AssertionError("restored UPS evidence does not create a Home Assistant notification")
    if "mqtt.publish" not in sensor_recovery_yaml:
        raise AssertionError("UPS sensor recovery should publish an SMS request")
    if confirmed_entity not in sensor_recovery_yaml:
        raise AssertionError("UPS recovery is not limited to confirmed faults")
    if sensor_recovery["action"][0].get("service") != "input_boolean.turn_off":
        raise AssertionError("UPS recovery does not clear confirmed incident state")
    state_recovery_yaml = yaml.safe_dump(sensor_recovery["action"][1], sort_keys=False)
    if "input_select.labpulse_ups_monitor_power_state" not in state_recovery_yaml:
        raise AssertionError("UPS recovery does not explicitly leave Sensor Fault")
    if "Possible On Battery" not in state_recovery_yaml or "Normal" not in state_recovery_yaml:
        raise AssertionError("UPS recovery does not reconcile both power outcomes")
    recovery_sequence = sensor_recovery["action"][2]["choose"][0]["sequence"]
    recovery_payload = recovery_sequence[1]["data"]["payload"]
    if '"event": "recovery"' not in recovery_payload or '"reading": "power"' not in recovery_payload:
        raise AssertionError("UPS sensor recovery SMS payload is not a validated power recovery")
    if sensor_recovery["trigger"][0].get("from") != "on":
        raise AssertionError("UPS sensor recovery can fire without a preceding fault")
    reconcile_yaml = yaml.safe_dump(
        aliases["LabPulse UPS Monitor Power Reconcile"], sort_keys=False
    )
    if confirmed_entity not in reconcile_yaml:
        raise AssertionError("UPS reconcile can display an unconfirmed startup fault")
    power_fault_state = package["template"][1]["binary_sensor"][0]["state"]
    if "last_updated" in power_fault_state:
        raise AssertionError("power fault still depends on value changes instead of MQTT expiry")
    if "reconnecting" in power_fault_state or "disconnected" in power_fault_state:
        raise AssertionError("UPS reconnect states bypass the evidence-age grace period")
    for field in (
        "request_id",
        "event",
        "service",
        "reading",
        "state",
        "title",
        "message",
        "test_mode",
        "current_reading",
    ):
        if f'"{field}"' not in text:
            raise AssertionError(f"SMS payload missing validated field: {field}")
    power_binary = package["template"][1]["binary_sensor"]
    if len(power_binary) != 4:
        raise AssertionError("power transition diagnostics are incomplete")
    meaning = power_binary[1]["attributes"]["meaning"]
    if "Fallback evidence" not in meaning or "mains is not measured directly" not in meaning:
        raise AssertionError("generated wording overstates direct mains measurement")
    if float(power_binary[1]["attributes"]["threshold_volts"]) != 4.05:
        raise AssertionError("generated evidence does not expose the voltage threshold")
    outage_attributes = power_binary[2]["attributes"]
    if float(outage_attributes["drop_threshold_volts"]) != 0.05:
        raise AssertionError("outage evidence omits characterized drop")
    recovery_attributes = power_binary[3]["attributes"]
    if float(recovery_attributes["rise_threshold_volts"]) != 0.062:
        raise AssertionError("recovery evidence omits characterized rise")
    if recovery_attributes["charge_recovery_enabled"] is not False:
        raise AssertionError("uncalibrated charge recovery was enabled")
    power_template_triggers = set(package["template"][1]["trigger"][0]["entity_id"])
    required_transition_triggers = {
        "sensor.labpulse_ups_monitor_voltage",
        "sensor.labpulse_ups_monitor_battery_level",
        "sensor.labpulse_ups_monitor_power_voltage_change",
        "sensor.labpulse_ups_monitor_power_charge_change",
    }
    if not required_transition_triggers.issubset(power_template_triggers):
        raise AssertionError(
            "transition templates do not follow fresh rolling statistics: "
            f"{required_transition_triggers - power_template_triggers}"
        )
    if int(power_binary[0]["attributes"]["maximum_evidence_age_seconds"]) != 15:
        raise AssertionError("generated fault diagnostics omit configured MQTT expiry")


def test_power_dashboard_rendering() -> None:
    """Check the compact dashboard exposes telemetry, lifecycle, history, and mute."""

    _, dashboard, _ = render_power()
    views = dashboard["data"]["config"]["views"]
    monitor_cards = views[0]["sections"][0]["cards"]
    gauge = monitor_cards[-2]
    if gauge != {
        "type": "gauge",
        "entity": "sensor.labpulse_ups_monitor_battery_level",
        "name": "UPS Battery Level",
        "min": 0,
        "max": 100,
        "needle": False,
        "severity": {"red": 0, "yellow": 25, "green": 50},
        "grid_options": {"columns": "full"},
    }:
        raise AssertionError(f"unexpected UPS battery gauge: {gauge!r}")
    entities = monitor_cards[-1]["entities"]
    names = [row["name"] for row in entities]
    if names != [
        "Inferred power state",
        "UPS battery voltage",
        "Last inferred outage started",
        "Last inferred outage duration",
    ]:
        raise AssertionError(f"unexpected power dashboard rows: {names!r}")
    if "title" in monitor_cards[-1]:
        raise AssertionError("power telemetry card should retain the compact untitled layout")
    history_entities = entities[-2:]
    if [row["entity"] for row in history_entities] != [
        "sensor.labpulse_ups_monitor_power_last_outage_started",
        "sensor.labpulse_ups_monitor_power_last_outage_duration",
    ]:
        raise AssertionError("outage history is not exposed through read-only sensors")
    if any(row["entity"].startswith(("input_datetime.", "input_number.")) for row in entities):
        raise AssertionError("editable outage-history storage leaked onto Monitor")
    global_entities = views[1]["sections"][0]["cards"][1]["entities"]
    if [row["entity"] for row in global_entities] != [
        "input_boolean.labpulse_global_notifications_muted",
        "input_boolean.labpulse_notification_test_mode",
    ]:
        raise AssertionError("power dashboard lacks global notification controls")
    setup_entities = views[1]["sections"][1]["cards"][1]["entities"]
    if not any(row["entity"] == "input_boolean.labpulse_ups_monitor_power_muted" for row in setup_entities):
        raise AssertionError("power alarm setup does not expose dedicated mute")
    expected_timing_rows = {
        "input_number.labpulse_ups_monitor_power_outage_confirm_seconds": "Outage confirmation time",
        "input_number.labpulse_ups_monitor_power_restore_confirm_seconds": "Recovery confirmation time",
    }
    actual_timing_rows = {
        row["entity"]: row["name"]
        for row in setup_entities
        if isinstance(row, dict) and row.get("entity") in expected_timing_rows
    }
    if actual_timing_rows != expected_timing_rows:
        raise AssertionError(f"power timing controls are missing or renamed: {actual_timing_rows!r}")
    diagnostic_entities = {
        row["entity"]
        for row in setup_entities
        if isinstance(row, dict) and "entity" in row
    }
    expected_diagnostics = {
        "sensor.labpulse_ups_monitor_power_voltage_change",
        "sensor.labpulse_ups_monitor_power_charge_change",
        "binary_sensor.labpulse_ups_monitor_power_outage_transition",
        "binary_sensor.labpulse_ups_monitor_power_recovery_transition",
        "binary_sensor.labpulse_ups_monitor_power_low_voltage_evidence",
    }
    if not expected_diagnostics.issubset(diagnostic_entities):
        raise AssertionError(
            f"power transition diagnostics missing: {expected_diagnostics - diagnostic_entities}"
        )


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("configuration and stable identity", test_config_validation_and_stable_identity),
    ("fake USB conversion preserves power service", test_fake_usb_conversion_preserves_power_identity_and_metadata),
    ("fake USB activates commented starter UPS", test_fake_usb_adds_power_to_commented_starter_config),
    ("dedicated lifecycle and timing", test_dedicated_lifecycle_and_timing_semantics),
    ("candidate/fault/mute/SMS", test_candidates_fault_mute_and_sms_contract),
    ("power dashboard rendering", test_power_dashboard_rendering),
]


def main() -> None:
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
