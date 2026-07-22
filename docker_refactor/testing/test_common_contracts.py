"""Regression tests for shared identity and MQTT boundaries."""

from pathlib import Path
import sys

from pydantic import ValidationError


sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.identity import entity_id, stable_id
from labpulse_common.config import LabPulseConfig
from labpulse_common.mqtt_contracts import (
    SMS_ALERT_PAYLOAD_FIELDS,
    SMS_RESULT_TOPIC_PREFIX,
    SMS_SEND_TOPIC,
    SMS_STATUS_DISCOVERY_TOPIC,
    SMS_STATUS_TOPIC,
    SMS_SUBSCRIPTION_TOPIC,
    SmsRequest,
    sms_result_topic,
    sensor_discovery_topic,
    sensor_state_topic,
    service_status_topic,
    status_discovery_topic,
)


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise AssertionError when two values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_stable_identity_contract() -> None:
    """Check shared IDs reproduce established Home Assistant identities."""

    assert_equal(
        stable_id("pump_room", "flow1"),
        "labpulse_pump_room_flow1",
        "stable ID",
    )
    assert_equal(
        entity_id("sensor", "pump_room", "flow1"),
        "sensor.labpulse_pump_room_flow1",
        "sensor entity ID",
    )


def test_sensor_topic_contract() -> None:
    """Check shared topic helpers preserve established MQTT paths."""

    assert_equal(
        sensor_state_topic("pump_room", "flow1"),
        "home/sensor/pump_room/flow1/state",
        "measurement state topic",
    )
    assert_equal(
        service_status_topic("pump_room"),
        "home/sensor/pump_room/status",
        "status state topic",
    )
    assert_equal(
        sensor_discovery_topic("pump_room", "flow1"),
        "homeassistant/sensor/pump_room_flow1/config",
        "measurement discovery topic",
    )
    assert_equal(
        status_discovery_topic("pump_room"),
        "homeassistant/sensor/pump_room_status/config",
        "status discovery topic",
    )


def test_sms_contract() -> None:
    """Check the shared alert topic and required payload fields."""

    assert_equal(SMS_SEND_TOPIC, "labpulse/sms/send", "SMS send topic")
    assert_equal(SMS_SUBSCRIPTION_TOPIC, SMS_SEND_TOPIC, "SMS subscription topic")
    assert_equal(SMS_STATUS_TOPIC, "labpulse/sms/status", "SMS status topic")
    assert_equal(
        SMS_STATUS_DISCOVERY_TOPIC,
        "homeassistant/sensor/labpulse_sms_status/config",
        "SMS status discovery topic",
    )
    assert_equal(SMS_RESULT_TOPIC_PREFIX, "labpulse/sms/result", "SMS result prefix")
    assert_equal(sms_result_topic("request-1"), "labpulse/sms/result/request-1", "SMS result topic")
    required = {
        "request_id",
        "event",
        "service",
        "measurement",
        "state",
        "title",
        "message",
        "test_mode",
        "current_measurement",
    }
    if not required.issubset(SMS_ALERT_PAYLOAD_FIELDS):
        raise AssertionError("SMS alert contract is missing required fields")
    request = SmsRequest.model_validate(
        {
            "request_id": "request-1",
            "event": "test",
            "service": "manual",
            "measurement": "sms",
            "state": "Test",
            "title": "Test",
            "message": "Test message",
        }
    )
    assert_equal(request.event, "test", "validated SMS request")
    assert_equal(request.test_mode, False, "normal delivery default")
    notification = SmsRequest.model_validate(
        {
            "request_id": "notification-1",
            "event": "notification",
            "service": "labpulse",
            "measurement": "phone_book",
            "state": "Notification",
            "title": "LabPulse Phone Book Notification",
            "message": "Phone book notification",
        }
    )
    assert_equal(notification.event, "notification", "validated notification request")


def test_service_health_config_contract() -> None:
    """Validate global service-health defaults and bounded overrides."""

    base = {
        "mqtt": {"broker": "mosquitto"},
        "setups": {"test_setup": {}},
        "services": {
            "hub": {
                "driver": "serial",
                "serial_port": "/tmp/hub",
                "device_name": "Hub",
                "measurements": [{"name": "pressure", "setups": ["test_setup"]}],
            }
        },
    }
    defaulted = LabPulseConfig.model_validate(base)
    assert_equal(defaulted.service_health.fault_confirm_seconds, 10, "fault default")
    assert_equal(defaulted.service_health.recovery_confirm_seconds, 15, "recovery default")
    configured = LabPulseConfig.model_validate(
        {
            **base,
            "service_health": {
                "fault_confirm_seconds": 7,
                "recovery_confirm_seconds": 12,
            },
        }
    )
    assert_equal(configured.service_health.fault_confirm_seconds, 7, "fault override")
    try:
        LabPulseConfig.model_validate(
            {**base, "service_health": {"fault_confirm_seconds": 0}}
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("zero service-health confirmation was accepted")


TESTS = [
    ("stable identity contract", test_stable_identity_contract),
    ("sensor topic contract", test_sensor_topic_contract),
    ("SMS contract", test_sms_contract),
    ("service health config", test_service_health_config_contract),
]


def main() -> None:
    """Run shared contract regression tests."""

    print("Running shared identity and MQTT contract tests")
    print(f"Refactor dir: {REFACTOR_DIR}")
    print()

    passed = 0
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
        passed += 1

    failed = len(TESTS) - passed
    print(f"Summary: {passed}/{len(TESTS)} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
