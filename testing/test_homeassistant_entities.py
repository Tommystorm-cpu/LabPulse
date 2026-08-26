from pathlib import Path
import sys


REFACTOR_DIR = Path(__file__).resolve().parents[1]

from labpulse.common.config import LabPulseConfig
from labpulse.common.identity import entity_id, stable_id
from labpulse.homeassistant.alarm import HomeAssistantRenderModel, build_template_context


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise AssertionError when two values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def sample_config() -> LabPulseConfig:
    """Return a small LabPulse config for identity/context tests."""

    return LabPulseConfig(**{
        "mqtt": {"broker": "mosquitto"},
        "setups": {"pump_room": {"label": "Pump Room"}},
        "services": {
            "pump_room": {
                "enabled": True,
                "driver": {
                    "type": "labpulse.serial_pipe",
                    "options": {"port": "/tmp/labpulse-fake-serial/pump_room"},
                },
                "device_name": "Pump Room Sensor Hub",
                "measurements": [
                    {"name": "flow1", "label": "Pump Room Flow", "short_label": "Flow", "setups": ["pump_room"], "unit": "L/min"},
                    {"name": "temp0", "label": "Pump Room Temperature", "short_label": "Temperature", "setups": ["pump_room"], "unit": "\u00b0C"},
                    {"name": "humidity", "label": "Pump Room Humidity", "setups": ["pump_room"], "alarmed": False, "unit": "%"},
                ],
            },
            "disabled_service": {
                "enabled": False,
                "driver": {
                    "type": "labpulse.serial_pipe",
                    "options": {"port": "/tmp/labpulse-fake-serial/disabled"},
                },
                "device_name": "Disabled",
                "measurements": [{"name": "ignored", "setups": ["pump_room"]}],
            },
        },
    })


def test_stable_id_prefix() -> None:
    """Check stable IDs always use the LabPulse prefix."""

    assert_equal(stable_id("pump_room", "flow1"), "labpulse_pump_room_flow1", "stable id")


def test_template_context_and_stable_entities() -> None:
    """Check the direct context and shared identity helper remain predictable."""

    context = build_template_context(sample_config())
    if not isinstance(context, HomeAssistantRenderModel):
        raise AssertionError("Home Assistant context is not an explicit render model")
    service = context.services[0]
    flow, temperature, humidity = service["measurements"]
    assert_equal(len(context.services), 1, "enabled services")
    assert_equal(len(context.setups), 1, "active setups")
    assert_equal(flow["setup_ids"], ("pump_room",), "setup membership")
    assert_equal(flow["label"], "Pump Room Flow", "full label")
    assert_equal(flow["short_label"], "Flow", "short contextual label")
    assert_equal(flow["threshold"]["range_min"], 0, "flow editor minimum")
    assert_equal(temperature["threshold"]["range_min"], -20, "temperature editor minimum")
    assert_equal(humidity["alarmed"], False, "explicit alarm disablement")
    assert_equal(
        tuple(measurement["name"] for _, measurement in context.alarm_measurements),
        ("flow1", "temp0"),
        "alarm-capable measurements",
    )

    expected = {
        entity_id("sensor", "pump_room", "status"): "sensor.labpulse_pump_room_status",
        entity_id("sensor", "pump_room", "flow1"): "sensor.labpulse_pump_room_flow1",
        entity_id("input_select", "pump_room", "flow1", "alarm_state"): "input_select.labpulse_pump_room_flow1_alarm_state",
        entity_id("input_boolean", "pump_room", "flow1", "alarm_controls_expanded"): "input_boolean.labpulse_pump_room_flow1_alarm_controls_expanded",
        entity_id("input_number", "pump_room", "flow1", "minimum_threshold"): "input_number.labpulse_pump_room_flow1_minimum_threshold",
        entity_id("binary_sensor", "pump_room", "flow1", "danger_zone"): "binary_sensor.labpulse_pump_room_flow1_danger_zone",
        entity_id("sensor", "pump_room", "flow1", "observed_danger_percent"): "sensor.labpulse_pump_room_flow1_observed_danger_percent",
    }
    for actual, wanted in expected.items():
        assert_equal(actual, wanted, "stable entity")
