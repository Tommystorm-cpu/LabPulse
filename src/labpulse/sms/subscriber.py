"""Subscribe to validated MQTT requests and coordinate SMS delivery."""

from collections import OrderedDict
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from collections.abc import Callable
from typing import Any

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from labpulse.common.config import MqttConfig
from labpulse.common.mqtt_contracts import (
    SMS_STATUS_DISCOVERY_TOPIC,
    SMS_STATUS_TOPIC,
    SMS_SUBSCRIPTION_TOPIC,
    SmsRequest,
    sms_result_topic,
)
from labpulse.sms.sender import DeliveryResult, SmsSender


ClientFactory = Callable[..., mqtt.Client]


class SmsPayloadError(ValueError):
    """Raised when an MQTT payload is not a valid SMS request."""


class RecentRequestCache:
    """Bounded duplicate and short-term flood protection for SMS requests."""

    def __init__(
        self,
        path: Path | None = None,
        retention_seconds: float = 86_400,
        cooldown_seconds: float = 30,
        max_entries: int = 2_000,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Load remembered request IDs and configure retention limits."""

        self.path = path
        self.retention_seconds = retention_seconds
        self.cooldown_seconds = cooldown_seconds
        self.max_entries = max_entries
        self.clock = clock
        self.request_times: OrderedDict[str, float] = OrderedDict()
        self.event_times: dict[str, float] = {}
        self._load()

    def rejection_reason(self, request: SmsRequest) -> str | None:
        """Return why a request is unsafe to enqueue, or None when accepted."""

        now = self.clock()
        self._prune(now)
        if request.request_id in self.request_times:
            return "duplicate"
        event_key = self._event_key(request)
        last_event = self.event_times.get(event_key)
        if last_event is not None and now - last_event < self.cooldown_seconds:
            return "rate_limited"
        return None

    def remember(self, request: SmsRequest) -> None:
        """Record an accepted request and persist the duplicate cache."""

        now = self.clock()
        self.request_times[request.request_id] = now
        self.request_times.move_to_end(request.request_id)
        self.event_times[self._event_key(request)] = now
        self._prune(now)
        self._save()

    def _event_key(self, request: SmsRequest) -> str:
        """Return the key used for short-term repeated-event suppression."""

        delivery_mode = "test" if request.test_mode else "live"
        return f"{delivery_mode}:{request.service}:{request.measurement}:{request.event}"

    def _prune(self, now: float) -> None:
        """Remove expired and excess entries."""

        cutoff = now - self.retention_seconds
        while self.request_times:
            first_id, first_time = next(iter(self.request_times.items()))
            if first_time >= cutoff and len(self.request_times) <= self.max_entries:
                break
            self.request_times.pop(first_id)
        self.event_times = {
            key: timestamp
            for key, timestamp in self.event_times.items()
            if timestamp >= now - self.cooldown_seconds
        }

    def _load(self) -> None:
        """Load valid remembered request timestamps from disk."""

        if self.path is None or not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        for request_id, timestamp in payload.items():
            if isinstance(request_id, str) and isinstance(timestamp, (int, float)):
                self.request_times[request_id] = float(timestamp)
        self._prune(self.clock())

    def _save(self) -> None:
        """Atomically persist remembered IDs when a cache path is configured."""

        if self.path is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary_path.write_text(
                json.dumps(self.request_times, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(self.path)
        except OSError:
            return


class SMSSubscriber:
    """Reliable MQTT subscriber used by the SMS container."""

    def __init__(
        self,
        mqtt_config: MqttConfig,
        sender: SmsSender,
        client_factory: ClientFactory = mqtt.Client,
        request_cache: RecentRequestCache | None = None,
    ) -> None:
        """Store dependencies and create a persistent-session MQTT client."""

        self.mqtt_config = mqtt_config
        self.sender = sender
        self.logger = logging.getLogger("LabPulse.SMS")
        self.request_cache = request_cache or RecentRequestCache()
        self.client = client_factory(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="LabPulse-SMS",
            clean_session=False,
        )
        self.client.will_set(
            SMS_STATUS_TOPIC,
            payload=json.dumps({"state": "offline"}),
            qos=1,
            retain=True,
        )
        self.sender.set_result_handler(self.publish_delivery_result)

    def connect(self) -> None:
        """Connect to the MQTT broker and register callbacks."""

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.logger.info(
            "Connecting to MQTT broker %s:%s",
            self.mqtt_config.broker,
            self.mqtt_config.port,
        )
        self.client.connect(self.mqtt_config.broker, self.mqtt_config.port, 60)

    def loop_forever(self) -> None:
        """Block forever handling MQTT network traffic."""

        self.client.loop_forever()

    def close(self) -> None:
        """Drain queued sends, publish offline status, and disconnect."""

        self.sender.close()
        self._publish_json(SMS_STATUS_TOPIC, {"state": "offline"}, retain=True)
        self.client.disconnect()

    def on_connect(
        self,
        client: mqtt.Client,
        _userdata: object,
        _flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        """Subscribe at QoS 1 whenever MQTT connects or reconnects."""

        if reason_code != 0:
            self.logger.error("SMS MQTT connection failed: %s", reason_code)
            return
        self.logger.info("SMS service subscribing to %s", SMS_SUBSCRIPTION_TOPIC)
        client.subscribe(SMS_SUBSCRIPTION_TOPIC, qos=1)
        self._publish_json(
            SMS_STATUS_DISCOVERY_TOPIC,
            {
                "name": "LabPulse SMS Status",
                "unique_id": "labpulse_sms_status",
                "state_topic": SMS_STATUS_TOPIC,
                "value_template": "{{ value_json.state }}",
                "icon": "mdi:message-alert",
            },
            retain=True,
        )
        self._publish_json(
            SMS_STATUS_TOPIC,
            {"state": "online", "timestamp": utc_timestamp()},
            retain=True,
        )

    def on_message(
        self,
        _client: mqtt.Client,
        _userdata: object,
        message: mqtt.MQTTMessage,
    ) -> None:
        """Validate and enqueue one inbound MQTT request."""

        try:
            request = parse_sms_payload(message.payload)
        except SmsPayloadError as error:
            self.logger.warning("Rejected invalid SMS request: %s", error)
            return

        reason = self.request_cache.rejection_reason(request)
        if reason is not None:
            self.logger.warning(
                "Rejected SMS request %s: %s", request.request_id, reason
            )
            self.publish_delivery_result(
                DeliveryResult(request.request_id, "", reason, reason)
            )
            return

        self.logger.info(
            "SMS request accepted: request_id=%s event=%s service=%s measurement=%s",
            request.request_id,
            request.event,
            request.service,
            request.measurement,
        )
        if self.sender.broadcast(request):
            self.request_cache.remember(request)

    def publish_delivery_result(self, result: DeliveryResult) -> None:
        """Publish one per-recipient delivery result at QoS 1."""

        self._publish_json(
            sms_result_topic(result.request_id),
            {
                "request_id": result.request_id,
                "recipient": result.recipient,
                "status": result.status,
                "detail": result.detail,
                "timestamp": utc_timestamp(),
            },
        )

    def _publish_json(
        self,
        topic: str,
        payload: dict[str, Any],
        retain: bool = False,
    ) -> None:
        """Publish one JSON object with the SMS service reliability settings."""

        self.client.publish(
            topic,
            json.dumps(payload, separators=(",", ":")),
            qos=1,
            retain=retain,
        )


def parse_sms_payload(payload: bytes | str) -> SmsRequest:
    """Decode and strictly validate one SMS MQTT request."""

    try:
        text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    except UnicodeDecodeError as error:
        raise SmsPayloadError("payload is not valid UTF-8") from error
    try:
        return SmsRequest.model_validate_json(text)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors()
        )
        raise SmsPayloadError(problems) from error


def utc_timestamp() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).isoformat()
