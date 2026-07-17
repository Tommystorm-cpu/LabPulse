"""Hand hardware readings to Home Assistant through MQTT discovery/state."""

import json
import logging

import paho.mqtt.client as mqtt

from labpulse_common.config import MqttConfig, ServiceConfig
from labpulse_common.identity import entity_id, stable_id
from labpulse_common.mqtt_contracts import (
    sensor_discovery_topic,
    sensor_state_topic,
    service_status_topic,
    status_discovery_topic,
)


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
        self.reading_configs = {
            reading.name: reading
            for reading in service_config.readings
        }
        self.discovered_readings: set[str] = set()
        self.status_discovery_published = False
        self.logger = logging.getLogger(f"HomeAssistantMqtt.{service_name}")
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"LabPulse-{service_name}",
        )

    def connect(self) -> None:
        """Connect to the MQTT broker and start the background network loop."""
        self.client.will_set(
            service_status_topic(self.service_name),
            payload="offline",
            qos=1,
            retain=True,
        )
        self.logger.info(
            "Connecting to MQTT broker %s:%s",
            self.mqtt_config.broker,
            self.mqtt_config.port,
        )
        self.client.connect(self.mqtt_config.broker, self.mqtt_config.port, 60)
        self.client.loop_start()

    def publish(self, readings: dict[str, float]) -> None:
        """
        Publish Home Assistant discovery for new readings, then publish values.
        """
        readings = self.configured_readings(readings)
        undiscovered_readings = {
            reading_name: reading
            for reading_name, reading in readings.items()
            if reading_name not in self.discovered_readings
        }

        if undiscovered_readings:
            self.publish_discovery(undiscovered_readings)
            self.discovered_readings.update(undiscovered_readings)

        self.publish_readings(readings)

    def configured_readings(self, readings: dict[str, float]) -> dict[str, float]:
        """Return only readings declared exactly in this service's config."""

        configured = {}

        for reading_name, reading in readings.items():
            if reading_name in self.reading_configs:
                configured[reading_name] = reading
            else:
                self.logger.warning("Ignoring unconfigured reading: %s", reading_name)

        return configured

    def publish_status(self, status: str) -> None:
        """Publish the service health status as a retained Home Assistant entity."""

        if not self.status_discovery_published:
            self.publish_status_discovery()
            self.status_discovery_published = True

        self.client.publish(
            service_status_topic(self.service_name),
            status,
            retain=True,
        )
        self.logger.info("Published service status: %s", status)

    def publish_status_discovery(self) -> None:
        """Publish Home Assistant MQTT discovery config for service status."""

        status_id = stable_id(self.service_name, "status")
        payload = {
            "name": "Status",
            "state_topic": service_status_topic(self.service_name),
            "unique_id": status_id,
            "object_id": status_id,
            "default_entity_id": entity_id("sensor", self.service_name, "status"),
            "icon": "mdi:heart-pulse",
            "device": {
                "identifiers": [self.service_name],
                "name": self.service_config.device_name,
            },
        }

        self.client.publish(
            status_discovery_topic(self.service_name),
            json.dumps(payload),
            retain=True,
        )
        self.logger.info("Published Home Assistant status discovery")

    def publish_discovery(self, readings: dict[str, float]) -> None:
        """Publish Home Assistant MQTT discovery config for each reading."""
        for reading_name in readings:
            reading_config = self.reading_configs.get(reading_name)
            reading_id = stable_id(self.service_name, reading_name)
            reading_label = (
                reading_config.display_label
                if reading_config
                else reading_name.replace("_", " ").title()
            )
            payload = {
                "name": reading_label,
                "state_topic": sensor_state_topic(self.service_name, reading_name),
                "expire_after": self._reading_expiry_seconds(),
                "unique_id": reading_id,
                "object_id": reading_id,
                "default_entity_id": entity_id("sensor", self.service_name, reading_name),
                "device": {
                    "identifiers": [self.service_name],
                    "name": self.service_config.device_name,
                },
            }

            if reading_config and reading_config.unit:
                payload["unit_of_measurement"] = reading_config.unit

            if reading_config and reading_config.device_class:
                payload["device_class"] = reading_config.device_class

            if reading_config and reading_config.state_class:
                payload["state_class"] = reading_config.state_class

            self.client.publish(
                sensor_discovery_topic(self.service_name, reading_name),
                json.dumps(payload),
                retain=True,
            )
            self.logger.info("Published Home Assistant discovery for %s", reading_name)

    def _reading_expiry_seconds(self) -> int:
        """Return how long Home Assistant may wait without an MQTT sample."""

        return self.service_config.maximum_reading_age_seconds

    def publish_readings(self, readings: dict[str, float]) -> None:
        """Publish current sensor readings to their MQTT state topics."""
        for reading_name, reading in readings.items():
            self.client.publish(
                sensor_state_topic(self.service_name, reading_name),
                reading,
            )
            #self.logger.info("Published %s reading: %s", reading_name, reading)

    def disconnect(self) -> None:
        """Publish a clean offline state, then stop MQTT networking."""
        publish_result = self.client.publish(
            service_status_topic(self.service_name),
            "offline",
            qos=1,
            retain=True,
        )
        publish_result.wait_for_publish(timeout=2.0)
        self.client.loop_stop()
        self.client.disconnect()
        self.logger.info("Disconnected from MQTT broker")
