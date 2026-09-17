"""Behavioral integration tests for generated Home Assistant configuration."""

from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
import yaml
from jinja2 import UndefinedError
from pydantic import ValidationError

from labpulse.common.config import SmsConfig, load_config
from labpulse.common.mqtt_contracts import (
    SMS_ALERT_PAYLOAD_FIELDS,
    SMS_SEND_TOPIC,
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


def test_recorder_excludes_internal_entities_but_keeps_alarm_history() -> None:
    """Record useful readings and danger history without internal helper history."""

    paths = render_into(REPOSITORY / "testing" / "tmp" / f"recorder-{uuid4().hex}")
    text = paths.configuration.read_text(encoding="utf-8")
    expected = {
        "binary_sensor.labpulse_*_reading_available",
        "binary_sensor.labpulse_*_recovery_zone",
        "binary_sensor.labpulse_*_service_offline",
        "binary_sensor.labpulse_bulk_*",
        "sensor.labpulse_*_observed_danger_percent",
        "sensor.labpulse_bulk_*",
        "input_boolean.labpulse_*",
        "input_button.labpulse_*",
        "input_datetime.labpulse_*",
        "input_number.labpulse_*",
        "input_select.labpulse_*",
        "automation.labpulse_*",
        "script.labpulse_*",
    }
    assert all(f"- {pattern}" in text for pattern in expected)
    assert "\n      - sensor.labpulse_*\n" not in text
    assert "\n      - binary_sensor.labpulse_*_danger_zone\n" not in text


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
            f"{helper}_missing_reading_incident_active",
            f"{helper}_missing_reading_notification_sent",
            f"{helper}_alarm_notification_sent",
            "labpulse_global_notifications_muted",
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
        "LabPulse Pressure Reading Missing",
        "LabPulse Pressure Reading Restored",
    }
    assert all(aliases.count(alias) == 1 for alias in expected)

    assert "labpulse_update_maintenance" not in paths.package.read_text(encoding="utf-8")
    danger = automation(package, "LabPulse Pressure Danger")
    unavailable = automation(package, "LabPulse Pressure Reading Missing")
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
    notification_index = next(
        index for index, item in enumerate(open_incident)
        if any(isinstance(child, dict) and child.get("service") == "persistent_notification.create"
               for child in walk(item))
    )
    sms_index = next(
        index for index, item in enumerate(open_incident)
        if any(isinstance(child, dict) and child.get("service") == "mqtt.publish"
               for child in walk(item))
    )
    assert notification_index < sms_index
    assert "input_boolean.labpulse_global_notifications_muted" in str(open_incident[:notification_index])
    assert "delivery_allowed" in str(open_incident[:notification_index])

    close_incident = str(package["script"]["labpulse_close_incident"])
    assert "original_notification_sent" in close_incident
    assert "original_sms_requested" in close_incident

    incident_alias_suffixes = (
        " Danger", " Recovery", " Reading Missing", " Reading Restored",
        " Service Offline", " Service Working", " Power Lost", " Power Restored",
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
        "LabPulse Pressure Reading Missing",
        "LabPulse Air Pressure Sensor Hub Service Offline",
    ):
        conditions = {
            (item.get("entity_id"), item.get("state"))
            for item in walk(automation(package, alias)["action"])
            if isinstance(item, dict) and item.get("condition") == "state"
        }
        assert ("input_boolean.labpulse_update_maintenance", "off") not in conditions


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


def test_non_required_reading_is_visible_without_missing_reading_incident() -> None:
    """Keep non-required telemetry while treating its absence as acceptable."""

    root = REPOSITORY / "testing" / "tmp" / f"generator-optional-{uuid4().hex}"
    data = sample_config()
    data["services"]["pressure_monitor"]["measurements"]["pressure"]["required"] = False  # type: ignore[index]
    config_path = root / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    ha_dir = root / "homeassistant" / "config"
    assert generate_homeassistant([str(config_path), str(ha_dir)]) == 0
    text = (ha_dir / "packages" / "labpulse_generated.yaml").read_text(encoding="utf-8")
    package = yaml.safe_load(text)
    helper = "labpulse_pressure_monitor_pressure"
    assert f"{helper}_reading_notifications_muted" in package["input_boolean"]
    assert f"{helper}_missing_reading_incident_active" not in package["input_boolean"]
    assert automation(package, "LabPulse Pressure Danger")
    assert not any(
        item["alias"] == "LabPulse Pressure Reading Missing"
        for item in package["automation"]
    )
    generated_sensors = [
        sensor
        for block in package["template"]
        for sensor in block.get("sensor", [])
    ]
    assert not any(
        sensor["unique_id"] == f"{helper}_availability"
        for sensor in generated_sensors
    )
    reading_statuses = [
        sensor
        for block in package["template"]
        for sensor in block.get("binary_sensor", [])
    ]
    status = next(
        sensor for sensor in reading_statuses
        if sensor["unique_id"] == f"{helper}_reading_available"
    )
    assert status["attributes"]["required"] == "{{ false }}"


def test_calculated_measurement_attributes_are_homeassistant_templates() -> None:
    """Render source metadata and flags as template strings accepted by Home Assistant."""

    data = sample_config()
    data["custom_measurements"] = {
        "temperature_difference": {
            "setups": ["air_pressure"],
            "inputs": {
                "first": "pressure_monitor.pressure",
                "second": "pressure_monitor.temperature",
            },
            "formula": "second - first",
            "required": False,
            "alarmed": False,
        }
    }
    root = REPOSITORY / "testing" / "tmp" / f"generator-calculated-{uuid4().hex}"
    config_path = root / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    ha_dir = root / "homeassistant" / "config"
    assert generate_homeassistant([str(config_path), str(ha_dir)]) == 0
    package = yaml.safe_load((ha_dir / "packages" / "labpulse_generated.yaml").read_text(encoding="utf-8"))
    sensor = next(
        sensor
        for block in package["template"]
        for sensor in block.get("sensor", [])
        if sensor["unique_id"] == "labpulse_custom_temperature_difference"
    )
    attributes = sensor["attributes"]
    assert attributes["labpulse_custom_measurement"] == "{{ true }}"
    assert attributes["formula"] == "second - first"
    assert attributes["required"] == "{{ false }}"
    assert attributes["physical_inputs"] == (
        '{{ {"first": "pressure_monitor.pressure", '
        '"second": "pressure_monitor.temperature"} }}'
    )
    assert all(isinstance(value, str) for value in attributes.values())


def test_service_failure_notification_switch_and_fridge_wording() -> None:
    """Keep outages visible while controlling only service notification delivery."""

    root = REPOSITORY / "testing" / "tmp" / f"generator-health-{uuid4().hex}"
    data = sample_config()
    data["service_health"] = {"offline_confirm_seconds": 10, "recovery_confirm_seconds": 23}
    data["services"]["pressure_monitor"]["notify_on_service_failure"] = False  # type: ignore[index]
    data["setups"]["cryogenics_room"] = {"label": "Cryogenics Room"}  # type: ignore[index]
    data["services"]["triton_01"] = {  # type: ignore[index]
        "label": "Triton 1 Fridge",
        "service_health": {"offline_confirm_seconds": 120},
        "driver": {
            "type": "labpulse.mqtt_json",
            "options": {
                "topic": "labpulse/triton/triton-01/measurements",
                "heartbeat_topic": "labpulse/triton/triton-01/heartbeat",
            },
        },
        "measurements": {
            "cold_plate_temperature": {
                "source": "Cold Plate T(K)", "setups": ["cryogenics_room"],
            },
        },
    }
    config_path = root / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    ha_dir = root / "homeassistant" / "config"
    assert generate_homeassistant([str(config_path), str(ha_dir)]) == 0
    package = yaml.safe_load((ha_dir / "packages" / "labpulse_generated.yaml").read_text(encoding="utf-8"))

    for suffix, expected in (("Service Offline", False), ("Service Working", False)):
        hub = automation(package, f"LabPulse Air Pressure Sensor Hub {suffix}")
        dispatch = next(item for item in walk(hub) if isinstance(item, dict)
                        and item.get("service") in {
                            "script.labpulse_open_incident", "script.labpulse_close_incident",
                        })
        assert dispatch["data"]["delivery_allowed"] is expected
        fridge = automation(package, f"LabPulse Triton 1 Fridge {suffix}")
        fridge_dispatch = next(item for item in walk(fridge) if isinstance(item, dict)
                               and item.get("service") in {
                                   "script.labpulse_open_incident", "script.labpulse_close_incident",
                               })
        assert fridge_dispatch["data"]["delivery_allowed"] is True
        assert "control-PC publisher" in str(fridge_dispatch["data"])
        delay = next(item["delay"]["seconds"] for item in walk(fridge)
                     if isinstance(item, dict) and isinstance(item.get("delay"), dict))
        assert delay == (120 if suffix == "Service Offline" else 23)

    assert "labpulse_pressure_monitor_service_offline_incident_active" in package["input_boolean"]
    assert automation(package, "LabPulse Pressure Reading Missing")
    service_offline = next(
        sensor for block in package["template"]
        for sensor in block.get("binary_sensor", [])
        if sensor["unique_id"] == "labpulse_triton_01_service_offline"
    )
    assert "awaiting_heartbeat" not in service_offline["state"]


def test_every_sms_incident_requests_its_recovery_without_a_second_option() -> None:
    """Pair recovery SMS with its opening request across every incident type."""

    root = REPOSITORY / "testing" / "tmp" / f"generator-paired-{uuid4().hex}"
    ha_dir = root / "homeassistant" / "config"
    root.mkdir(parents=True)
    config_path = root / "config.yaml"
    config_path.write_bytes((REPOSITORY / "config.yaml").read_bytes())
    import shutil

    shutil.copytree(REPOSITORY / "config.d", root / "config.d")
    assert generate_homeassistant([str(config_path), str(ha_dir)]) == 0
    package = yaml.safe_load((ha_dir / "packages" / "labpulse_generated.yaml").read_text(encoding="utf-8"))
    recovery_automations = [
        item for item in package["automation"]
        if str(item.get("alias", "")).endswith((
            " Recovery", " Reading Restored", " Service Working", " Recovery Confirm",
        ))
    ]
    assert all(any(str(item.get("alias", "")).endswith(suffix)
                   for item in recovery_automations) for suffix in (
        " Recovery", " Reading Restored", " Service Working", " Recovery Confirm",
    ))
    for recovery in recovery_automations:
        dispatches = [
            item for item in walk(recovery)
            if isinstance(item, dict) and item.get("service") == "script.labpulse_close_incident"
        ]
        assert len(dispatches) == 1
        assert "recovery_sms_payload" in dispatches[0]["data"]
        assert "recovery_sms_pending_entity" not in dispatches[0]["data"]
        assert '"test_mode": is_state(' in dispatches[0]["data"]["recovery_sms_payload"]
        assert "input_boolean.labpulse_notification_test_mode" in dispatches[0]["data"]["recovery_sms_payload"]

    opening_suffixes = (
        " Danger", " Reading Missing", " Service Offline", " Outage Confirm",
    )
    for opening in package["automation"]:
        if str(opening.get("alias", "")).endswith(opening_suffixes):
            assert not any(
                isinstance(item, dict) and item.get("condition") == "state"
                and item.get("entity_id") == "input_boolean.labpulse_update_maintenance"
                for item in walk(opening["action"])
            )

    close_sequence = package["script"]["labpulse_close_incident"]["sequence"]
    sms_dispatch = next(
        (index, item) for index, item in enumerate(close_sequence)
        if item.get("choose") and any(
            isinstance(child, dict) and child.get("service") == "mqtt.publish"
            for child in walk(item)
        )
    )
    notification_dispatch = next(
        (index, item) for index, item in enumerate(close_sequence)
        if item.get("choose") and any(
            isinstance(child, dict) and child.get("service") == "persistent_notification.create"
            for child in walk(item)
        )
    )
    assert notification_dispatch[0] < sms_dispatch[0]
    assert "labpulse_update_maintenance" not in str(notification_dispatch[1])
    assert sms_dispatch[1]["choose"][0]["conditions"] == [
        {
            "condition": "template",
            "value_template": "{{ original_sms_requested and delivery_allowed | bool }}",
        },
        {
            "condition": "state",
            "entity_id": "input_boolean.labpulse_global_notifications_muted",
            "state": "off",
        },
    ]
    assert "recovery_sms_pending_entity" not in str(close_sequence)
    with pytest.raises(ValidationError):
        SmsConfig.model_validate({"send_recovery_sms": False})


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


def test_latest_readings_show_when_samples_were_received() -> None:
    """Show receipt age for available readings instead of value-change age."""

    paths = render_into(REPOSITORY / "testing" / "tmp" / f"generator-{uuid4().hex}")
    dashboard = paths.dashboard.read_text(encoding="utf-8")
    assert dashboard.count("- last-updated") == 2
