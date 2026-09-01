"""Hardware-free tests for the named JSON MQTT input driver."""

import json
import time
from types import SimpleNamespace
from unittest.mock import patch

from labpulse.common.service_config import ServiceConfig
from labpulse.hardware.driver import ConnectionLost, TransientReadError
from labpulse.hardware.drivers.mqtt_json import MqttJsonConfig, MqttJsonDriver, parse_measurement_message
from labpulse.hardware.registry import get_driver_definition


class FakeMqttClient:
    """Small Paho stand-in that exposes the callbacks used by the driver."""

    def __init__(self) -> None:
        """Start with no connection, subscription, or cleanup calls."""

        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None
        self.connected_to: tuple[str, int, int] | None = None
        self.subscribed_to: tuple[str, int] | None = None
        self.loop_started = False
        self.disconnected = False

    def connect(self, broker: str, port: int, keepalive: int) -> None:
        """Record the requested broker connection."""

        self.connected_to = (broker, port, keepalive)

    def loop_start(self) -> None:
        """Record that MQTT background networking started."""

        self.loop_started = True

    def subscribe(self, topic: str, qos: int) -> tuple[int, int]:
        """Record and accept one exact topic subscription."""

        self.subscribed_to = (topic, qos)
        return 0, 1

    def disconnect(self) -> None:
        """Record the intentional disconnect."""

        self.disconnected = True

    def loop_stop(self) -> None:
        """Record that MQTT background networking stopped."""

        self.loop_started = False


def make_driver() -> MqttJsonDriver:
    """Build the standard Triton field-selection driver used by tests."""

    config = MqttJsonConfig(
        topic="labpulse/triton/measurements",
        parameters={
            "cold_plate_temperature": "Cold Plate T(K)",
            "turbo_speed": "turbo speed(Hz)",
        },
        maximum_record_age_seconds=30,
    )
    return MqttJsonDriver("triton", config)


def message_payload(measurements: dict[str, object], recorded_at: float | None = None) -> bytes:
    """Encode one protocol-valid message with caller-supplied measurements."""

    message = {
        "protocol": "labpulse.measurements",
        "version": 1,
        "recorded_at": time.time() if recorded_at is None else recorded_at,
        "measurements": measurements,
    }
    return json.dumps(message).encode("utf-8")


def test_parse_selects_configured_names_from_a_changing_header_set() -> None:
    """Ignore extra headers and map selected raw names to stable LabPulse IDs."""

    readings = parse_measurement_message(
        message_payload({
            "new header": 123.0,
            "turbo speed(Hz)": 819,
            "Cold Plate T(K)": 0.0857,
        }),
        {
            "cold_plate_temperature": "Cold Plate T(K)",
            "turbo_speed": "turbo speed(Hz)",
        },
        maximum_record_age_seconds=30,
        received_at=time.time(),
    )

    assert dict(readings.values) == {
        "cold_plate_temperature": 0.0857,
        "turbo_speed": 819.0,
    }
    assert readings.issues == ()


def test_service_config_builds_the_registered_mqtt_json_driver() -> None:
    """Validate driver options once through the complete service boundary."""

    service = ServiceConfig.model_validate({
        "label": "Triton Fridge",
        "driver": {
            "type": "labpulse.mqtt_json",
            "options": {
                "topic": "labpulse/triton/measurements",
                "parameters": {"cold_plate_temperature": "Cold Plate T(K)"},
                "maximum_record_age_seconds": 30,
            },
        },
        "measurements": {
            "cold_plate_temperature": {
                "setups": ["cryogenics_room"],
                "unit": "K",
                "device_class": "temperature",
            }
        },
    })

    assert isinstance(service.driver.options, MqttJsonConfig)
    definition = get_driver_definition(service.driver.type)
    driver = definition.create_driver("triton", service.driver.options)
    assert isinstance(driver, MqttJsonDriver)
    assert definition.container_requirements(service.driver.options, False).devices == ()


def test_parse_retains_available_values_when_one_selected_header_is_missing() -> None:
    """Return a partial fault without discarding another valid measurement."""

    readings = parse_measurement_message(
        message_payload({"Cold Plate T(K)": 0.09}),
        {
            "cold_plate_temperature": "Cold Plate T(K)",
            "turbo_speed": "turbo speed(Hz)",
        },
        maximum_record_age_seconds=30,
        received_at=time.time(),
    )

    assert dict(readings.values) == {"cold_plate_temperature": 0.09}
    assert readings.issues[0].code == "missing_measurements"
    assert "turbo speed(Hz)" in readings.issues[0].message


def test_parse_rejects_stale_and_completely_unusable_messages() -> None:
    """Reject old snapshots and messages with no usable configured fields."""

    now = time.time()
    stale = message_payload({"Cold Plate T(K)": 0.09}, recorded_at=now - 31)
    unusable = message_payload({"Cold Plate T(K)": None, "turbo speed(Hz)": False})

    for payload, expected_message in ((stale, "seconds old"), (unusable, "none of the configured")):
        try:
            parse_measurement_message(
                payload,
                {
                    "cold_plate_temperature": "Cold Plate T(K)",
                    "turbo_speed": "turbo speed(Hz)",
                },
                maximum_record_age_seconds=30,
                received_at=now,
            )
        except ValueError as error:
            assert expected_message in str(error)
        else:
            raise AssertionError("invalid MQTT message was accepted")


def test_driver_subscribes_and_returns_each_snapshot_once() -> None:
    """Exercise the real callback boundary and consume only the newest snapshot."""

    fake_client = FakeMqttClient()
    driver = make_driver()
    with patch("labpulse.hardware.drivers.mqtt_json.mqtt.Client", return_value=fake_client):
        driver.connect()

    assert fake_client.connected_to == ("mosquitto", 1883, 60)
    assert fake_client.loop_started is True
    assert fake_client.on_connect is not None
    fake_client.on_connect(fake_client, None, None, SimpleNamespace(is_failure=False), None)
    assert fake_client.subscribed_to == ("labpulse/triton/measurements", 1)

    assert fake_client.on_message is not None
    fake_client.on_message(
        fake_client,
        None,
        SimpleNamespace(payload=message_payload({
            "Cold Plate T(K)": 0.08,
            "turbo speed(Hz)": 820,
        })),
    )
    readings = driver.read()
    assert dict(readings.values) == {"cold_plate_temperature": 0.08, "turbo_speed": 820.0}
    assert driver.read() is None

    driver.close()
    assert fake_client.disconnected is True
    assert fake_client.loop_started is False


def test_driver_reports_bad_messages_and_unexpected_disconnects() -> None:
    """Translate callback failures into the runner's expected lifecycle errors."""

    fake_client = FakeMqttClient()
    driver = make_driver()
    with patch("labpulse.hardware.drivers.mqtt_json.mqtt.Client", return_value=fake_client):
        driver.connect()

    assert fake_client.on_message is not None
    fake_client.on_message(fake_client, None, SimpleNamespace(payload=b"not JSON"))
    try:
        driver.read()
    except TransientReadError as error:
        assert "invalid JSON" in str(error)
    else:
        raise AssertionError("bad JSON did not produce TransientReadError")

    assert fake_client.on_disconnect is not None
    fake_client.on_disconnect(fake_client, None, None, "network failure", None)
    try:
        driver.read()
    except ConnectionLost as error:
        assert "network failure" in str(error)
    else:
        raise AssertionError("disconnect did not produce ConnectionLost")
