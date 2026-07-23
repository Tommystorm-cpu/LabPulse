"""Hand hardware measurements to Home Assistant through MQTT discovery/state."""

import json
import logging

import paho.mqtt.client as mqtt

from labpulse.common.config import MqttConfig, ServiceConfig
from labpulse.common.identity import entity_id, stable_id
from labpulse.common.mqtt_contracts import (
    sensor_discovery_topic,
    sensor_state_topic,
    service_status_topic,
    status_discovery_topic,
)


class HomeAssistantMqttPublisher:
    """
    Publishes LabPulse measurements to MQTT using Home Assistant discovery.
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
        self.measurement_configs = {
            measurement.name: measurement
            for measurement in service_config.measurements
        }
        self.discovered_measurements: set[str] = set()
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

    def publish(self, measurements: dict[str, float]) -> None:
        """
        Publish Home Assistant discovery for new measurements, then publish values.
        """
        measurements = self.configured_measurements(measurements)
        undiscovered_measurements = {
            measurement_name: measurement
            for measurement_name, measurement in measurements.items()
            if measurement_name not in self.discovered_measurements
        }

        if undiscovered_measurements:
            self.publish_discovery(undiscovered_measurements)
            self.discovered_measurements.update(undiscovered_measurements)

        self.publish_measurements(measurements)

    def configured_measurements(self, measurements: dict[str, float]) -> dict[str, float]:
        """Return only measurements declared exactly in this service's config."""

        configured = {}

        for measurement_name, measurement in measurements.items():
            if measurement_name in self.measurement_configs:
                configured[measurement_name] = measurement
            else:
                self.logger.warning("Ignoring unconfigured measurement: %s", measurement_name)

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

    def publish_discovery(self, measurements: dict[str, float]) -> None:
        """Publish Home Assistant MQTT discovery config for each measurement."""
        for measurement_name in measurements:
            measurement_config = self.measurement_configs.get(measurement_name)
            measurement_id = stable_id(self.service_name, measurement_name)
            measurement_label = (
                measurement_config.display_label
                if measurement_config
                else measurement_name.replace("_", " ").title()
            )
            payload = {
                "name": measurement_label,
                "state_topic": sensor_state_topic(self.service_name, measurement_name),
                "expire_after": self._measurement_expiry_seconds(),
                "unique_id": measurement_id,
                "object_id": measurement_id,
                "default_entity_id": entity_id("sensor", self.service_name, measurement_name),
                "device": {
                    "identifiers": [self.service_name],
                    "name": self.service_config.device_name,
                },
            }

            if measurement_config and measurement_config.unit:
                payload["unit_of_measurement"] = measurement_config.unit

            if measurement_config and measurement_config.device_class:
                payload["device_class"] = measurement_config.device_class

            if measurement_config and measurement_config.state_class:
                payload["state_class"] = measurement_config.state_class

            self.client.publish(
                sensor_discovery_topic(self.service_name, measurement_name),
                json.dumps(payload),
                retain=True,
            )
            self.logger.info("Published Home Assistant discovery for %s", measurement_name)

    def _measurement_expiry_seconds(self) -> int:
        """Return how long Home Assistant may wait without an MQTT sample."""

        return self.service_config.maximum_measurement_age_seconds

    def publish_measurements(self, measurements: dict[str, float]) -> None:
        """Publish current sensor measurements to their MQTT state topics."""
        for measurement_name, measurement in measurements.items():
            self.client.publish(
                sensor_state_topic(self.service_name, measurement_name),
                measurement,
            )
            #self.logger.info("Published %s measurement: %s", measurement_name, measurement)

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
