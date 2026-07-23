from pathlib import Path
import sys

sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR / "src"))

from labpulse.common.config import LabPulseConfig
from labpulse.common.identity import stable_id
from labpulse.homeassistant.render_model import RenderModel


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise AssertionError when two values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def sample_config() -> LabPulseConfig:
    """Return a small LabPulse config for render-model tests."""

    return LabPulseConfig(**{
        "mqtt": {"broker": "mosquitto"},
        "setups": {"pump_room": {"label": "Pump Room"}},
        "services": {
            "pump_room": {
                "enabled": True,
                "driver": "serial",
                "serial_port": "/tmp/labpulse-fake-serial/pump_room",
                "device_name": "Pump Room Sensor Hub",
                "measurements": [
                    {"name": "flow1", "label": "Flow 1", "setups": ["pump_room"], "unit": "L/min"},
                    {"name": "temp0", "label": "Temperature 0", "setups": ["pump_room"], "unit": "\u00b0C"},
                ],
            },
            "disabled_service": {
                "enabled": False,
                "driver": "serial",
                "serial_port": "/tmp/labpulse-fake-serial/disabled",
                "device_name": "Disabled",
                "measurements": [{"name": "ignored", "setups": ["pump_room"]}],
            },
        },
    })


def test_stable_id_prefix() -> None:
    """Check stable IDs always use the LabPulse prefix."""

    assert_equal(stable_id("pump_room", "flow1"), "labpulse_pump_room_flow1", "stable id")


def test_render_model_stable_entities() -> None:
    """Check render model creates predictable Home Assistant entity IDs."""

    model = RenderModel.from_config(sample_config())
    service = model.services[0]
    flow = service.measurements[0]
    temp = service.measurements[1]

    assert_equal(len(model.services), 1, "enabled services")
    assert_equal(len(model.setups), 1, "active setups")
    assert_equal(
        model.setups[0].muted_entity,
        "input_boolean.labpulse_setup_pump_room_notifications_muted",
        "setup mute",
    )
    assert_equal(service.status_entity.entity_id, "sensor.labpulse_pump_room_status", "status entity")
    assert_equal(flow.mqtt_entity.entity_id, "sensor.labpulse_pump_room_flow1", "flow entity")
    assert_equal(
        flow.entities["alarm_controls_expanded"],
        "input_boolean.labpulse_pump_room_flow1_alarm_controls_expanded",
        "flow alarm controls toggle",
    )
    assert_equal(
        temp.entities["alarm_controls_expanded"],
        "input_boolean.labpulse_pump_room_temp0_alarm_controls_expanded",
        "temperature alarm controls toggle",
    )
    assert_equal(flow.entities["alarm_state"], "input_select.labpulse_pump_room_flow1_alarm_state", "flow state")
    assert_equal(flow.entities["alarm_mode"], "input_select.labpulse_pump_room_flow1_alarm_mode", "flow mode")
    assert_equal(flow.entities["alarm_muted"], "input_boolean.labpulse_pump_room_flow1_alarm_muted", "flow mute")
    assert_equal(
        flow.setup_muted_entities,
        ("input_boolean.labpulse_setup_pump_room_notifications_muted",),
        "flow setup mute gates",
    )
    assert_equal(flow.entities["danger_zone"], "binary_sensor.labpulse_pump_room_flow1_danger_zone", "flow danger")
    assert_equal(flow.entities["recovery_zone"], "binary_sensor.labpulse_pump_room_flow1_recovery_zone", "flow recovery")
    assert_equal(
        flow.entities["sensor_fault_zone"],
        "binary_sensor.labpulse_pump_room_flow1_sensor_fault_zone",
        "flow fault",
    )
    assert_equal(
        flow.entities["observed_danger_percent"],
        "sensor.labpulse_pump_room_flow1_observed_danger_percent",
        "observed flow danger",
    )
    assert_equal(flow.threshold.range_min, 0, "flow editor minimum")
    assert_equal(temp.threshold.range_min, -20, "temperature editor minimum")
    assert_equal(
        flow.entities["minimum_threshold"],
        "input_number.labpulse_pump_room_flow1_minimum_threshold",
        "flow threshold",
    )
    assert_equal(
        flow.entities["maximum_threshold"],
        "input_number.labpulse_pump_room_flow1_maximum_threshold",
        "flow max threshold",
    )
    assert_equal(
        flow.entities["recovery_deadband"],
        "input_number.labpulse_pump_room_flow1_recovery_deadband",
        "flow recovery deadband",
    )
    assert_equal(temp.entities["maximum_threshold"], "input_number.labpulse_pump_room_temp0_maximum_threshold", "temp max")
    assert_equal(
        flow.entities["required_danger_percent"],
        "input_number.labpulse_pump_room_flow1_required_danger_percent",
        "required measurement danger",
    )
    assert_equal(
        flow.entities["observation_window_seconds"],
        "input_number.labpulse_pump_room_flow1_observation_window_seconds",
        "measurement observation window",
    )
    assert_equal(
        flow.entities["required_recovery_seconds"],
        "input_number.labpulse_pump_room_flow1_required_recovery_seconds",
        "required recovery",
    )
    assert_equal(
        flow.entities["alarm_timing_initialized"],
        "input_boolean.labpulse_pump_room_flow1_alarm_timing_initialized",
        "measurement timing initializer",
    )


TESTS = [
    ("stable id prefix", test_stable_id_prefix),
    ("render model stable entities", test_render_model_stable_entities),
]


def main() -> None:
    """Run Home Assistant render-model tests."""

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
