"""Behavioral integration tests for generated Home Assistant configuration."""

from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import yaml
from jinja2 import UndefinedError

from labpulse.common.config import load_config
from labpulse.common.mqtt_contracts import (
    SMS_ALERT_PAYLOAD_FIELDS,
    SMS_SEND_TOPIC,
    UPDATE_MAINTENANCE_ACK_TOPIC,
    UPDATE_MAINTENANCE_TOPIC,
)
import labpulse.homeassistant.generator as generator
from labpulse.homeassistant.generator import main as generate_homeassistant


REPOSITORY = Path(__file__).resolve().parents[1]


def sample_config() -> dict[str, object]:
    """Return a minimal alarmed service with two measurements."""

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
                        "label": "Pressure", "setups": ["air_pressure"],
                        "unit": "bar", "device_class": "pressure",
                    },
                    "temperature": {
                        "label": "Temperature", "setups": ["air_pressure"],
                        "unit": "°C", "device_class": "temperature",
                    },
                },
            }
        },
    }


def render_into(temp_dir: Path) -> SimpleNamespace:
    """Render the sample into an isolated Home Assistant directory."""

    temp_dir.mkdir(parents=True, exist_ok=True)
    config_path = temp_dir / "config.yaml"
    config_path.write_text(yaml.safe_dump(sample_config(), sort_keys=False), encoding="utf-8")
    ha_dir = temp_dir / "homeassistant" / "config"
    paths = SimpleNamespace(
        config=config_path,
        package=ha_dir / "packages" / "labpulse_generated.yaml",
        configuration=ha_dir / "configuration.yaml",
        dashboard=ha_dir / "labpulse-dashboard.yaml",
    )
    assert generate_homeassistant([str(config_path), str(ha_dir)]) == 0
    return paths


def walk(value: object) -> Iterable[object]:
    """Yield every nested YAML object."""

    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def automation(package: dict[str, object], alias: str) -> dict[str, object]:
    """Return one automation by its public alias."""

    return next(item for item in package["automation"] if item["alias"] == alias)


def test_generated_package_exposes_alarm_lifecycle_and_sms_contract() -> None:
    """Generate helpers and one canonical automation per lifecycle transition."""

    paths = render_into(REPOSITORY / "testing" / "tmp" / f"generator-{uuid4().hex}")
    package = yaml.safe_load(paths.package.read_text(encoding="utf-8"))
    helper = "labpulse_pressure_monitor_pressure"
    required = {
        "input_select": {f"{helper}_alarm_state", f"{helper}_alarm_mode"},
        "input_number": {f"{helper}_minimum_threshold", f"{helper}_maximum_threshold"},
        "input_boolean": {
            f"{helper}_reading_notifications_muted",
            f"{helper}_availability_incident_active",
            f"{helper}_availability_notification_sent",
            f"{helper}_alarm_notification_sent",
            "labpulse_global_notifications_muted",
            "labpulse_update_maintenance",
        },
        "input_button": {f"{helper}_resend_active_alert"},
        "script": {
            "labpulse_apply_bulk_alarm_settings",
            "labpulse_open_incident",
            "labpulse_close_incident",
        },
    }
    for domain, identifiers in required.items():
        assert identifiers <= package[domain].keys()

    aliases = [item["alias"] for item in package["automation"]]
    expected = {
        "LabPulse Pressure Danger",
        "LabPulse Pressure Recovery",
        "LabPulse Pressure Reading Unavailable",
        "LabPulse Pressure Reading Available",
    }
    assert all(aliases.count(alias) == 1 for alias in expected)

    maintenance = automation(package, "LabPulse Synchronize Update Maintenance")
    assert maintenance["trigger"] == [
        {"platform": "mqtt", "topic": UPDATE_MAINTENANCE_TOPIC}
    ]
    acknowledgement = next(
        item for item in walk(maintenance)
        if isinstance(item, dict)
        and item.get("service") == "mqtt.publish"
    )
    assert acknowledgement["data"]["topic"] == UPDATE_MAINTENANCE_ACK_TOPIC
    assert acknowledgement["data"]["retain"] is True
    startup_sync = automation(
        package, "LabPulse Publish Restored Update Maintenance State"
    )
    startup_publish = next(
        item for item in walk(startup_sync)
        if isinstance(item, dict) and item.get("service") == "mqtt.publish"
    )
    assert startup_publish["data"]["topic"] == UPDATE_MAINTENANCE_TOPIC
    assert "homeassistant-startup-" in startup_publish["data"]["payload"]

    danger = automation(package, "LabPulse Pressure Danger")
    unavailable = automation(package, "LabPulse Pressure Reading Unavailable")
    resend = f"input_button.{helper}_resend_active_alert"
    for item in (danger, unavailable):
        trigger = next(value for value in item["trigger"] if value.get("id") == "resend")
        assert trigger == {
            "platform": "state",
            "id": "resend",
            "entity_id": resend,
        }

    dispatch = next(
        item for item in walk(danger)
        if isinstance(item, dict) and item.get("service") == "script.labpulse_open_incident"
    )
    payload = str(dispatch["data"]["sms_payload"])
    assert all(f'"{field}"' in payload for field in SMS_ALERT_PAYLOAD_FIELDS)
    assert "Affected setup: Air Pressure." in payload
    central_publish = next(
        item for item in walk(package["script"]["labpulse_open_incident"])
        if isinstance(item, dict) and item.get("service") == "mqtt.publish"
    )
    assert central_publish["data"]["topic"] == SMS_SEND_TOPIC
    open_incident = package["script"]["labpulse_open_incident"]["sequence"]
    maintenance_gate_index = next(
        index for index, item in enumerate(open_incident)
        if item.get("condition") == "state"
        and item.get("entity_id") == "input_boolean.labpulse_update_maintenance"
        and item.get("state") == "off"
    )
    notification_index = next(
        index for index, item in enumerate(open_incident)
        if item.get("service") == "persistent_notification.create"
    )
    sms_index = next(
        index for index, item in enumerate(open_incident)
        if item.get("service") == "mqtt.publish"
    )
    assert maintenance_gate_index < notification_index < sms_index

    close_incident = str(package["script"]["labpulse_close_incident"])
    assert "original_notification_sent" in close_incident
    assert "original_sms_requested" in close_incident
    assert "input_boolean.labpulse_update_maintenance" in close_incident

    incident_alias_suffixes = (
        " Danger", " Recovery", " Reading Unavailable", " Reading Available",
        " Service Offline", " Service Online", " Power Lost", " Power Restored",
    )
    for generated_automation in package["automation"]:
        if str(generated_automation.get("alias", "")).endswith(incident_alias_suffixes):
            assert not any(
                isinstance(item, dict)
                and item.get("service") == "persistent_notification.create"
                for item in walk(generated_automation)
            )

    assert package["input_select"][f"{helper}_alarm_state"]["options"] == ["Normal", "Danger"]
    assert "Sensor Fault" not in paths.package.read_text(encoding="utf-8")

    for alias in (
        "LabPulse Pressure Reading Unavailable",
        "LabPulse Air Pressure Sensor Hub Service Offline",
    ):
        conditions = {
            (item.get("entity_id"), item.get("state"))
            for item in walk(automation(package, alias)["action"])
            if isinstance(item, dict) and item.get("condition") == "state"
        }
        assert ("input_boolean.labpulse_update_maintenance", "off") in conditions


def test_threshold_helpers_restore_state_without_seed_files() -> None:
    """Leave editable values to Home Assistant restore-state semantics."""

    paths = render_into(REPOSITORY / "testing" / "tmp" / f"generator-{uuid4().hex}")
    package = yaml.safe_load(paths.package.read_text(encoding="utf-8"))
    assert not paths.config.with_name("alarm_defaults.json").exists()
    for suffix in ("minimum_threshold", "maximum_threshold", "recovery_deadband"):
        helper = package["input_number"][f"labpulse_pressure_monitor_pressure_{suffix}"]
        assert "initial" not in helper
    assert package["input_select"]["labpulse_pressure_monitor_pressure_alarm_mode"]["options"][0] == "Disabled"
    assert package["input_select"]["labpulse_pressure_monitor_pressure_alarm_state"]["options"][0] == "Normal"


def test_optional_reading_is_visible_without_availability_incident() -> None:
    """Keep optional telemetry and alarms while treating absence as non-actionable."""

    root = REPOSITORY / "testing" / "tmp" / f"generator-optional-{uuid4().hex}"
    data = sample_config()
    data["services"]["pressure_monitor"]["measurements"]["pressure"]["availability"] = "optional"  # type: ignore[index]
    config_path = root / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    ha_dir = root / "homeassistant" / "config"
    assert generate_homeassistant([str(config_path), str(ha_dir)]) == 0
    text = (ha_dir / "packages" / "labpulse_generated.yaml").read_text(encoding="utf-8")
    package = yaml.safe_load(text)
    helper = "labpulse_pressure_monitor_pressure"
    assert f"{helper}_reading_notifications_muted" in package["input_boolean"]
    assert f"{helper}_availability_incident_active" not in package["input_boolean"]
    assert automation(package, "LabPulse Pressure Danger")
    assert not any(
        item["alias"] == "LabPulse Pressure Reading Unavailable"
        for item in package["automation"]
    )
    availability_sensors = [
        sensor
        for block in package["template"]
        for sensor in block.get("sensor", [])
    ]
    status = next(
        sensor for sensor in availability_sensors
        if sensor["unique_id"] == f"{helper}_availability"
    )
    assert "Unavailable — optional" in status["state"]


def test_first_install_mutes_once_without_overriding_restored_state() -> None:
    """Guard the initial global mute with a restore-state marker."""

    paths = render_into(REPOSITORY / "testing" / "tmp" / f"generator-{uuid4().hex}")
    package = yaml.safe_load(paths.package.read_text(encoding="utf-8"))
    for helper in ("labpulse_global_notifications_muted", "labpulse_first_install_initialized"):
        assert "initial" not in package["input_boolean"][helper]
    initializer = automation(package, "LabPulse Initialize First Installation")
    assert initializer["condition"][0]["entity_id"] == "input_boolean.labpulse_first_install_initialized"
    assert set(initializer["action"][0]["target"]["entity_id"]) == {
        "input_boolean.labpulse_global_notifications_muted",
        "input_boolean.labpulse_first_install_initialized",
    }


def test_failed_render_preserves_managed_and_user_owned_files() -> None:
    """Install nothing when any generated artifact fails validation."""

    root = REPOSITORY / "testing" / "tmp" / f"generator-atomic-{uuid4().hex}"
    ha_dir = root / "homeassistant" / "config"
    files = tuple(
        ha_dir / name for name in (
            "configuration.yaml", "packages/labpulse_generated.yaml",
            "labpulse-dashboard.yaml", "automations.yaml", "scripts.yaml", "scenes.yaml",
        )
    )
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"sentinel:{path.name}\n", encoding="utf-8")
    config_path = root / "config.yaml"
    config_path.write_text(yaml.safe_dump(sample_config(), sort_keys=False), encoding="utf-8")

    with patch.object(generator, "_render_dashboard", side_effect=ValueError("bad dashboard")):
        try:
            generator.generate_homeassistant(load_config(config_path), ha_dir)
        except ValueError as error:
            assert str(error) == "bad dashboard"
        else:
            raise AssertionError("invalid render unexpectedly installed output")
    for path in files:
        assert path.read_text(encoding="utf-8") == f"sentinel:{path.name}\n"


def test_templates_are_strict_and_dashboard_shape_is_validated() -> None:
    """Reject missing template values and malformed dashboard roots."""

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
                raise AssertionError("malformed dashboard passed validation")
