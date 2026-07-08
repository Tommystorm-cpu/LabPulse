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
        self.discovered_metrics: set[str] = set()
        self.status_discovery_published = False
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
        Publish Home Assistant discovery for new metrics, then publish readings.
        """
        undiscovered_readings = {
            metric_name: reading
            for metric_name, reading in readings.items()
            if metric_name not in self.discovered_metrics
        }

        if undiscovered_readings:
            self.publish_discovery(undiscovered_readings)
            self.discovered_metrics.update(undiscovered_readings)

        self.publish_readings(readings)

    def publish_status(self, status: str) -> None:
        """Publish the service health status as a retained Home Assistant entity."""

        if not self.status_discovery_published:
            self.publish_status_discovery()
            self.status_discovery_published = True

        self.client.publish(self.status_topic(), status, retain=True)
        self.logger.info("Published service status: %s", status)

    def publish_status_discovery(self) -> None:
        """Publish Home Assistant MQTT discovery config for service status."""

        payload = {
            "name": "Status",
            "state_topic": self.status_topic(),
            "unique_id": f"{self.service_name}_status",
            "icon": "mdi:heart-pulse",
            "device": {
                "identifiers": [self.service_name],
                "name": self.service_config.device_name,
            },
        }

        self.client.publish(
            self.status_discovery_topic(),
            json.dumps(payload),
            retain=True,
        )
        self.logger.info("Published Home Assistant status discovery")

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
            #self.logger.info("Published %s reading: %s", metric_name, reading)

    def disconnect(self) -> None:
        """Stop MQTT networking and disconnect from the broker."""
        self.client.loop_stop()
        self.client.disconnect()
        self.logger.info("Disconnected from MQTT broker")

    def state_topic(self, metric_name: str) -> str:
        """Return the MQTT state topic for one metric."""
        return f"{STATE_TOPIC_PREFIX}/{self.service_name}/{metric_name}/state"

    def status_topic(self) -> str:
        """Return the MQTT state topic for this service's health status."""

        return f"{STATE_TOPIC_PREFIX}/{self.service_name}/status"

    def discovery_topic(self, metric_name: str) -> str:
        """Return the Home Assistant discovery topic for one metric."""
        return f"{DISCOVERY_PREFIX}/sensor/{self.service_name}_{metric_name}/config"

    def status_discovery_topic(self) -> str:
        """Return the Home Assistant discovery topic for service status."""

        return f"{DISCOVERY_PREFIX}/sensor/{self.service_name}_status/config"

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

