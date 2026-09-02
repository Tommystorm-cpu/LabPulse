"""Safely coordinate one physical output with a Home Assistant MQTT switch."""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import paho.mqtt.client as mqtt

from labpulse.common.config import MqttConfig
from labpulse.common.identity import entity_id, stable_id
from labpulse.common.mqtt_contracts import (
    output_availability_topic,
    output_command_topic,
    output_discovery_topic,
    output_state_topic,
)
from labpulse.common.output_config import OutputConfig
from labpulse.hardware.driver import DriverError, HardwareOutputDriver


OUTPUT_MQTT_KEEPALIVE_SECONDS = 15


def output_discovery_payload(output_name: str, config: OutputConfig) -> dict[str, Any]:
    """Build Home Assistant MQTT discovery for one controlled output."""

    output_id = stable_id("output", output_name)
    return {
        "name": config.label,
        "command_topic": output_command_topic(output_name),
        "state_topic": output_state_topic(output_name),
        "availability_topic": output_availability_topic(output_name),
        "payload_on": "ON",
        "payload_off": "OFF",
        "state_on": "ON",
        "state_off": "OFF",
        "payload_available": "online",
        "payload_not_available": "offline",
        "qos": 1,
        "retain": False,
        "optimistic": False,
        "unique_id": output_id,
        "object_id": output_id,
        "default_entity_id": entity_id("switch", "output", output_name),
        "icon": config.icon,
        "device": {
            "identifiers": [f"output_{output_name}"],
            "name": config.label,
        },
    }


def parse_output_command(payload: bytes | str) -> bool:
    """Decode the exact non-retained ON/OFF payload emitted by Home Assistant."""

    try:
        text = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    except UnicodeDecodeError as error:
        raise ValueError("payload is not valid UTF-8") from error
    if text == "ON":
        return True
    if text == "OFF":
        return False
    raise ValueError("payload must be exactly ON or OFF")


class OutputMqttService:
    """Own one output, subscribe to commands, and enforce its safe-state policy."""

    def __init__(
        self,
        output_name: str,
        output_config: OutputConfig,
        mqtt_config: MqttConfig,
        driver: HardwareOutputDriver,
        client: mqtt.Client,
    ) -> None:
        """Store required collaborators and initialize worker lifecycle state."""

        self.output_name = output_name
        self.output_config = output_config
        self.mqtt_config = mqtt_config
        self.driver = driver
        self.client = client
        self._logger = logging.getLogger(f"LabPulse.Output.{output_name}")
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._driver_ready = False
        self._mqtt_connected = False
        self._next_driver_connect_at = 0.0
        self._active_deadline: float | None = None
        self._closed = False

    def run_forever(self) -> None:
        """Connect MQTT, retry hardware, and enforce the maximum active time."""

        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.will_set(
            output_availability_topic(self.output_name),
            payload="offline",
            qos=1,
            retain=True,
        )
        self._maintain_output()
        self._logger.info(
            "Connecting to MQTT broker %s:%s",
            self.mqtt_config.broker,
            self.mqtt_config.port,
        )
        try:
            self.client.connect(
                self.mqtt_config.broker,
                self.mqtt_config.port,
                OUTPUT_MQTT_KEEPALIVE_SECONDS,
            )
            self.client.loop_start()
            while not self._stop_event.wait(0.1):
                self._maintain_output()
        finally:
            self.close()

    def stop(self) -> None:
        """Ask the main worker loop to stop at its next short wake-up."""

        self._stop_event.set()

    def on_connect(
        self,
        client: mqtt.Client,
        _userdata: object,
        _flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        """Restore discovery, command subscription, state, and availability."""

        if reason_code != 0:
            self._logger.error("Output MQTT connection failed: %s", reason_code)
            return
        self._mqtt_connected = True
        client.subscribe(output_command_topic(self.output_name), qos=1)
        self._publish(
            output_discovery_topic(self.output_name),
            json.dumps(
                output_discovery_payload(self.output_name, self.output_config),
                separators=(",", ":"),
            ),
            retain=True,
        )
        with self._lock:
            if self._driver_ready and self._publish_current_state():
                self._publish_availability("online")
            else:
                self._publish_availability("offline")

    def on_disconnect(
        self,
        _client: mqtt.Client,
        _userdata: object,
        _disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        """Apply the safe state whenever command authority is disconnected."""

        self._mqtt_connected = False
        with self._lock:
            if self._driver_ready:
                self._apply_state(self.driver.safe_state, "MQTT disconnected", publish=False)
        if reason_code != 0:
            self._logger.warning("MQTT disconnected; output forced safe: %s", reason_code)

    def on_message(
        self,
        _client: mqtt.Client,
        _userdata: object,
        message: mqtt.MQTTMessage,
    ) -> None:
        """Validate and apply one live Home Assistant output command."""

        if message.topic != output_command_topic(self.output_name):
            self._logger.warning("Rejected output command from unexpected topic: %s", message.topic)
            return
        if message.retain:
            self._logger.warning("Rejected retained output command")
            return
        try:
            active = parse_output_command(message.payload)
        except ValueError as error:
            self._logger.warning("Rejected invalid output command: %s", error)
            return

        with self._lock:
            if not self._driver_ready:
                self._logger.warning("Rejected output command while GPIO hardware is unavailable")
                return
            self._apply_state(active, "Home Assistant command", publish=True)

    def close(self) -> None:
        """Force the safe state, publish offline, and release all resources."""

        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._driver_ready:
                self._apply_state(self.driver.safe_state, "service shutdown", publish=True)
            self.driver.close()
            self._driver_ready = False
            self._active_deadline = None

        if self._mqtt_connected:
            result = self.client.publish(
                output_availability_topic(self.output_name),
                "offline",
                qos=1,
                retain=True,
            )
            result.wait_for_publish(timeout=2.0)
        self.client.loop_stop()
        self.client.disconnect()
        self._mqtt_connected = False
        self._logger.info("Output service stopped in safe state")

    def _maintain_output(self) -> None:
        """Retry unavailable hardware and expire an overlong active command."""

        now = time.monotonic()
        with self._lock:
            if not self._driver_ready:
                if now < self._next_driver_connect_at:
                    return
                try:
                    self.driver.connect()
                    self.driver.set_state(self.driver.safe_state)
                except (DriverError, OSError, ValueError) as error:
                    self.driver.close()
                    self._next_driver_connect_at = (
                        now + self.output_config.reconnect_interval_seconds
                    )
                    self._logger.error("Output hardware unavailable: %s", error)
                    if self._mqtt_connected:
                        self._publish_availability("offline")
                    return
                self._driver_ready = True
                self._active_deadline = None
                self._logger.info("Output hardware ready in safe state")
                if self._mqtt_connected:
                    if self._publish_current_state():
                        self._publish_availability("online")
                    else:
                        self._publish_availability("offline")
                return

            if self._active_deadline is not None and now >= self._active_deadline:
                self._logger.warning("Maximum active time reached; forcing output safe")
                self._apply_state(self.driver.safe_state, "maximum active time", publish=True)

    def _apply_state(self, active: bool, reason: str, *, publish: bool) -> None:
        """Set one state, or mark the hardware unavailable after a failed write."""

        try:
            self.driver.set_state(active)
            readings = self.driver.read()
        except (DriverError, OSError, ValueError) as error:
            self._logger.error("Output state change failed during %s: %s", reason, error)
            self.driver.close()
            self._driver_ready = False
            self._active_deadline = None
            self._next_driver_connect_at = (
                time.monotonic() + self.output_config.reconnect_interval_seconds
            )
            if self._mqtt_connected:
                self._publish_availability("offline")
            return

        active_now = readings.values.get("state") == 1.0
        if active_now and self.output_config.maximum_active_seconds is not None:
            # Repeated ON commands do not extend an existing safety window.
            if self._active_deadline is None:
                self._active_deadline = (
                    time.monotonic() + self.output_config.maximum_active_seconds
                )
        else:
            self._active_deadline = None
        self._logger.info("Output state is %s (%s)", "ON" if active_now else "OFF", reason)
        if publish and self._mqtt_connected:
            self._publish_state(active_now)

    def _publish_current_state(self) -> bool:
        """Publish current logical state and report whether readback succeeded."""

        try:
            readings = self.driver.read()
        except (DriverError, OSError, ValueError) as error:
            self._logger.error("Output readback failed: %s", error)
            self.driver.close()
            self._driver_ready = False
            self._next_driver_connect_at = (
                time.monotonic() + self.output_config.reconnect_interval_seconds
            )
            return False
        self._publish_state(readings.values.get("state") == 1.0)
        return True

    def _publish_state(self, active: bool) -> None:
        """Publish the verified logical output state as retained ON or OFF."""

        self._publish(
            output_state_topic(self.output_name),
            "ON" if active else "OFF",
            retain=True,
        )

    def _publish_availability(self, state: str) -> None:
        """Publish whether this worker can currently control its GPIO line."""

        self._publish(output_availability_topic(self.output_name), state, retain=True)

    def _publish(self, topic: str, payload: str, *, retain: bool) -> Any:
        """Publish one output message with the shared QoS-one policy."""

        return self.client.publish(topic, payload, qos=1, retain=retain)
