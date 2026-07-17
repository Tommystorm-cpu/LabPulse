"""End-to-end generation contracts for direct X1200 power detection."""

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
    """Require direct GPIO configuration and stable live/simulated identities."""

    simulated = load_config(SIM_CONFIG)
    service = simulated.services["ups_monitor"]
    detection = service.power_detection
    if detection is None:
        raise AssertionError("simulator has no direct power detection config")
    expected = {
        "source": "x1200_gpio",
        "gpio_chip": "/dev/gpiochip0",
        "gpio_line": 6,
        "mains_present_active_high": True,
        "outage_confirm_seconds": 3,
        "restore_confirm_seconds": 5,
    }
    for field, value in expected.items():
        if getattr(detection, field) != value:
            raise AssertionError(f"unexpected {field}: {getattr(detection, field)!r}")
    expected_readings = ["voltage", "battery_level", "mains_present"]
    if [reading.name for reading in service.readings] != expected_readings:
        raise AssertionError("simulator readings are not normalized")

    live_data = yaml.safe_load(SIM_CONFIG.read_text(encoding="utf-8"))
    live_service = live_data["services"]["ups_monitor"]
    live_service.update(
        driver="i2c",
        i2c_sensor="max17043_ups",
        i2c_bus=1,
        i2c_address=0x36,
    )
    for key in ("parser", "serial_port", "baud_rate"):
        live_service.pop(key, None)
    live = LabPulseConfig.model_validate(live_data)
    sim_model = build_render_model(simulated).services[0]
    live_model = build_render_model(live).services[0]
    sim_ids = [sim_model.status_unique_id] + [r.mqtt_unique_id for r in sim_model.readings]
    live_ids = [live_model.status_unique_id] + [r.mqtt_unique_id for r in live_model.readings]
    if sim_ids != live_ids:
        raise AssertionError("live and simulated power identities differ")

    invalid = dict(live_service)
    invalid["readings"] = [
        {"name": "voltage"},
        {"name": "battery_level"},
    ]
    try:
        ServiceConfig.model_validate(invalid)
    except ValidationError as error:
        if "mains_present" not in str(error):
            raise AssertionError(f"unexpected missing-reading error: {error}")
    else:
        raise AssertionError("power config without mains_present passed validation")

    legacy = dict(live_service)
    legacy["power_detection"] = {"source": "ups_transition_inference"}
    try:
        ServiceConfig.model_validate(legacy)
    except ValidationError:
        pass
    else:
        raise AssertionError("removed voltage-inference source still validates")

    obsolete = dict(live_service)
    obsolete["power_detection"] = {
        **live_service["power_detection"],
        "low_voltage_threshold": 4.05,
    }
    try:
        ServiceConfig.model_validate(obsolete)
    except ValidationError:
        pass
    else:
        raise AssertionError("removed voltage threshold is silently accepted")


def test_fake_usb_conversion_preserves_power_identity_and_metadata() -> None:
    """Switch transport while retaining the direct normalized mains reading."""

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
    before = build_render_model(LabPulseConfig.model_validate(yaml.safe_load(source)))
    converted_text = convert_power_service_to_fake_serial(source)
    converted = LabPulseConfig.model_validate(yaml.safe_load(converted_text))
    fake = converted.services["ups_monitor"]
    if (fake.driver, fake.parser, fake.serial_port) != (
        "serial",
        "ups_simulator",
        "/tmp/labpulse-fake-serial/ups_monitor",
    ):
        raise AssertionError("fake conversion selected the wrong UPS transport")
    after = build_render_model(converted)
    if [r.mqtt_unique_id for r in before.services[0].readings] != [
        r.mqtt_unique_id for r in after.services[0].readings
    ]:
        raise AssertionError("fake conversion changed power reading identities")


def test_fake_usb_adds_power_to_commented_starter_config() -> None:
    """Activate a complete three-reading fake UPS from the starter config."""

    starter = (REFACTOR_DIR / "config.yaml").read_text(encoding="utf-8")
    converted = LabPulseConfig.model_validate(
        yaml.safe_load(convert_power_service_to_fake_serial(starter))
    )
    service = converted.services["ups_monitor"]
    if [reading.name for reading in service.readings] != [
        "voltage",
        "battery_level",
        "mains_present",
    ]:
        raise AssertionError("starter fake UPS readings are incomplete")
    if service.power_detection is None or service.power_detection.source != "x1200_gpio":
        raise AssertionError("starter fake UPS lacks direct GPIO lifecycle metadata")


def render_power() -> tuple[dict, dict, str]:
    """Generate and load one isolated power-only Home Assistant package."""

    temp = REFACTOR_DIR / "testing" / "tmp" / f"power-{uuid4().hex}"
    ha_dir = temp / "homeassistant" / "config"
    result = generate_homeassistant(["generator", str(SIM_CONFIG), str(ha_dir), "1"])
    if result != 0:
        raise AssertionError(f"generator returned {result}")
    package_text = (ha_dir / "packages" / "labpulse_generated.yaml").read_text(
        encoding="utf-8"
    )
    package = yaml.safe_load(package_text)
    dashboard = json.loads((ha_dir / ".storage" / "lovelace").read_text(encoding="utf-8"))
    return package, dashboard, package_text


def aliases(package: dict) -> dict[str, dict]:
    """Index generated automations by their user-facing alias."""

    return {automation["alias"]: automation for automation in package["automation"]}


def test_direct_lifecycle_and_confirmation_semantics() -> None:
    """Use cancellable state timers and one persistent outage latch."""

    package, _, text = render_power()
    state_options = package["input_select"]["labpulse_ups_monitor_power_state"]["options"]
    if state_options != ["Normal", "On Battery", "Sensor Fault"]:
        raise AssertionError(f"unexpected direct power states: {state_options!r}")
    helper_ids = set(package["input_boolean"])
    required = {
        "labpulse_ups_monitor_power_outage_active",
        "labpulse_ups_monitor_power_sensor_fault_confirmed",
        "labpulse_ups_monitor_power_muted",
    }
    if not required.issubset(helper_ids):
        raise AssertionError(f"missing persistent direct-power helpers: {required-helper_ids}")
    if any("candidate" in helper for helper in helper_ids):
        raise AssertionError("obsolete candidate helpers remain")
    if package["sensor"] != []:
        raise AssertionError("voltage transition statistics remain")
    for removed in (
        "ups_transition_inference",
        "low_voltage",
        "voltage_change",
        "charge_change",
        "outage_transition",
        "recovery_transition",
        "Possible On Battery",
        "inferred",
    ):
        if removed in text:
            raise AssertionError(f"obsolete inference fragment remains: {removed}")

    automation = aliases(package)
    outage = automation["LabPulse UPS Monitor Outage Confirm"]
    recovery = automation["LabPulse UPS Monitor Recovery Confirm"]
    if int(outage["trigger"][0].get("for", {}).get("seconds", 0)) != 3:
        raise AssertionError("outage does not require three continuous seconds")
    if int(recovery["trigger"][0].get("for", {}).get("seconds", 0)) != 5:
        raise AssertionError("recovery does not require five continuous seconds")
    outage_yaml = yaml.safe_dump(outage, sort_keys=False)
    recovery_yaml = yaml.safe_dump(recovery, sort_keys=False)
    if "power_outage_active\n  state: 'off'" not in outage_yaml:
        raise AssertionError("outage warning can repeat while already active")
    if "power_outage_active\n  state: 'on'" not in recovery_yaml:
        raise AssertionError("recovery can fire without a confirmed outage")
    if "trigger.to_state.last_changed" not in outage_yaml:
        raise AssertionError("outage does not record the GPIO transition time")
    if "recovery_start - outage_start" not in recovery_yaml:
        raise AssertionError("recovery does not calculate outage duration")


def test_fault_reconciliation_and_sms_contract() -> None:
    """Keep unavailable GPIO separate from outages and preserve safe SMS routing."""

    package, _, text = render_power()
    automation = aliases(package)
    required_aliases = {
        "LabPulse UPS Monitor Power Sensor Fault",
        "LabPulse UPS Monitor Power Sensor Recovery",
        "LabPulse UPS Monitor Power Reconcile",
        "LabPulse UPS Monitor Reconcile Missed Outage",
        "LabPulse UPS Monitor Reconcile Missed Recovery",
    }
    if not required_aliases.issubset(automation):
        raise AssertionError(f"missing restart/fault rules: {required_aliases-set(automation)}")
    template_binary = package["template"][0]["binary_sensor"]
    mains, fault = template_binary
    if mains["state"] != "{{ states('sensor.labpulse_ups_monitor_mains_present') | float(0) >= 0.5 }}":
        raise AssertionError("mains-present template does not normalize raw GPIO")
    if "not is_number(raw)" not in fault["state"] or "gpio_fault" not in fault["state"]:
        raise AssertionError("unavailable GPIO is not a distinct sensor fault")
    if "power_outage_active\n  state: 'off'" not in yaml.safe_dump(
        automation["LabPulse UPS Monitor Reconcile Missed Outage"], sort_keys=False
    ):
        raise AssertionError("restart reconciliation can duplicate outage warnings")
    if "power_outage_active\n  state: 'on'" not in yaml.safe_dump(
        automation["LabPulse UPS Monitor Reconcile Missed Recovery"], sort_keys=False
    ):
        raise AssertionError("restart recovery is not gated by a prior outage")

    notification_rules = [
        automation["LabPulse UPS Monitor Outage Confirm"],
        automation["LabPulse UPS Monitor Recovery Confirm"],
        automation["LabPulse UPS Monitor Power Sensor Fault"],
        automation["LabPulse UPS Monitor Reconcile Missed Outage"],
        automation["LabPulse UPS Monitor Reconcile Missed Recovery"],
    ]
    for rule in notification_rules:
        rendered = yaml.safe_dump(rule, sort_keys=False)
        if "input_boolean.labpulse_global_notifications_muted" not in rendered:
            raise AssertionError(f"{rule['alias']} bypasses global mute")
        if "input_boolean.labpulse_notification_test_mode" not in rendered:
            raise AssertionError(f"{rule['alias']} bypasses test-mode routing")
        if '"test_mode"' not in rendered:
            raise AssertionError(f"{rule['alias']} omits SMS test_mode")
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
            raise AssertionError(f"SMS payload missing field: {field}")


def test_power_dashboard_rendering() -> None:
    """Expose direct mains state, battery telemetry, history and fault state."""

    _, dashboard, _ = render_power()
    views = dashboard["data"]["config"]["views"]
    monitor_cards = views[0]["sections"][0]["cards"]
    entities = monitor_cards[-1]["entities"]
    if [row["name"] for row in entities] != [
        "Power state",
        "External power present",
        "UPS battery voltage",
        "Last outage started",
        "Last outage duration",
    ]:
        raise AssertionError("power monitor still describes inferred evidence")
    setup_entities = views[1]["sections"][1]["cards"][1]["entities"]
    entity_ids = {
        row["entity"]
        for row in setup_entities
        if isinstance(row, dict) and "entity" in row
    }
    required = {
        "binary_sensor.labpulse_ups_monitor_power_mains_present",
        "sensor.labpulse_ups_monitor_mains_present",
        "binary_sensor.labpulse_ups_monitor_power_sensor_fault",
        "input_boolean.labpulse_ups_monitor_power_outage_active",
    }
    if not required.issubset(entity_ids):
        raise AssertionError(f"direct power diagnostics missing: {required-entity_ids}")


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("configuration and identity", test_config_validation_and_stable_identity),
    ("fake conversion", test_fake_usb_conversion_preserves_power_identity_and_metadata),
    ("starter fake UPS", test_fake_usb_adds_power_to_commented_starter_config),
    ("direct lifecycle", test_direct_lifecycle_and_confirmation_semantics),
    ("fault/restart/SMS", test_fault_reconciliation_and_sms_contract),
    ("dashboard", test_power_dashboard_rendering),
]


def main() -> None:
    """Run the standalone direct-power generation tests."""

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
