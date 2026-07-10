"""Hand hardware readings to Home Assistant through MQTT discovery/state."""

import json
import logging

import paho.mqtt.client as mqtt

from labpulse_common.config import MqttConfig, ReadingConfig, ServiceConfig
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
        self.discovered_readings: set[str] = set()
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
            reading_config = self.reading_config_for(reading_name)
            if reading_config:
                configured[reading_name] = reading
            else:
                self.logger.warning("Ignoring unconfigured reading: %s", reading_name)

        return configured

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
            "unique_id": self.discovery_id("status"),
            "object_id": self.object_id("status"),
            "default_entity_id": self.default_entity_id("status"),
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
        """Publish Home Assistant MQTT discovery config for each reading."""
        for reading_name in readings:
            reading_config = self.reading_config_for(reading_name)
            payload = {
                "name": self.reading_label(reading_name, reading_config),
                "state_topic": self.state_topic(reading_name),
                "unique_id": self.discovery_id(reading_name),
                "object_id": self.object_id(reading_name),
                "default_entity_id": self.default_entity_id(reading_name),
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
                self.discovery_topic(reading_name),
                json.dumps(payload),
                retain=True,
            )
            self.logger.info("Published Home Assistant discovery for %s", reading_name)

    def publish_readings(self, readings: dict[str, float]) -> None:
        """Publish current sensor readings to their MQTT state topics."""
        for reading_name, reading in readings.items():
            self.client.publish(self.state_topic(reading_name), reading)
            #self.logger.info("Published %s reading: %s", reading_name, reading)

    def disconnect(self) -> None:
        """Stop MQTT networking and disconnect from the broker."""
        self.client.loop_stop()
        self.client.disconnect()
        self.logger.info("Disconnected from MQTT broker")

    def state_topic(self, reading_name: str) -> str:
        """Return the MQTT state topic for one reading."""
        return sensor_state_topic(self.service_name, reading_name)

    def status_topic(self) -> str:
        """Return the MQTT state topic for this service's health status."""

        return service_status_topic(self.service_name)

    def discovery_topic(self, reading_name: str) -> str:
        """Return the Home Assistant discovery topic for one reading."""
        return sensor_discovery_topic(self.service_name, reading_name)

    def status_discovery_topic(self) -> str:
        """Return the Home Assistant discovery topic for service status."""

        return status_discovery_topic(self.service_name)

    def discovery_id(self, reading_name: str) -> str:
        """Return the stable LabPulse MQTT discovery and object identifier."""

        return stable_id(self.service_name, reading_name)

    def object_id(self, reading_name: str) -> str:
        """Return the Home Assistant object ID for one discovered entity.

        The object ID intentionally matches the stable discovery ID so Home
        Assistant creates predictable entity IDs such as
        `sensor.labpulse_pressure_monitor_pressure`.
        """

        return self.discovery_id(reading_name)

    def default_entity_id(self, reading_name: str) -> str:
        """Return the preferred Home Assistant entity ID for discovery.

        Home Assistant MQTT discovery uses `default_entity_id` to choose the
        initial entity ID. `object_id` alone is not enough to make dashboard
        entity IDs predictable.
        """

        return entity_id("sensor", self.service_name, reading_name)

    def reading_config_for(self, reading_name: str) -> ReadingConfig | None:
        """Return configured metadata for a published reading name."""

        for reading in self.service_config.readings:
            if reading_name == reading.name:
                return reading

        return None

    @staticmethod
    def reading_label(
        reading_name: str,
        reading_config: ReadingConfig | None,
    ) -> str:
        """Return the configured label, or a title-cased fallback."""

        if reading_config:
            return reading_config.display_label

        return reading_name.replace("_", " ").title()
