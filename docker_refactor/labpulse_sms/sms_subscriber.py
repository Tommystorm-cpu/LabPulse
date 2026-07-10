"""Subscribe to MQTT events that should be forwarded by the SMS service."""

import json
import logging

import paho.mqtt.client as mqtt

from labpulse_common.config import MqttConfig
from labpulse_common.mqtt_contracts import SMS_SUBSCRIPTION_TOPIC
from labpulse_sms.sender import SmsSender, format_sms_message


class SMSSubscriber:
    """MQTT subscriber used by the SMS container."""

    def __init__(self, mqtt_config: MqttConfig, sender: SmsSender) -> None:
        """Store MQTT settings and create the client."""

        self.mqtt_config = mqtt_config
        self.sender = sender
        self.logger = logging.getLogger("HomeAssistantMqtt.SMS")
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id="LabPulse-SMS",
        )

    def connect(self) -> None:
        """Connect to the MQTT broker."""

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

    def on_connect(
        self,
        client: mqtt.Client,
        _userdata: object,
        _flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        """Subscribe to SMS requests whenever MQTT connects or reconnects."""

        if reason_code != 0:
            self.logger.error("SMS MQTT connection failed: %s", reason_code)
            return

        self.logger.info("SMS service subscribing to %s", SMS_SUBSCRIPTION_TOPIC)
        client.subscribe(SMS_SUBSCRIPTION_TOPIC)

    def on_message(self, _client: mqtt.Client, _userdata: object, message: mqtt.MQTTMessage) -> None:
        """Handle one inbound MQTT message."""

        request = parse_sms_payload(message.payload)
        self.logger.info(
            "SMS request received: service=%s reading=%s entity_id=%s title=%s message=%s",
            request.get("service", "unknown"),
            request.get("reading", "unknown"),
            request.get("entity_id", "unknown"),
            request.get("title", "LabPulse SMS"),
            request.get("message", ""),
        )
        self.sender.broadcast(format_sms_message(request))


def parse_sms_payload(payload: bytes | str) -> dict[str, str]:
    """Decode one SMS MQTT payload into a loggable request dictionary."""

    text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return {"message": text}

    if not isinstance(decoded, dict):
        return {"message": text}

    return {str(key): str(value) for key, value in decoded.items()}
