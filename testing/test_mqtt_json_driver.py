"""Hardware-free tests for the named JSON MQTT input driver."""

import json
import time
from types import SimpleNamespace
from unittest.mock import patch

from labpulse.common.service_config import ServiceConfig
from labpulse.common.identity import stable_id
from labpulse.hardware.driver import ConnectionLost, SourceHealth, TransientReadError
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
        self.subscriptions: list[tuple[str, int]] = []
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
        self.subscriptions.append((topic, qos))
        return 0, 1

    def disconnect(self) -> None:
        """Record the intentional disconnect."""

        self.disconnected = True

    def loop_stop(self) -> None:
        """Record that MQTT background networking stopped."""

        self.loop_started = False


def make_driver() -> MqttJsonDriver:
    """Build the standard Triton field-selection driver used by tests."""

    service = ServiceConfig.model_validate({
        "label": "Triton Fridge",
        "driver": {
            "type": "labpulse.mqtt_json",
            "options": {
                "topic": "labpulse/triton/measurements",
                "maximum_record_age_seconds": 30,
            },
        },
        "measurement_defaults": {"setups": ["cryogenics_room"], "alarmed": False},
        "measurements": {
            "cold_plate_temperature": {"source": "Cold Plate T(K)", "unit": "K"},
            "turbo_speed": {"source": "turbo speed(Hz)", "unit": "Hz"},
        },
    })
    definition = get_driver_definition(service.driver.type)
    driver = definition.create_driver("triton", service.driver.options)
    assert isinstance(driver, MqttJsonDriver)
    return driver


def make_heartbeat_driver(fridge_id: str = "triton-01") -> MqttJsonDriver:
    """Build one fridge input with independent publisher-health topics."""

    service = ServiceConfig.model_validate({
        "label": "Triton Fridge",
        "driver": {
            "type": "labpulse.mqtt_json",
            "options": {
                "topic": f"labpulse/triton/{fridge_id}/measurements",
                "heartbeat_topic": f"labpulse/triton/{fridge_id}/heartbeat",
                "heartbeat_timeout_seconds": 60,
            },
        },
        "measurements": {
            "cold_plate_temperature": {
                "source": "Cold Plate T(K)", "setups": ["cryogenics_room"],
            },
        },
    })
    driver = get_driver_definition(service.driver.type).create_driver(fridge_id, service.driver.options)
    assert isinstance(driver, MqttJsonDriver)
    return driver


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
                "maximum_record_age_seconds": 30,
            },
        },
        "measurements": {
            "cold_plate_temperature": {
                "source": "Cold Plate T(K)",
                "setups": ["cryogenics_room"],
                "unit": "K",
                "device_class": "temperature",
            }
        },
    })

    assert isinstance(service.driver.options, MqttJsonConfig)
    assert service.driver.options.measurement_sources == {
        "cold_plate_temperature": "Cold Plate T(K)"
    }
    definition = get_driver_definition(service.driver.type)
    driver = definition.create_driver("triton", service.driver.options)
    assert isinstance(driver, MqttJsonDriver)
    assert definition.container_requirements(service.driver.options, False).devices == ()


def test_service_defaults_are_resolved_and_individual_values_override_them() -> None:
    """Apply shared settings once while preserving explicit measurement choices."""

    service = ServiceConfig.model_validate({
        "label": "Triton Fridge",
        "driver": {
            "type": "labpulse.mqtt_json",
            "options": {"topic": "labpulse/triton/measurements"},
        },
        "measurement_defaults": {
            "setups": ["cryogenics_room"],
            "alarmed": False,
            "missing_confirm_seconds": 90,
        },
        "measurements": {
            "cold_plate_temperature": {
                "source": "Cold Plate T(K)",
                "unit": "K",
            },
            "condense_pressure": {
                "source": "P2 Condense (Bar)",
                "required": False,
                "alarmed": True,
                "unit": "bar",
            },
        },
    })

    cold_plate = service.measurements["cold_plate_temperature"]
    assert cold_plate.setups == ("cryogenics_room",)
    assert cold_plate.alarmed is False
    assert cold_plate.required is True
    assert cold_plate.missing_confirm_seconds == 90
    assert cold_plate.recovery_confirm_seconds == 15
    assert cold_plate.display_label("cold_plate_temperature") == "Cold Plate Temperature"

    pressure = service.measurements["condense_pressure"]
    assert pressure.alarmed is True
    assert pressure.required is False


def test_explicit_measurement_labels_override_inference() -> None:
    """Keep specialist capitalization and compact labels available to users."""

    service = ServiceConfig.model_validate({
        "label": "Triton Fridge",
        "driver": {
            "type": "labpulse.mqtt_json",
            "options": {"topic": "labpulse/triton/measurements"},
        },
        "measurements": {
            "ups_voltage": {
                "source": "UPS voltage(V)",
                "label": "UPS Battery Voltage",
                "short_label": "Battery Voltage",
                "setups": ["cryogenics_room"],
            }
        },
    })

    measurement = service.measurements["ups_voltage"]
    assert measurement.display_label("ups_voltage") == "UPS Battery Voltage"
    assert measurement.display_short_label("ups_voltage") == "Battery Voltage"


def test_label_choices_do_not_change_measurement_identity() -> None:
    """Keep stable entity identity independent of inferred or explicit wording."""

    def service_with_label(label: str | None) -> ServiceConfig:
        measurement = {
            "source": "Cold Plate T(K)",
            "setups": ["cryogenics_room"],
        }
        if label is not None:
            measurement["label"] = label
        return ServiceConfig.model_validate({
            "label": "Triton Fridge",
            "driver": {
                "type": "labpulse.mqtt_json",
                "options": {"topic": "labpulse/triton/measurements"},
            },
            "measurements": {"cold_plate_temperature": measurement},
        })

    inferred = service_with_label(None)
    explicit = service_with_label("Cold-plate thermometer")
    measurement_id = next(iter(inferred.measurements))
    assert measurement_id == next(iter(explicit.measurements))
    assert inferred.measurements[measurement_id].display_label(measurement_id) == "Cold Plate Temperature"
    assert explicit.measurements[measurement_id].display_label(measurement_id) == "Cold-plate thermometer"
    assert stable_id("triton_01", measurement_id) == "labpulse_triton_01_cold_plate_temperature"


def test_invalid_measurement_defaults_and_source_contracts_are_rejected() -> None:
    """Reject unknown defaults, obsolete mappings, and ambiguous source definitions."""

    base = {
        "label": "Triton Fridge",
        "driver": {
            "type": "labpulse.mqtt_json",
            "options": {"topic": "labpulse/triton/measurements"},
        },
        "measurements": {
            "cold_plate_temperature": {
                "source": "Cold Plate T(K)",
                "setups": ["cryogenics_room"],
            }
        },
    }

    invalid_cases = (
        ({**base, "measurement_defaults": {"unknown": True}}, "unknown"),
        ({**base, "measurements": {}}, "at least one measurement source"),
        ({
            **base,
            "driver": {
                "type": "labpulse.mqtt_json",
                "options": {
                    "topic": "labpulse/triton/measurements",
                    "parameters": {"cold_plate_temperature": "Cold Plate T(K)"},
                },
            },
        }, "parameters"),
        ({**base, "measurements": {
            "cold_plate_temperature": {"setups": ["cryogenics_room"]}
        }}, "requires source"),
        ({**base, "measurements": {
            "cold_plate_temperature": {
                "source": "   ", "setups": ["cryogenics_room"]
            }
        }}, "source must not be blank"),
        ({**base, "measurements": {
            "cold_plate_temperature": {
                "source": "Cold Plate T(K)", "setups": ["cryogenics_room"]
            },
            "duplicate_temperature": {
                "source": "Cold Plate T(K)", "setups": ["cryogenics_room"]
            },
        }}, "sources must be unique"),
    )

    for value, expected in invalid_cases:
        try:
            ServiceConfig.model_validate(value)
        except ValueError as error:
            assert expected in str(error)
        else:
            raise AssertionError(f"invalid configuration was accepted: {expected}")


def test_source_is_rejected_for_a_driver_without_external_names() -> None:
    """Keep serial and direct-hardware measurements keyed by their stable IDs."""

    try:
        ServiceConfig.model_validate({
            "label": "Pressure Monitor",
            "driver": {
                "type": "labpulse.serial_pipe",
                "options": {"port": "/tmp/pressure"},
            },
            "measurements": {
                "pressure": {
                    "source": "Pressure",
                    "setups": ["compressed_air"],
                }
            },
        })
    except ValueError as error:
        assert "does not support measurement source names" in str(error)
    else:
        raise AssertionError("serial source name was accepted")


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


def test_heartbeat_requires_fresh_non_retained_delivery_and_availability() -> None:
    """A quiet logfile stays healthy, but stale, retained, and offline signals do not."""

    fake_client = FakeMqttClient()
    driver = make_heartbeat_driver()
    with patch("labpulse.hardware.drivers.mqtt_json.mqtt.Client", return_value=fake_client):
        driver.connect()
    fake_client.on_connect(fake_client, None, None, SimpleNamespace(is_failure=False), None)
    assert fake_client.subscriptions == [
        ("labpulse/triton/triton-01/measurements", 1),
        ("labpulse/triton/triton-01/heartbeat", 1),
        ("labpulse/triton/triton-01/availability", 1),
    ]
    assert driver.health_status() == SourceHealth.WAITING

    fake_client.on_message(fake_client, None, SimpleNamespace(
        topic=driver.availability_topic, payload=b"online", retain=True,
    ))
    fake_client.on_message(fake_client, None, SimpleNamespace(
        topic=driver.heartbeat_topic, payload=b"alive", retain=True,
    ))
    assert driver.health_status() == SourceHealth.WAITING

    with patch("labpulse.hardware.drivers.mqtt_json.time.monotonic", return_value=100):
        fake_client.on_message(fake_client, None, SimpleNamespace(
            topic=driver.heartbeat_topic, payload=b"alive", retain=False,
        ))
        assert driver.health_status() == SourceHealth.ONLINE
        fake_client.on_connect(fake_client, None, None, SimpleNamespace(is_failure=False), None)
        assert driver.health_status() == SourceHealth.WAITING
        fake_client.on_message(fake_client, None, SimpleNamespace(
            topic=driver.availability_topic, payload=b"online", retain=True,
        ))
        fake_client.on_message(fake_client, None, SimpleNamespace(
            topic=driver.heartbeat_topic, payload=b"alive", retain=False,
        ))
        assert driver.health_status() == SourceHealth.ONLINE
    assert driver.read() is None
    with patch("labpulse.hardware.drivers.mqtt_json.time.monotonic", return_value=161):
        assert driver.health_status() == SourceHealth.OFFLINE

    fake_client.on_message(fake_client, None, SimpleNamespace(
        topic=driver.availability_topic, payload=b"offline", retain=True,
    ))
    assert driver.health_status() == SourceHealth.OFFLINE
    fake_client.on_connect(fake_client, None, None, SimpleNamespace(is_failure=False), None)
    assert driver.health_status() == SourceHealth.WAITING


def test_each_fridge_health_isolated_and_options_reject_ambiguous_topics() -> None:
    """One fridge's signals cannot make the other service healthy."""

    first = make_heartbeat_driver("triton-01")
    second = make_heartbeat_driver("triton-02")
    for driver in (first, second):
        fake_client = FakeMqttClient()
        with patch("labpulse.hardware.drivers.mqtt_json.mqtt.Client", return_value=fake_client):
            driver.connect()
        fake_client.on_connect(fake_client, None, None, SimpleNamespace(is_failure=False), None)
        fake_client.on_message(fake_client, None, SimpleNamespace(
            topic="labpulse/triton/triton-01/availability", payload=b"online", retain=True,
        ))
        fake_client.on_message(fake_client, None, SimpleNamespace(
            topic="labpulse/triton/triton-01/heartbeat", payload=b"alive", retain=False,
        ))
    assert first.health_status() == SourceHealth.ONLINE
    assert second.health_status() == SourceHealth.WAITING

    for options in (
        {"topic": "labpulse/triton/measurements", "heartbeat_timeout_seconds": 60},
        {"topic": "labpulse/triton/measurements", "heartbeat_topic": "bad/#"},
        {"topic": "labpulse/triton/measurements", "heartbeat_topic": "labpulse/triton/measurements"},
    ):
        try:
            MqttJsonConfig.model_validate(options)
        except ValueError:
            pass
        else:
            raise AssertionError(f"ambiguous heartbeat options were accepted: {options}")


def test_service_failure_notification_setting_defaults_on_and_is_strict() -> None:
    """Only an explicit YAML boolean can silence one sensor-hub outage."""

    source = {
        "label": "Sensor Hub",
        "driver": {"type": "labpulse.serial_pipe", "options": {"port": "/tmp/hub"}},
        "measurements": {"pressure": {"setups": ["compressed_air"]}},
    }
    assert ServiceConfig.model_validate(source).notify_on_service_failure is True
    assert ServiceConfig.model_validate({
        **source, "notify_on_service_failure": False,
    }).notify_on_service_failure is False
    try:
        ServiceConfig.model_validate({**source, "notify_on_service_failure": "false"})
    except ValueError:
        pass
    else:
        raise AssertionError("string false was accepted as a notification policy")
