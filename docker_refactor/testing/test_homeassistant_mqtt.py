from pathlib import Path
import json
import sys
from typing import Any


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


def make_publisher() -> HomeAssistantMqttPublisher:
    """Create a publisher wired to FakeMqttClient."""

    service_config = ServiceConfig(
        enabled=True,
        driver="serial",
        parser="pressure",
        serial_port="/tmp/labpulse-fake-serial/pressure",
        baud_rate=9600,
        device_name="Air Pressure Sensor Hub",
        metric_prefix="air_pressure",
    )
    mqtt_config = MqttConfig(broker="mosquitto", port=1883)
    publisher = HomeAssistantMqttPublisher(
        "pressure_monitor",
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
    """Check topic construction and Home Assistant unit inference."""

    publisher = make_publisher()

    assert_equal(
        publisher.state_topic("pressure_monitor_pressure"),
        "home/sensor/pressure_monitor/pressure_monitor_pressure/state",
        "state topic",
    )
    assert_equal(
        publisher.discovery_topic("pressure_monitor_pressure"),
        "homeassistant/sensor/pressure_monitor_pressure_monitor_pressure/config",
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
    assert_equal(publisher.unit_for_metric("pressure_monitor_pressure"), "bar", "pressure unit")
    assert_equal(publisher.unit_for_metric("pump_room_temp0"), "\u00b0C", "temperature unit")
    assert_equal(publisher.unit_for_metric("pump_room_roomhum"), "%", "humidity unit")
    assert_equal(publisher.unit_for_metric("pump_room_flow1"), "L/min", "flow unit")


def test_publish_discovery_once_then_readings() -> None:
    """Check discovery is retained once and state readings publish every time."""

    publisher = make_publisher()
    readings = {"pressure_monitor_pressure": 1.23}

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
        "homeassistant/sensor/pressure_monitor_pressure_monitor_pressure/config",
        "discovery topic",
    )

    payload = json.loads(str(discovery["payload"]))
    assert_equal(payload["name"], "Pressure Monitor Pressure", "entity name")
    assert_equal(payload["unit_of_measurement"], "bar", "unit")
    assert_equal(payload["device"]["name"], "Air Pressure Sensor Hub", "device name")

    assert_equal(
        first_state["topic"],
        "home/sensor/pressure_monitor/pressure_monitor_pressure/state",
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
    assert_equal(payload["icon"], "mdi:heart-pulse", "status icon")

    assert_equal(first_status["topic"], "home/sensor/pressure_monitor/status", "first status topic")
    assert_equal(first_status["payload"], "disconnected", "first status payload")
    assert_equal(first_status["retain"], True, "first status retain")
    assert_equal(second_status["payload"], "reconnecting", "second status payload")


TESTS = [
    ("connect and disconnect", test_connect_and_disconnect),
    ("topics and units", test_topics_and_units),
    ("publish discovery once then readings", test_publish_discovery_once_then_readings),
    ("publish status discovery once then status", test_publish_status_discovery_once_then_status),
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
