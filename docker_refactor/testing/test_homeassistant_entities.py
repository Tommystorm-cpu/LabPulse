from pathlib import Path
import sys


REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_homeassistant.entities import sensor_entity_id
from labpulse_homeassistant.models import EntityRegistry


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise AssertionError when two values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_uses_exact_mqtt_unique_id() -> None:
    """Check dashboard entity lookup uses the exact MQTT unique ID."""

    registry = EntityRegistry(
        by_unique_id={
            "pump_room_temp1": "sensor.pump_room_sensor_hub_temperature_1",
        },
        mqtt_entries=[],
    )

    entity_id = sensor_entity_id(
        service_name="pump_room",
        service_config={"device_name": "Pump Room Sensor Hub"},
        reading_name="temp1",
        reading_key="pump_room_temp1",
        reading_label="Temperature 1",
        entity_registry=registry,
    )

    assert_equal(
        entity_id,
        "sensor.pump_room_sensor_hub_temperature_1",
        "resolved entity id",
    )


def test_fallback_uses_device_name_prefix() -> None:
    """Check first-run dashboard guesses match Home Assistant entity names."""

    registry = EntityRegistry(by_unique_id={}, mqtt_entries=[])

    entity_id = sensor_entity_id(
        service_name="pump_room",
        service_config={"device_name": "Pump Room Sensor Hub"},
        reading_name="flow1",
        reading_key="pump_room_flow1",
        reading_label="Flow 1",
        entity_registry=registry,
    )

    assert_equal(entity_id, "sensor.pump_room_sensor_hub_flow_1", "fallback entity id")


TESTS = [
    ("uses exact mqtt unique id", test_uses_exact_mqtt_unique_id),
    ("fallback uses device name prefix", test_fallback_uses_device_name_prefix),
]


def main() -> None:
    """Run Home Assistant entity lookup tests."""

    print("Running Home Assistant entity lookup tests")
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
