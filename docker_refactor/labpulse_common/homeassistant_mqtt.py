import json
import logging

import paho.mqtt.client as mqtt

from labpulse_common.config import MqttConfig, ServiceConfig


DISCOVERY_PREFIX = "homeassistant"
STATE_TOPIC_PREFIX = "home/sensor"


class HomeAssistantMqttPublisher:
    """
    Publishes LabPulse readings to MQTT using Home Assistant discovery.
    """

    def __init__(
        self,
        service_name: str,
        service_config: ServiceConfig,
        mqtt_config: MqttConfig,
    ) -> None:
        """Create an MQTT publisher for one LabPulse service."""

        self.service_name = service_name
        self.service_config = service_config
        self.mqtt_config = mqtt_config
        self.discovery_published = False
        self.logger = logging.getLogger(f"HomeAssistantMqtt.{service_name}")
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"LabPulse-{service_name}",
        )

    def connect(self) -> None:
        """Connect to the MQTT broker and start the background network loop."""
        self.logger.info(
            "Connecting to MQTT broker %s:%s",
            self.mqtt_config.broker,
            self.mqtt_config.port,
        )
        self.client.connect(self.mqtt_config.broker, self.mqtt_config.port, 60)
        self.client.loop_start()

    def publish(self, readings: dict[str, float]) -> None:
        """
        Publish Home Assistant discovery once, then publish the latest readings.
        """
        if not self.discovery_published:
            self.publish_discovery(readings)
            self.discovery_published = True

        self.publish_readings(readings)

    def publish_discovery(self, readings: dict[str, float]) -> None:
        """Publish Home Assistant MQTT discovery config for each metric."""
        for metric_name in readings:
            payload = {
                "name": self.metric_label(metric_name),
                "state_topic": self.state_topic(metric_name),
                "unique_id": f"{self.service_name}_{metric_name}",
                "device": {
                    "identifiers": [self.service_name],
                    "name": self.service_config.device_name,
                },
            }

            unit = self.unit_for_metric(metric_name)
            if unit:
                payload["unit_of_measurement"] = unit

            self.client.publish(
                self.discovery_topic(metric_name),
                json.dumps(payload),
                retain=True,
            )
            self.logger.info("Published Home Assistant discovery for %s", metric_name)

    def publish_readings(self, readings: dict[str, float]) -> None:
        """Publish current sensor readings to their MQTT state topics."""
        for metric_name, reading in readings.items():
            self.client.publish(self.state_topic(metric_name), reading)
            self.logger.info("Published %s reading: %s", metric_name, reading)

    def disconnect(self) -> None:
        """Stop MQTT networking and disconnect from the broker."""
        self.client.loop_stop()
        self.client.disconnect()
        self.logger.info("Disconnected from MQTT broker")

    def state_topic(self, metric_name: str) -> str:
        """Return the MQTT state topic for one metric."""
        return f"{STATE_TOPIC_PREFIX}/{self.service_name}/{metric_name}/state"

    def discovery_topic(self, metric_name: str) -> str:
        """Return the Home Assistant discovery topic for one metric."""
        return f"{DISCOVERY_PREFIX}/sensor/{self.service_name}_{metric_name}/config"

    @staticmethod
    def metric_label(metric_name: str) -> str:
        """Convert a metric key into a readable Home Assistant entity name."""
        return metric_name.replace("_", " ").title()

    @staticmethod
    def unit_for_metric(metric_name: str) -> str | None:
        """Infer a Home Assistant unit from the metric name."""
        if "pressure" in metric_name or "press" in metric_name:
            return "bar"

        if "temp" in metric_name:
            return "\u00b0C"

        if "hum" in metric_name:
            return "%"

        if "flow" in metric_name:
            return "L/min"

        return None

