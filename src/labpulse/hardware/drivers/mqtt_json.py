"""Receive named measurements from one JSON snapshot published over MQTT."""

import json
import math
from collections.abc import Mapping
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt import MQTTException
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

from labpulse.hardware.driver import (
    ContainerRequirements,
    ConnectionLost,
    DriverDefinition,
    DriverUnavailable,
    HardwareDriver,
    HardwareIssue,
    HardwareReadings,
    SourceHealth,
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
    maximum_record_age_seconds: int = Field(default=300, ge=2, le=86400)
    heartbeat_topic: str | None = None
    heartbeat_timeout_seconds: int = Field(default=60, ge=2, le=3600)
    _measurement_sources: dict[str, str] = PrivateAttr(default_factory=dict)

    @field_validator("broker", "topic")
    @classmethod
    def validate_non_blank_text(cls, value: str) -> str:
        """Normalize required MQTT connection strings."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("topic", "heartbeat_topic")
    @classmethod
    def validate_exact_topic(cls, topic: str | None) -> str | None:
        """Require one exact topic rather than an MQTT wildcard subscription."""

        if topic is None:
            return None
        if "+" in topic or "#" in topic:
            raise ValueError("topic must not contain MQTT wildcards")
        normalized = topic.strip()
        if not normalized:
            raise ValueError("topic must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_heartbeat_contract(self) -> "MqttJsonConfig":
        """Keep one heartbeat and availability pair distinct from measurements."""

        if self.heartbeat_topic is not None:
            if not self.heartbeat_topic.endswith("/heartbeat"):
                raise ValueError("heartbeat_topic must end with /heartbeat")
            if self.topic in {self.heartbeat_topic, self.availability_topic}:
                raise ValueError("measurement topic must differ from publisher-health topics")
        elif "heartbeat_timeout_seconds" in self.model_fields_set:
            raise ValueError("heartbeat_timeout_seconds requires heartbeat_topic")
        return self

    @property
    def availability_topic(self) -> str | None:
        """Derive the retained availability topic beside the heartbeat."""

        if self.heartbeat_topic is None:
            return None
        return self.heartbeat_topic.removesuffix("heartbeat") + "availability"

    def bind_measurement_sources(self, sources: Mapping[str, str]) -> None:
        """Store source names already validated at the service boundary."""

        if not sources:
            raise ValueError("MQTT JSON services require at least one measurement source")
        seen_sources: set[str] = set()
        duplicate_sources: set[str] = set()
        for source in sources.values():
            if source in seen_sources:
                duplicate_sources.add(source)
            seen_sources.add(source)
        if duplicate_sources:
            raise ValueError(
                "MQTT JSON measurement sources must be unique: "
                + ", ".join(sorted(duplicate_sources))
            )
        self._measurement_sources = dict(sources)

    @property
    def measurement_sources(self) -> Mapping[str, str]:
        """Return the stable-ID to external-source mapping for this service."""

        return self._measurement_sources


def bind_measurement_sources(config: BaseModel, sources: Mapping[str, str]) -> None:
    """Bind service measurement sources to validated MQTT JSON options."""

    if not isinstance(config, MqttJsonConfig):
        raise TypeError("labpulse.mqtt_json received the wrong configuration model")
    config.bind_measurement_sources(sources)


def parse_measurement_message(
    payload: bytes,
    measurement_sources: Mapping[str, str],
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
    for measurement_name, source_header in measurement_sources.items():
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
    """Pass the latest MQTT sample from Paho callbacks to the runner under a lock.

    Pending data is one replaceable slot, not a queue. Nothing is persisted.
    With heartbeat monitoring, reconnect needs fresh health evidence. See README.md.
    """

    def __init__(self, service_name: str, config: MqttJsonConfig) -> None:
        """Store the MQTT source and configured raw-header mapping."""

        super().__init__(service_name)
        self.broker = config.broker
        self.port = config.port
        self.topic = config.topic
        self.heartbeat_topic = config.heartbeat_topic
        self.availability_topic = config.availability_topic
        self.heartbeat_timeout_seconds = config.heartbeat_timeout_seconds
        if not config.measurement_sources:
            raise ValueError(
                "MQTT JSON measurement sources were not bound during configuration validation"
            )
        self.measurement_sources = dict(config.measurement_sources)
        self.maximum_record_age_seconds = config.maximum_record_age_seconds

        self._client: mqtt.Client | None = None
        self._message_lock = threading.Lock()
        self._pending_readings: HardwareReadings | None = None
        self._pending_error: str | None = None
        self._connection_lost: str | None = None
        self._heartbeat_received_at: float | None = None
        self._publisher_available = False
        self._publisher_availability_known = False
        self._health_connection_started_at: float | None = None
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
            self._heartbeat_received_at = None
            self._publisher_available = False
            self._publisher_availability_known = False
            self._health_connection_started_at = time.monotonic()
            self._closing = False

        try:
            client.connect(self.broker, self.port, keepalive=60)
            client.loop_start()
        except (OSError, MQTTException) as error:
            raise DriverUnavailable(f"failed to connect to MQTT broker {self.broker}:{self.port}: {error}") from error

        self._client = client
        self.logger.info("Connecting to MQTT broker %s:%s for %s", self.broker, self.port, self.topic)

    def read(self) -> HardwareReadings | None:
        """Take and clear pending data under the lock without waiting for a message.

        ConnectionLost takes priority over TransientReadError, then readings.
        Return None if no sample or failure is pending.
        """

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

    def health_status(self) -> SourceHealth | None:
        """Wait for a first heartbeat, then require its continued delivery."""

        if self.heartbeat_topic is None:
            return None
        with self._message_lock:
            heartbeat_received_at = self._heartbeat_received_at
            publisher_available = self._publisher_available
            availability_known = self._publisher_availability_known
            connection_started_at = self._health_connection_started_at
        current_time = time.monotonic()
        if availability_known and not publisher_available:
            return SourceHealth.OFFLINE
        if (
            availability_known and heartbeat_received_at is not None
            and current_time - heartbeat_received_at < self.heartbeat_timeout_seconds
        ):
            return SourceHealth.ONLINE
        if connection_started_at is not None and current_time - connection_started_at >= self.heartbeat_timeout_seconds:
            return SourceHealth.OFFLINE
        return SourceHealth.WAITING

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
        except (OSError, MQTTException) as error:
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

        with self._message_lock:
            self._heartbeat_received_at = None
            self._publisher_available = False
            self._publisher_availability_known = False
            self._health_connection_started_at = time.monotonic()
        topics = [self.topic]
        if self.heartbeat_topic is not None and self.availability_topic is not None:
            topics.extend((self.heartbeat_topic, self.availability_topic))
        for topic in topics:
            result, _message_id = client.subscribe(topic, qos=1)
            if result != mqtt.MQTT_ERR_SUCCESS:
                with self._message_lock:
                    self._connection_lost = f"MQTT subscription to {topic} failed with result {result}"
                return
            self.logger.info("Subscribed to MQTT input topic %s", topic)

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
                self._heartbeat_received_at = None
                self._publisher_available = False
                self._publisher_availability_known = False

    def _on_message(self, _client: mqtt.Client, _userdata: object, message: Any) -> None:
        """Validate one broker message and make it available to the runner."""

        topic = getattr(message, "topic", self.topic)
        if topic == self.heartbeat_topic:
            # An old retained heartbeat must never establish current health.
            if not getattr(message, "retain", False) and message.payload == b"alive":
                with self._message_lock:
                    self._heartbeat_received_at = time.monotonic()
            return
        if topic == self.availability_topic:
            with self._message_lock:
                self._publisher_available = message.payload == b"online"
                self._publisher_availability_known = True
                if not self._publisher_available:
                    self._heartbeat_received_at = None
            return
        if topic != self.topic:
            return

        try:
            readings = parse_measurement_message(
                message.payload,
                self.measurement_sources,
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
    bind_measurement_sources=bind_measurement_sources,
)
