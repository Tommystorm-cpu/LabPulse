"""Regression tests for shared identity and MQTT boundaries."""

from pathlib import Path
import sys


sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.identity import entity_id, stable_id
from labpulse_common.mqtt_contracts import (
    SMS_ALERT_PAYLOAD_FIELDS,
    SMS_SEND_TOPIC,
    SMS_SUBSCRIPTION_TOPIC,
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
        "reading state topic",
    )
    assert_equal(
        service_status_topic("pump_room"),
        "home/sensor/pump_room/status",
        "status state topic",
    )
    assert_equal(
        sensor_discovery_topic("pump_room", "flow1"),
        "homeassistant/sensor/pump_room_flow1/config",
        "reading discovery topic",
    )
    assert_equal(
        status_discovery_topic("pump_room"),
        "homeassistant/sensor/pump_room_status/config",
        "status discovery topic",
    )


def test_sms_contract() -> None:
    """Check the shared alert topic and required payload fields."""

    assert_equal(SMS_SEND_TOPIC, "labpulse/sms/send", "SMS send topic")
    assert_equal(SMS_SUBSCRIPTION_TOPIC, "labpulse/sms/#", "SMS subscription topic")
    required = {
        "event",
        "service",
        "reading",
        "entity_id",
        "title",
        "message",
        "current",
        "minimum_threshold",
        "maximum_threshold",
    }
    if not required.issubset(SMS_ALERT_PAYLOAD_FIELDS):
        raise AssertionError("SMS alert contract is missing required fields")


TESTS = [
    ("stable identity contract", test_stable_identity_contract),
    ("sensor topic contract", test_sensor_topic_contract),
    ("SMS contract", test_sms_contract),
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
