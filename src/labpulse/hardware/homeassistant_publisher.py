"""Hand hardware measurements to Home Assistant through MQTT discovery/state."""

import json
import logging
from typing import Any

import paho.mqtt.client as mqtt

from labpulse.common.config import MeasurementConfig, MqttConfig, ServiceConfig
from labpulse.common.identity import entity_id, stable_id
from labpulse.common.mqtt_contracts import (
    sensor_discovery_topic,
    sensor_state_topic,
    service_status_topic,
    status_discovery_topic,
)


DEFAULT_MEASUREMENT_ICONS = {
    "battery": "mdi:battery",
    "current": "mdi:current-dc",
    "energy": "mdi:lightning-bolt-circle",
    "humidity": "mdi:water-percent",
    "power": "mdi:lightning-bolt",
    "pressure": "mdi:gauge",
    "signal_strength": "mdi:wifi",
    "temperature": "mdi:thermometer",
    "voltage": "mdi:flash",
    "volume_flow_rate": "mdi:pipe-valve",
}
DEFAULT_MEASUREMENT_ICON = "mdi:chart-line"


def measurement_icon(device_class: str | None, override: str | None) -> str:
    """Return an explicit icon without enabling Home Assistant unit conversion."""

    if override:
        return override
    if device_class:
        return DEFAULT_MEASUREMENT_ICONS.get(
            device_class,
            DEFAULT_MEASUREMENT_ICON,
        )
    return DEFAULT_MEASUREMENT_ICON


def status_discovery_payload(
    service_name: str,
    device_name: str,
) -> dict[str, Any]:
    """Build the Home Assistant discovery document for service health."""

    status_id = stable_id(service_name, "status")
    return {
        "name": "Status",
        "state_topic": service_status_topic(service_name),
        "unique_id": status_id,
        "object_id": status_id,
        "default_entity_id": entity_id("sensor", service_name, "status"),
        "icon": "mdi:heart-pulse",
        "device": {
            "identifiers": [service_name],
            "name": device_name,
        },
    }


def measurement_discovery_payload(
    service_name: str,
    device_name: str,
    measurement: MeasurementConfig,
    expire_after: int,
) -> dict[str, Any]:
    """Build one measurement discovery document without publishing it."""

    measurement_id = stable_id(service_name, measurement.name)
    payload: dict[str, Any] = {
        "name": measurement.display_label,
        "state_topic": sensor_state_topic(service_name, measurement.name),
        "expire_after": expire_after,
        "unique_id": measurement_id,
        "object_id": measurement_id,
        "default_entity_id": entity_id("sensor", service_name, measurement.name),
        "device": {
            "identifiers": [service_name],
            "name": device_name,
        },
    }
    if measurement.unit:
        payload["unit_of_measurement"] = measurement.unit
    # Home Assistant converts numeric values when a convertible device class
    # is present. LabPulse treats the configured unit as the data contract, so
    # discovery publishes an icon while device_class stays internal metadata.
    payload["icon"] = measurement_icon(
        measurement.device_class,
        measurement.icon,
    )
    if measurement.state_class:
        payload["state_class"] = measurement.state_class
    return payload


class HomeAssistantMqttPublisher:
    """Publish LabPulse measurements through MQTT and Home Assistant discovery."""

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
        # Index once because every driver batch is filtered against the same
        # service contract before either discovery or state is published.
        self.measurement_configs = {
            measurement.name: measurement
            for measurement in service_config.measurements
        }
        # Discovery is retained by MQTT, so it only needs publishing when a
        # configured measurement first appears or the broker reconnects.
        self.discovered_measurements: set[str] = set()
        self.status_discovery_published = False
        self.current_status: str | None = None
        self.logger = logging.getLogger(f"HomeAssistantMqtt.{service_name}")
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"LabPulse-{service_name}",
        )

    def connect(self) -> None:
        """Connect to the MQTT broker and start the background network loop."""

        self.client.on_connect = self._on_connect
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
        """Publish discovery for new names, followed by their current values."""

        # A typo or extra key from a driver must never create an undeclared Home
        # Assistant entity. The warning remains visible to the operator.
        measurements = self.configured_measurements(measurements)
        undiscovered_measurements = {
            measurement_name: measurement
            for measurement_name, measurement in measurements.items()
            if measurement_name not in self.discovered_measurements
        }

        if undiscovered_measurements:
            # Home Assistant must know the entity before its first state arrives.
            self.publish_discovery(undiscovered_measurements)
            self.discovered_measurements.update(undiscovered_measurements)

        self.publish_measurements(measurements)

    def configured_measurements(self, measurements: dict[str, float]) -> dict[str, float]:
        """Return only measurements declared exactly in this service's config."""

        configured: dict[str, float] = {}
        for measurement_name, value in measurements.items():
            if measurement_name in self.measurement_configs:
                configured[measurement_name] = value
            else:
                self.logger.warning(
                    "Ignoring unconfigured measurement: %s",
                    measurement_name,
                )

        return configured

    def publish_status(self, status: str) -> None:
        """Publish the service health status as a retained Home Assistant entity."""

        self.current_status = status
        if not self.status_discovery_published:
            self.publish_status_discovery()
            self.status_discovery_published = True

        self.client.publish(
            service_status_topic(self.service_name),
            status,
            qos=1,
            retain=True,
        )
        self.logger.info("Published service status: %s", status)

    def _on_connect(
        self,
        client: mqtt.Client,
        _userdata: object,
        _flags: Any,
        reason_code: Any,
        _properties: Any,
    ) -> None:
        """Restore retained discovery and service status after every connection."""

        if getattr(reason_code, "is_failure", False):
            self.logger.error("MQTT connection failed: %s", reason_code)
            return

        # A broker restart can retain the client's Last Will ``offline`` state.
        # The runner may still be internally online and suppress an identical
        # status transition, so reconnect handling must restore that fact.
        self.publish_status_discovery()
        self.status_discovery_published = True

        if self.discovered_measurements:
            self.publish_discovery(
                {
                    measurement_name: 0.0
                    for measurement_name in self.discovered_measurements
                }
            )

        if self.current_status is not None:
            client.publish(
                service_status_topic(self.service_name),
                self.current_status,
                qos=1,
                retain=True,
            )
            self.logger.info(
                "Republished service status after MQTT connection: %s",
                self.current_status,
            )

    def publish_status_discovery(self) -> None:
        """Publish Home Assistant MQTT discovery config for service status."""

        self.client.publish(
            status_discovery_topic(self.service_name),
            json.dumps(
                status_discovery_payload(
                    self.service_name,
                    self.service_config.device_name,
                )
            ),
            retain=True,
        )
        self.logger.info("Published Home Assistant status discovery")

    def publish_discovery(self, measurements: dict[str, float]) -> None:
        """Publish Home Assistant MQTT discovery config for each measurement."""

        for measurement_name in measurements:
            payload = measurement_discovery_payload(
                self.service_name,
                self.service_config.device_name,
                self.measurement_configs[measurement_name],
                self._measurement_expiry_seconds(),
            )

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

    def disconnect(self) -> None:
        """Publish a clean offline state, then stop MQTT networking."""

        # Flush the retained offline state before stopping the network loop. If
        # the process dies unexpectedly, the broker's Last Will covers this path.
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
