from pathlib import Path
import json
import sys
from typing import Any

sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.config import MqttConfig, ServiceConfig
from labpulse_common.homeassistant_mqtt import HomeAssistantMqttPublisher


class FakeMqttClient:
    """Small in-memory MQTT client used to test publishing without a broker."""

    def __init__(self) -> None:
        """Create empty connection and publish tracking state."""

        self.published: list[dict[str, object]] = []
        self.connected_to: tuple[str, int, int] | None = None
        self.loop_started = False
        self.loop_stopped = False
        self.disconnected = False

    def connect(self, broker: str, port: int, keepalive: int) -> None:
        """Record MQTT connection arguments."""

        self.connected_to = (broker, port, keepalive)

    def loop_start(self) -> None:
        """Record that the MQTT network loop was started."""

        self.loop_started = True

    def publish(self, topic: str, payload: Any, retain: bool = False) -> None:
        """Record one MQTT publish call."""

        self.published.append(
            {
                "topic": topic,
                "payload": payload,
                "retain": retain,
            }
        )

    def loop_stop(self) -> None:
        """Record that the MQTT network loop was stopped."""

        self.loop_stopped = True

    def disconnect(self) -> None:
        """Record that the MQTT client was disconnected."""

        self.disconnected = True


def make_publisher(
    service_name: str = "pressure_monitor",
    parser: str = "pressure",
    device_name: str = "Air Pressure Sensor Hub",
    readings: list[dict[str, str]] | None = None,
) -> HomeAssistantMqttPublisher:
    """Create a publisher wired to FakeMqttClient."""

    service_config = ServiceConfig(
        enabled=True,
        driver="serial",
        parser=parser,
        serial_port="/tmp/labpulse-fake-serial/pressure",
        baud_rate=9600,
        device_name=device_name,
        readings=readings or [{"name": "pressure", "label": "Pressure", "unit": "bar"}],
    )
    mqtt_config = MqttConfig(broker="mosquitto", port=1883)
    publisher = HomeAssistantMqttPublisher(
        service_name,
        service_config,
        mqtt_config,
    )
    publisher.client = FakeMqttClient()
    return publisher


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise AssertionError when two values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_connect_and_disconnect() -> None:
    """Check that connect and disconnect delegate to the MQTT client."""

    publisher = make_publisher()

    publisher.connect()
    publisher.disconnect()

    assert_equal(publisher.client.connected_to, ("mosquitto", 1883, 60), "connect args")
    assert_equal(publisher.client.loop_started, True, "loop started")
    assert_equal(publisher.client.loop_stopped, True, "loop stopped")
    assert_equal(publisher.client.disconnected, True, "disconnected")


def test_topics_and_units() -> None:
    """Check topic construction and configured reading lookup."""

    publisher = make_publisher()

    assert_equal(
        publisher.state_topic("pressure"),
        "home/sensor/pressure_monitor/pressure/state",
        "state topic",
    )
    assert_equal(
        publisher.discovery_topic("pressure"),
        "homeassistant/sensor/pressure_monitor_pressure/config",
        "discovery topic",
    )
    assert_equal(
        publisher.status_topic(),
        "home/sensor/pressure_monitor/status",
        "status topic",
    )
    assert_equal(
        publisher.status_discovery_topic(),
        "homeassistant/sensor/pressure_monitor_status/config",
        "status discovery topic",
    )
    reading = publisher.reading_config_for("pressure")
    assert_equal(reading.unit if reading else None, "bar", "pressure unit")


def test_publish_discovery_once_then_readings() -> None:
    """Check discovery is retained once and state readings publish every time."""

    publisher = make_publisher()
    readings = {"pressure": 1.23}

    publisher.publish(readings)
    publisher.publish(readings)

    published = publisher.client.published
    assert_equal(len(published), 3, "publish count")

    discovery = published[0]
    first_state = published[1]
    second_state = published[2]

    assert_equal(discovery["retain"], True, "discovery retain")
    assert_equal(
        discovery["topic"],
        "homeassistant/sensor/pressure_monitor_pressure/config",
        "discovery topic",
    )

    payload = json.loads(str(discovery["payload"]))
    assert_equal(payload["name"], "Pressure", "entity name")
    assert_equal(payload["unique_id"], "labpulse_pressure_monitor_pressure", "unique id")
    assert_equal(payload["object_id"], "labpulse_pressure_monitor_pressure", "object id")
    assert_equal(payload["default_entity_id"], "sensor.labpulse_pressure_monitor_pressure", "default entity id")
    assert_equal(payload["unit_of_measurement"], "bar", "unit")
    assert_equal(payload["state_class"], "measurement", "state class")
    assert_equal(payload["device"]["name"], "Air Pressure Sensor Hub", "device name")

    assert_equal(
        first_state["topic"],
        "home/sensor/pressure_monitor/pressure/state",
        "first state topic",
    )
    assert_equal(first_state["payload"], 1.23, "first state payload")
    assert_equal(second_state["payload"], 1.23, "second state payload")


def test_publish_status_discovery_once_then_status() -> None:
    """Check service status discovery is retained once and status updates publish."""

    publisher = make_publisher()

    publisher.publish_status("disconnected")
    publisher.publish_status("reconnecting")

    published = publisher.client.published
    assert_equal(len(published), 3, "publish count")

    discovery = published[0]
    first_status = published[1]
    second_status = published[2]

    assert_equal(discovery["retain"], True, "status discovery retain")
    assert_equal(
        discovery["topic"],
        "homeassistant/sensor/pressure_monitor_status/config",
        "status discovery topic",
    )

    payload = json.loads(str(discovery["payload"]))
    assert_equal(payload["name"], "Status", "status name")
    assert_equal(payload["state_topic"], "home/sensor/pressure_monitor/status", "status state topic")
    assert_equal(payload["unique_id"], "labpulse_pressure_monitor_status", "status unique id")
    assert_equal(payload["object_id"], "labpulse_pressure_monitor_status", "status object id")
    assert_equal(payload["default_entity_id"], "sensor.labpulse_pressure_monitor_status", "status default entity id")
    assert_equal(payload["icon"], "mdi:heart-pulse", "status icon")

    assert_equal(first_status["topic"], "home/sensor/pressure_monitor/status", "first status topic")
    assert_equal(first_status["payload"], "disconnected", "first status payload")
    assert_equal(first_status["retain"], True, "first status retain")
    assert_equal(second_status["payload"], "reconnecting", "second status payload")


def test_publish_discovery_for_new_readings() -> None:
    """Check multi-format hubs discover readings that appear after first publish."""

    publisher = make_publisher(
        service_name="pump_room",
        parser="pump_room",
        device_name="Pump Room Sensor Hub",
        readings=[
            {"name": "flow1", "label": "Flow 1", "unit": "L/min"},
            {"name": "temp0", "label": "Temperature 0", "unit": "\u00b0C"},
        ],
    )

    publisher.publish({"flow1": 2.1})
    publisher.publish({"temp0": 20.5})

    published = publisher.client.published
    discovery_publishes = [
        (item["topic"], item["payload"])
        for item in published
        if str(item["topic"]).startswith("homeassistant/sensor/")
    ]

    assert_equal(
        discovery_publishes,
        [
            (
                "homeassistant/sensor/pump_room_flow1/config",
                json.dumps(
                    {
                        "name": "Flow 1",
                        "state_topic": "home/sensor/pump_room/flow1/state",
                        "unique_id": "labpulse_pump_room_flow1",
                        "object_id": "labpulse_pump_room_flow1",
                        "default_entity_id": "sensor.labpulse_pump_room_flow1",
                        "device": {
                            "identifiers": ["pump_room"],
                            "name": "Pump Room Sensor Hub",
                        },
                        "unit_of_measurement": "L/min",
                        "state_class": "measurement",
                    }
                ),
            ),
            (
                "homeassistant/sensor/pump_room_temp0/config",
                json.dumps(
                    {
                        "name": "Temperature 0",
                        "state_topic": "home/sensor/pump_room/temp0/state",
                        "unique_id": "labpulse_pump_room_temp0",
                        "object_id": "labpulse_pump_room_temp0",
                        "default_entity_id": "sensor.labpulse_pump_room_temp0",
                        "device": {
                            "identifiers": ["pump_room"],
                            "name": "Pump Room Sensor Hub",
                        },
                        "unit_of_measurement": "\u00b0C",
                        "state_class": "measurement",
                    }
                ),
            ),
        ],
        "discovery publishes",
    )


def test_ignore_unconfigured_readings() -> None:
    """Check readings not declared in config are ignored."""

    publisher = make_publisher(
        service_name="pump_room",
        parser="pump_room",
        device_name="Pump Room Sensor Hub",
        readings=[
            {"name": "flow1", "label": "Flow 1", "unit": "L/min"},
        ],
    )

    publisher.publish({"press1": 1.2, "flow1": 2.1})

    published = publisher.client.published
    assert_equal(
        [item["topic"] for item in published],
        [
            "homeassistant/sensor/pump_room_flow1/config",
            "home/sensor/pump_room/flow1/state",
        ],
        "published topics",
    )


TESTS = [
    ("connect and disconnect", test_connect_and_disconnect),
    ("topics and units", test_topics_and_units),
    ("publish discovery once then readings", test_publish_discovery_once_then_readings),
    ("publish status discovery once then status", test_publish_status_discovery_once_then_status),
    ("publish discovery for new readings", test_publish_discovery_for_new_readings),
    ("ignore unconfigured readings", test_ignore_unconfigured_readings),
]


def main() -> None:
    """Run all HomeAssistantMqttPublisher test cases."""

    print("Running HomeAssistantMqttPublisher tests")
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
