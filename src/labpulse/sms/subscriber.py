"""Subscribe to validated MQTT requests and coordinate SMS delivery."""

from collections import OrderedDict
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
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

REQUEST_RETENTION_SECONDS = 86_400
EVENT_COOLDOWN_SECONDS = 30
MAX_REMEMBERED_REQUESTS = 2_000


class RecentRequestCache:
    """Bounded duplicate and short-term flood protection for SMS requests."""

    def __init__(
        self,
        path: Path,
    ) -> None:
        """Load remembered request IDs from the persistent cache."""

        self.path = path
        self._request_times: OrderedDict[str, float] = OrderedDict()
        self._event_times: dict[str, float] = {}
        self._load()

    def rejection_reason(self, request: SmsRequest) -> str | None:
        """Return why a request is unsafe to enqueue, or None when accepted."""

        now = time.time()
        self._prune(now)
        if request.request_id in self._request_times:
            return "duplicate"
        event_key = self._event_key(request)
        last_event = self._event_times.get(event_key)
        if last_event is not None and now - last_event < EVENT_COOLDOWN_SECONDS:
            return "rate_limited"
        return None

    def remember(self, request: SmsRequest) -> None:
        """Record an accepted request and persist the duplicate cache."""

        now = time.time()
        self._request_times[request.request_id] = now
        self._request_times.move_to_end(request.request_id)
        self._event_times[self._event_key(request)] = now
        self._prune(now)
        self._save()

    def _event_key(self, request: SmsRequest) -> str:
        """Return the key used for short-term repeated-event suppression."""

        delivery_mode = "test" if request.test_mode else "live"
        return f"{delivery_mode}:{request.service}:{request.measurement}:{request.event}"

    def _prune(self, now: float) -> None:
        """Remove expired and excess entries."""

        cutoff = now - REQUEST_RETENTION_SECONDS
        # OrderedDict keeps the oldest request first, so pruning can stop as
        # soon as the first retained entry is both recent and within the limit.
        while self._request_times:
            first_id, first_time = next(iter(self._request_times.items()))
            if first_time >= cutoff and len(self._request_times) <= MAX_REMEMBERED_REQUESTS:
                break
            self._request_times.pop(first_id)
        self._event_times = {
            key: timestamp
            for key, timestamp in self._event_times.items()
            if timestamp >= now - EVENT_COOLDOWN_SECONDS
        }

    def _load(self) -> None:
        """Load valid remembered request timestamps from disk."""

        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        for request_id, timestamp in payload.items():
            if isinstance(request_id, str) and isinstance(timestamp, (int, float)):
                self._request_times[request_id] = float(timestamp)
        self._prune(time.time())

    def _save(self) -> None:
        """Atomically persist remembered request IDs."""

        try:
            # Replacing a finished temporary file prevents a restart from
            # loading partially written JSON.
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary_path.write_text(
                json.dumps(self._request_times, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(self.path)
        except OSError:
            return


class SmsSubscriber:
    """Reliable MQTT subscriber used by the SMS container."""

    def __init__(
        self,
        mqtt_config: MqttConfig,
        sender: SmsSender,
        request_cache_path: Path,
    ) -> None:
        """Store dependencies and create a persistent-session MQTT client."""

        self._mqtt_config = mqtt_config
        self._sender = sender
        self._request_cache = RecentRequestCache(request_cache_path)
        self._logger = logging.getLogger("LabPulse.SMS")
        # A persistent MQTT session preserves QoS 1 messages while this service
        # is briefly offline. QoS 1 may redeliver, so RecentRequestCache removes
        # duplicates before they reach the modem.
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="LabPulse-SMS",
            clean_session=False,
        )
        self._client.will_set(
            SMS_STATUS_TOPIC,
            payload=json.dumps({"state": "offline"}),
            qos=1,
            retain=True,
        )
        self._sender.set_result_handler(self.publish_delivery_result)

    def connect(self) -> None:
        """Connect to the MQTT broker and register callbacks."""

        self._client.on_connect = self.on_connect
        self._client.on_message = self.on_message
        self._logger.info(
            "Connecting to MQTT broker %s:%s",
            self._mqtt_config.broker,
            self._mqtt_config.port,
        )
        self._client.connect(self._mqtt_config.broker, self._mqtt_config.port, 60)

    def loop_forever(self) -> None:
        """Block forever handling MQTT network traffic."""

        self._client.loop_forever()

    def close(self) -> None:
        """Drain queued sends, publish offline status, and disconnect."""

        self._sender.close()
        self._publish_json(SMS_STATUS_TOPIC, {"state": "offline"}, retain=True)
        self._client.disconnect()

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
            self._logger.error("SMS MQTT connection failed: %s", reason_code)
            return
        self._logger.info("SMS service subscribing to %s", SMS_SUBSCRIPTION_TOPIC)
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
        except ValueError as error:
            self._logger.warning("Rejected invalid SMS request: %s", error)
            return

        reason = self._request_cache.rejection_reason(request)
        if reason is not None:
            self._logger.warning(
                "Rejected SMS request %s: %s", request.request_id, reason
            )
            self.publish_delivery_result(
                DeliveryResult(request.request_id, "", reason, reason)
            )
            return

        self._logger.info(
            "SMS request accepted: request_id=%s event=%s service=%s measurement=%s",
            request.request_id,
            request.event,
            request.service,
            request.measurement,
        )
        # Remember only requests the sender accepted. A full queue or missing
        # recipient configuration should be retryable rather than marked done.
        if self._sender.broadcast(request):
            self._request_cache.remember(request)

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

        self._client.publish(
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
        raise ValueError("payload is not valid UTF-8") from error
    try:
        return SmsRequest.model_validate_json(text)
    except ValidationError as error:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors()
        )
        raise ValueError(problems) from error


def utc_timestamp() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).isoformat()
