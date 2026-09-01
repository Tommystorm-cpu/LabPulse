"""Receive named measurements from one JSON snapshot published over MQTT."""

import json
import math
import re
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt
from pydantic import BaseModel, ConfigDict, Field, field_validator

from labpulse.hardware.driver import (
    ContainerRequirements,
    ConnectionLost,
    DriverDefinition,
    DriverUnavailable,
    HardwareDriver,
    HardwareIssue,
    HardwareReadings,
    TransientReadError,
)


MQTT_PROTOCOL = "labpulse.measurements"
MQTT_PROTOCOL_VERSION = 1
MAXIMUM_MESSAGE_BYTES = 1_000_000
FUTURE_TIMESTAMP_TOLERANCE_SECONDS = 60


# Values accepted under driver.options in config.yaml.
class MqttJsonConfig(BaseModel):
    """MQTT source and raw-name mapping for one JSON measurement stream."""

    model_config = ConfigDict(extra="forbid", strict=True)

    broker: str = "mosquitto"
    port: int = Field(default=1883, ge=1, le=65535)
    topic: str
    parameters: dict[str, str] = Field(min_length=1)
    maximum_record_age_seconds: int = Field(default=300, ge=2, le=86400)

    @field_validator("broker", "topic")
    @classmethod
    def validate_non_blank_text(cls, value: str) -> str:
        """Normalize required MQTT connection strings."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("topic")
    @classmethod
    def validate_exact_topic(cls, topic: str) -> str:
        """Require one exact topic rather than an MQTT wildcard subscription."""

        if "+" in topic or "#" in topic:
            raise ValueError("topic must not contain MQTT wildcards")
        return topic

    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, parameters: dict[str, str]) -> dict[str, str]:
        """Validate readable LabPulse IDs mapped to non-blank source headers."""

        normalized: dict[str, str] = {}
        for measurement_name, source_header in parameters.items():
            if re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", measurement_name) is None:
                raise ValueError(
                    "parameter names must use lowercase letters, numbers, and underscores"
                )
            header = source_header.strip()
            if not header:
                raise ValueError(f"source header for {measurement_name} must not be blank")
            normalized[measurement_name] = header
        return normalized


def parse_measurement_message(
    payload: bytes,
    parameters: dict[str, str],
    maximum_record_age_seconds: int,
    received_at: float,
) -> HardwareReadings:
    """Validate one external JSON message and select configured measurements."""

    if len(payload) > MAXIMUM_MESSAGE_BYTES:
        raise ValueError(f"MQTT JSON message exceeds {MAXIMUM_MESSAGE_BYTES} bytes")

    try:
        message = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON: {error}") from error

    if not isinstance(message, dict):
        raise ValueError("MQTT JSON message must be an object")
    if message.get("protocol") != MQTT_PROTOCOL:
        raise ValueError(f"protocol must be {MQTT_PROTOCOL!r}")
    version = message.get("version")
    if isinstance(version, bool) or version != MQTT_PROTOCOL_VERSION:
        raise ValueError(f"unsupported protocol version: {version!r}")

    recorded_at = message.get("recorded_at")
    if isinstance(recorded_at, bool) or not isinstance(recorded_at, (int, float)):
        raise ValueError("recorded_at must be a Unix timestamp")
    if not math.isfinite(recorded_at):
        raise ValueError("recorded_at must be finite")
    if recorded_at > received_at + FUTURE_TIMESTAMP_TOLERANCE_SECONDS:
        raise ValueError("recorded_at is in the future")
    record_age = received_at - recorded_at
    if record_age > maximum_record_age_seconds:
        raise ValueError(f"Triton record is {record_age:.1f} seconds old")

    source_measurements = message.get("measurements")
    if not isinstance(source_measurements, dict):
        raise ValueError("measurements must be an object")

    selected_measurements: dict[str, float] = {}
    unavailable_headers: list[str] = []
    for measurement_name, source_header in parameters.items():
        value = source_measurements.get(source_header)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            unavailable_headers.append(source_header)
            continue
        selected_measurements[measurement_name] = float(value)

    if not selected_measurements:
        missing = ", ".join(unavailable_headers)
        raise ValueError(f"none of the configured measurements are available: {missing}")

    if unavailable_headers:
        missing = ", ".join(unavailable_headers)
        issue = HardwareIssue(code="missing_measurements", message=f"Unavailable MQTT measurements: {missing}")
        return HardwareReadings(selected_measurements, issues=(issue,))
    return HardwareReadings(selected_measurements)


# The MQTT network loop receives messages on a background thread. The runner
# reads the newest completed snapshot through the small lock below.
class MqttJsonDriver(HardwareDriver):
    """Receive complete JSON snapshots and expose selected numeric fields."""

    def __init__(self, service_name: str, config: MqttJsonConfig) -> None:
        """Store the MQTT source and configured raw-header mapping."""

        super().__init__(service_name)
        self.broker = config.broker
        self.port = config.port
        self.topic = config.topic
        self.parameters = dict(config.parameters)
        self.maximum_record_age_seconds = config.maximum_record_age_seconds

        self._client: mqtt.Client | None = None
        self._message_lock = threading.Lock()
        self._pending_readings: HardwareReadings | None = None
        self._pending_error: str | None = None
        self._connection_lost: str | None = None
        self._closing = False

    def connect(self) -> None:
        """Connect to the broker and subscribe to the configured snapshot topic."""

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"LabPulse-{self.service_name}-input")
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message

        with self._message_lock:
            self._pending_readings = None
            self._pending_error = None
            self._connection_lost = None
            self._closing = False

        try:
            client.connect(self.broker, self.port, keepalive=60)
            client.loop_start()
        except (OSError, mqtt.MQTTException) as error:
            raise DriverUnavailable(f"failed to connect to MQTT broker {self.broker}:{self.port}: {error}") from error

        self._client = client
        self.logger.info("Connecting to MQTT broker %s:%s for %s", self.broker, self.port, self.topic)

    def read(self) -> HardwareReadings | None:
        """Return the newest snapshot once, or classify an MQTT stream failure."""

        if self._client is None:
            raise ConnectionLost("MQTT input client is not running")

        with self._message_lock:
            connection_lost = self._connection_lost
            pending_error = self._pending_error
            pending_readings = self._pending_readings
            self._connection_lost = None
            self._pending_error = None
            self._pending_readings = None

        if connection_lost is not None:
            raise ConnectionLost(connection_lost)
        if pending_error is not None:
            raise TransientReadError(pending_error)
        return pending_readings

    def close(self) -> None:
        """Stop MQTT networking and release the client safely."""

        client = self._client
        self._client = None
        if client is None:
            return

        with self._message_lock:
            self._closing = True
        try:
            client.disconnect()
        except (OSError, mqtt.MQTTException) as error:
            self.logger.warning("Failed to close MQTT input client: %s", error)
        finally:
            client.loop_stop()

    def _on_connect(
        self,
        client: mqtt.Client,
        _userdata: object,
        _flags: Any,
        reason_code: Any,
        _properties: Any,
    ) -> None:
        """Subscribe after the broker accepts the MQTT connection."""

        if getattr(reason_code, "is_failure", False):
            with self._message_lock:
                self._connection_lost = f"MQTT broker rejected the connection: {reason_code}"
            return

        result, _message_id = client.subscribe(self.topic, qos=1)
        if result != mqtt.MQTT_ERR_SUCCESS:
            with self._message_lock:
                self._connection_lost = f"MQTT subscription failed with result {result}"
            return
        self.logger.info("Subscribed to MQTT input topic %s", self.topic)

    def _on_disconnect(
        self,
        _client: mqtt.Client,
        _userdata: object,
        _disconnect_flags: Any,
        reason_code: Any,
        _properties: Any,
    ) -> None:
        """Make an unexpected broker disconnection visible to the runner."""

        with self._message_lock:
            if not self._closing:
                self._connection_lost = f"MQTT input connection lost: {reason_code}"

    def _on_message(self, _client: mqtt.Client, _userdata: object, message: Any) -> None:
        """Validate one broker message and make it available to the runner."""

        try:
            readings = parse_measurement_message(
                message.payload,
                self.parameters,
                self.maximum_record_age_seconds,
                time.time(),
            )
        except ValueError as error:
            with self._message_lock:
                self._pending_readings = None
                self._pending_error = f"invalid MQTT measurement message: {error}"
            return

        with self._message_lock:
            self._pending_readings = readings
            self._pending_error = None


# MQTT is ordinary outbound networking, so the container needs no host devices
# or privileged access in the generated Docker Compose file.
def container_requirements(_config: MqttJsonConfig, _force_simulated: bool) -> ContainerRequirements:
    """Return the empty container requirements for an MQTT network source."""

    return ContainerRequirements()


DRIVER_DEFINITION = DriverDefinition(
    driver_id="labpulse.mqtt_json",
    config_model=MqttJsonConfig,
    driver_class=MqttJsonDriver,
    container_requirements=container_requirements,
    default_read_interval_seconds=0.1,
)
