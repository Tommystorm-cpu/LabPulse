from pathlib import Path
import sys

sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.config import LabPulseConfig
from labpulse_common.identity import stable_id
from labpulse_homeassistant.model import build_render_model


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise AssertionError when two values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def sample_config() -> LabPulseConfig:
    """Return a small LabPulse config for render-model tests."""

    return LabPulseConfig(**{
        "mqtt": {"broker": "mosquitto"},
        "services": {
            "pump_room": {
                "enabled": True,
                "driver": "serial",
                "parser": "pump_room",
                "serial_port": "/tmp/labpulse-fake-serial/pump_room",
                "device_name": "Pump Room Sensor Hub",
                "display": {"section": "Pump Room", "icon": "mdi:water-pump", "order": 10},
                "readings": [
                    {"name": "flow1", "label": "Flow 1", "unit": "L/min"},
                    {"name": "temp0", "label": "Temperature 0", "unit": "\u00b0C"},
                ],
            },
            "disabled_service": {
                "enabled": False,
                "driver": "serial",
                "parser": "pressure",
                "serial_port": "/tmp/labpulse-fake-serial/disabled",
                "device_name": "Disabled",
                "readings": [{"name": "ignored"}],
            },
        }
    })


def test_stable_id_prefix() -> None:
    """Check stable IDs always use the LabPulse prefix."""

    assert_equal(stable_id("pump_room", "flow1"), "labpulse_pump_room_flow1", "stable id")


def test_render_model_stable_entities() -> None:
    """Check render model creates predictable Home Assistant entity IDs."""

    model = build_render_model(sample_config())
    service = model.services[0]
    flow = service.readings[0]
    temp = service.readings[1]

    assert_equal(len(model.services), 1, "enabled services")
    assert_equal(service.status_entity_id, "sensor.labpulse_pump_room_status", "status entity")
    assert_equal(flow.expected_entity_id, "sensor.labpulse_pump_room_flow1", "flow entity")
    assert_equal(flow.alarm_entity_id, "binary_sensor.labpulse_pump_room_flow1_alarm", "flow alarm")
    assert_equal(flow.active_alert_entity, "input_boolean.labpulse_pump_room_flow1_alert_active", "flow active")
    assert_equal(
        flow.minimum_threshold_entity,
        "input_number.labpulse_pump_room_flow1_minimum_threshold",
        "flow threshold",
    )
    assert_equal(
        flow.maximum_threshold_entity,
        "input_number.labpulse_pump_room_flow1_maximum_threshold",
        "flow max threshold",
    )
    assert_equal(temp.maximum_threshold_entity, "input_number.labpulse_pump_room_temp0_maximum_threshold", "temp max")


TESTS = [
    ("stable id prefix", test_stable_id_prefix),
    ("render model stable entities", test_render_model_stable_entities),
]


def main() -> None:
    """Run Home Assistant entity lookup tests."""

    print("Running Home Assistant render-model tests")
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
