"""End-to-end generation contracts for direct X1200 power detection."""

from pathlib import Path
import sys
from typing import Callable
from uuid import uuid4

import yaml
from pydantic import ValidationError

REFACTOR_DIR = Path(__file__).resolve().parents[1]

from labpulse.common.config import LabPulseConfig, load_config
from labpulse.common.identity import stable_id
from labpulse.common.fake_config import derive_fake_config
from labpulse.common.service_config import ServiceConfig
from labpulse.homeassistant.generator import main as generate_homeassistant


SIM_CONFIG = REFACTOR_DIR / "testing" / "ups_test_pi_config.yaml"


def test_config_validation_and_stable_identity() -> None:
    """Require direct GPIO configuration and stable live/simulated identities."""

    simulated = load_config(SIM_CONFIG).config
    service = simulated.services["ups_monitor"]
    detection = service.power_detection
    if detection is None:
        raise AssertionError("simulator has no direct power detection config")
    expected = {
        "outage_confirm_seconds": 3,
        "restore_confirm_seconds": 5,
    }
    for field, value in expected.items():
        if getattr(detection, field) != value:
            raise AssertionError(f"unexpected {field}: {getattr(detection, field)!r}")
    expected_measurements = ["voltage", "battery_level", "mains_present"]
    if list(service.measurements) != expected_measurements:
        raise AssertionError("simulator measurements are not normalized")

    live_data = yaml.safe_load(SIM_CONFIG.read_text(encoding="utf-8"))
    live_service = live_data["services"]["ups_monitor"]
    live_service["driver"] = {
        "type": "labpulse.x1200",
        "options": {
            "bus": 1,
            "address": 0x36,
            "gpio_chip": "/dev/gpiochip0",
            "gpio_line": 6,
            "mains_present_active_high": True,
        },
    }
    live = LabPulseConfig.model_validate(live_data)
    sim_service = simulated.services["ups_monitor"]
    live_service_config = live.services["ups_monitor"]
    sim_ids = [stable_id("ups_monitor", "status")] + [
        stable_id("ups_monitor", measurement_id)
        for measurement_id in sim_service.measurements
    ]
    live_ids = [stable_id("ups_monitor", "status")] + [
        stable_id("ups_monitor", measurement_id)
        for measurement_id in live_service_config.measurements
    ]
    if sim_ids != live_ids:
        raise AssertionError("live and simulated power identities differ")

    invalid = dict(live_service)
    invalid["measurements"] = {"voltage": {}, "battery_level": {}}
    try:
        ServiceConfig.model_validate(invalid)
    except ValidationError as error:
        if "mains_present" not in str(error):
            raise AssertionError(f"unexpected missing-measurement error: {error}")
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


def test_fake_hardware_preserves_power_config_identity_and_metadata() -> None:
    """Keep the real power declaration intact for runtime-level simulation."""

    live_data = yaml.safe_load(SIM_CONFIG.read_text(encoding="utf-8"))
    service = live_data["services"]["ups_monitor"]
    service["driver"] = {
        "type": "labpulse.x1200",
        "options": {
            "bus": 1,
            "address": 0x36,
            "gpio_chip": "/dev/gpiochip0",
            "gpio_line": 6,
            "mains_present_active_high": True,
        },
    }
    source = yaml.safe_dump(live_data, sort_keys=False)
    before = LabPulseConfig.model_validate(yaml.safe_load(source))
    converted_text = derive_fake_config(source)
    converted = LabPulseConfig.model_validate(yaml.safe_load(converted_text))
    fake = converted.services["ups_monitor"]
    if fake.driver.type != "labpulse.x1200":
        raise AssertionError("fake mode changed the configured UPS driver")
    if converted_text != source:
        raise AssertionError("fake mode changed the resolved source configuration")
    before_ids = [
        stable_id("ups_monitor", measurement_id)
        for measurement_id in before.services["ups_monitor"].measurements
    ]
    after_ids = [
        stable_id("ups_monitor", measurement_id)
        for measurement_id in converted.services["ups_monitor"].measurements
    ]
    if before_ids != after_ids:
        raise AssertionError("fake conversion changed power measurement identities")


def render_power() -> tuple[dict, dict, str]:
    """Generate and load one isolated power-only Home Assistant package."""

    temp = REFACTOR_DIR / "testing" / "tmp" / f"power-{uuid4().hex}"
    ha_dir = temp / "homeassistant" / "config"
    temp.mkdir(parents=True)
    config_path = temp / "config.yaml"
    config_path.write_bytes(SIM_CONFIG.read_bytes())
    result = generate_homeassistant([str(config_path), str(ha_dir)])
    if result != 0:
        raise AssertionError(f"generator returned {result}")
    package_text = (ha_dir / "packages" / "labpulse_generated.yaml").read_text(
        encoding="utf-8"
    )
    package = yaml.safe_load(package_text)
    dashboard = yaml.safe_load((ha_dir / "labpulse-dashboard.yaml").read_text(encoding="utf-8"))
    return package, dashboard, package_text


def aliases(package: dict) -> dict[str, dict]:
    """Index generated automations by their user-facing alias."""

    return {automation["alias"]: automation for automation in package["automation"]}


def test_direct_lifecycle_and_confirmation_semantics() -> None:
    """Keep power condition separate from component availability."""

    package, _, text = render_power()
    state_options = package["input_select"]["labpulse_ups_monitor_power_state"]["options"]
    if state_options != ["Mains power", "Running on battery"]:
        raise AssertionError(f"unexpected direct power states: {state_options!r}")
    helper_ids = set(package["input_boolean"])
    required = {
        "labpulse_ups_monitor_power_outage_active",
        "labpulse_ups_monitor_power_notification_sent",
        "labpulse_ups_monitor_power_sms_requested",
        "labpulse_ups_monitor_power_muted",
    }
    if not required.issubset(helper_ids):
        raise AssertionError(f"missing persistent direct-power helpers: {required-helper_ids}")
    if any("candidate" in helper for helper in helper_ids):
        raise AssertionError("obsolete candidate helpers remain")
    if "labpulse_bulk_alarm_timing_target" in package["input_select"]:
        raise AssertionError("power-only config generated an empty ordinary timing target")
    if "labpulse_apply_bulk_alarm_timing" in package.get("script", {}):
        raise AssertionError("power-only config generated an ordinary bulk timing script")
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
    if int(outage["action"][0]["delay"].get("seconds", 0)) != 3:
        raise AssertionError("outage does not require three continuous seconds")
    if int(recovery["action"][0]["delay"].get("seconds", 0)) != 5:
        raise AssertionError("recovery does not require five continuous seconds")
    outage_yaml = yaml.safe_dump(outage, sort_keys=False)
    recovery_yaml = yaml.safe_dump(recovery, sort_keys=False)
    if "labpulse_ups_monitor_power_outage_active" not in outage_yaml:
        raise AssertionError("outage does not preserve its confirmed incident")
    if "labpulse_ups_monitor_power_outage_active" not in recovery_yaml:
        raise AssertionError("recovery can fire without a confirmed outage")
    if "outage_start" not in outage_yaml:
        raise AssertionError("outage does not record its confirmed start")
    if "as_timestamp(now()) - outage_start" not in recovery_yaml:
        raise AssertionError("recovery does not calculate outage duration")
    if "Sensor Fault" in text or "sensor_fault" in text:
        raise AssertionError("power condition still contains availability fault state")


def test_power_missing_reading_and_sms_contract() -> None:
    """Use common reading incidents and central delivery for power inputs."""

    package, _, text = render_power()
    automation = aliases(package)
    required_aliases = {
        "LabPulse External Power Present Reading Missing",
        "LabPulse External Power Present Reading Restored",
        "LabPulse UPS Monitor Outage Confirm",
        "LabPulse UPS Monitor Recovery Confirm",
    }
    if not required_aliases.issubset(automation):
        raise AssertionError(f"missing restart/fault rules: {required_aliases-set(automation)}")
    template_binary = [
        sensor
        for block in package["template"]
        for sensor in block.get("binary_sensor", [])
    ]
    by_name = {sensor["name"]: sensor for sensor in template_binary}
    service_offline = by_name["labpulse_ups_monitor_service_offline"]
    mains = by_name["labpulse_ups_monitor_power_mains_present"]
    reading_available = by_name["labpulse_ups_monitor_mains_present_reading_available"]
    if "gpio_fault" in service_offline["state"]:
        raise AssertionError("X1200 component GPIO fault became a whole-service outage")
    if mains["state"] != "{{ states('sensor.labpulse_ups_monitor_mains_present') | float(0) >= 0.5 }}":
        raise AssertionError("mains-present template does not normalize raw GPIO")
    if "is_number" not in reading_available["state"]:
        raise AssertionError("raw GPIO availability is not classified independently")

    notification_rules = [
        automation["LabPulse UPS Monitor Outage Confirm"],
        automation["LabPulse UPS Monitor Recovery Confirm"],
        automation["LabPulse External Power Present Reading Missing"],
        automation["LabPulse External Power Present Reading Restored"],
    ]
    for rule in notification_rules:
        rendered = yaml.safe_dump(rule, sort_keys=False)
        if "input_boolean.labpulse_notification_test_mode" not in rendered:
            raise AssertionError(f"{rule['alias']} bypasses test-mode routing")
        if '"test_mode"' not in str(rule):
            raise AssertionError(f"{rule['alias']} omits SMS test_mode")
        if "Monitoring context: Dedicated power monitoring." not in str(rule):
            raise AssertionError(f"{rule['alias']} omits setup notification context")

        if "script.labpulse_" not in rendered:
            raise AssertionError(f"{rule['alias']} bypasses central delivery")
    notification_text = "\n".join(str(rule) for rule in notification_rules)
    for field in (
        "request_id",
        "event",
        "service",
        "measurement",
        "state",
        "title",
        "message",
        "test_mode",
        "current_measurement",
    ):
        if f'"{field}"' not in notification_text:
            raise AssertionError(f"SMS payload missing field: {field}")


def test_power_dashboard_rendering() -> None:
    """Expose direct mains state, battery telemetry, history and fault state."""

    _, dashboard, _ = render_power()
    rendered = yaml.safe_dump(dashboard, sort_keys=False)
    for required in (
        "sensor.labpulse_ups_monitor_voltage",
        "sensor.labpulse_ups_monitor_battery_level",
        "sensor.labpulse_ups_monitor_mains_present",
        "input_select.labpulse_ups_monitor_power_state",
        "binary_sensor.labpulse_ups_monitor_power_mains_present",
    ):
        if required not in rendered:
            raise AssertionError(f"direct power dashboard entity missing: {required}")
    for internal in (
        "sensor.labpulse_ups_monitor_mains_present_availability",
        "input_boolean.labpulse_ups_monitor_power_outage_active",
    ):
        if internal in rendered:
            raise AssertionError(f"internal power state leaked onto dashboard: {internal}")
