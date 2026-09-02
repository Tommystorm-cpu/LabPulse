"""Hardware-free safety and MQTT contracts for controlled outputs."""

import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

from labpulse.common.config import LabPulseConfig, MqttConfig
from labpulse.common.output_config import OutputConfig
from labpulse.hardware.driver import ConnectionLost, HardwareOutputDriver, HardwareReadings
from labpulse.output import service as output_service
from labpulse.output.service import OutputMqttService, output_discovery_payload, parse_output_command


class FakePublishResult:
    """Record that a retained shutdown publish was flushed."""

    def __init__(self) -> None:
        """Start with no wait call."""

        self.waited = False

    def wait_for_publish(self, timeout: float | None = None) -> None:
        """Record the requested flush timeout."""

        self.waited = timeout == 2.0


class FakeMqttClient:
    """Record MQTT lifecycle, subscriptions, and publications in memory."""

    def __init__(self) -> None:
        """Initialize empty call collections and callbacks."""

        self.on_connect = None
        self.on_disconnect = None
        self.on_message = None
        self.published: list[dict[str, object]] = []
        self.subscriptions: list[tuple[str, int]] = []
        self.will: dict[str, object] | None = None
        self.connected_to: tuple[str, int, int] | None = None
        self.loop_started = False
        self.loop_stopped = False
        self.disconnected = False
        self.stop_after_loop_start = None

    def will_set(self, topic: str, payload: str, qos: int, retain: bool) -> None:
        """Record the MQTT Last Will."""

        self.will = {"topic": topic, "payload": payload, "qos": qos, "retain": retain}

    def subscribe(self, topic: str, qos: int) -> None:
        """Record one output command subscription."""

        self.subscriptions.append((topic, qos))

    def connect(self, broker: str, port: int, keepalive: int) -> None:
        """Record broker connection arguments."""

        self.connected_to = (broker, port, keepalive)

    def loop_start(self) -> None:
        """Record loop startup and optionally stop the owning service."""

        self.loop_started = True
        if self.stop_after_loop_start is not None:
            self.stop_after_loop_start()

    def publish(self, topic: str, payload: str, qos: int, retain: bool) -> FakePublishResult:
        """Record one publication and return a flushable result."""

        result = FakePublishResult()
        self.published.append(
            {"topic": topic, "payload": payload, "qos": qos, "retain": retain, "result": result}
        )
        return result

    def loop_stop(self) -> None:
        """Record MQTT network-loop shutdown."""

        self.loop_stopped = True

    def disconnect(self) -> None:
        """Record MQTT disconnection."""

        self.disconnected = True


class FakeOutputDriver(HardwareOutputDriver):
    """In-memory logical output with injectable hardware failures."""

    def __init__(self, safe_state: bool = False) -> None:
        """Initialize the fake output in its safe state."""

        super().__init__("cooling_valve_enable")
        self._safe_state = safe_state
        self.state = safe_state
        self.connected = False
        self.connect_count = 0
        self.close_count = 0
        self.fail_connect = False
        self.fail_write = False
        self.fail_read = False
        self.states: list[bool] = []

    @property
    def safe_state(self) -> bool:
        """Return the fake output's safe logical state."""

        return self._safe_state

    def connect(self) -> None:
        """Connect in the safe state or simulate unavailable hardware."""

        self.connect_count += 1
        if self.fail_connect:
            raise ConnectionLost("simulated unavailable output")
        self.connected = True
        self.state = self.safe_state

    def set_state(self, active: bool) -> None:
        """Apply or reject a logical state."""

        if not self.connected or self.fail_write:
            raise ConnectionLost("simulated output write failure")
        self.state = active
        self.states.append(active)

    def read(self) -> HardwareReadings:
        """Return the currently held logical state."""

        if not self.connected or self.fail_read:
            raise ConnectionLost("simulated output is disconnected")
        return HardwareReadings({"state": 1.0 if self.state else 0.0})

    def close(self) -> None:
        """Return safe and record release."""

        self.state = self.safe_state
        self.connected = False
        self.close_count += 1


def make_config(maximum_active_seconds: float | None = 5.0) -> OutputConfig:
    """Build one validated output configuration."""

    return OutputConfig(
        label="Cooling Valve Enable",
        icon="mdi:valve",
        driver={
            "type": "labpulse.gpio_output",
            "options": {
                "gpio_chip": "/dev/gpiochip0",
                "gpio_line": 18,
                "active_high": True,
                "safe_state": False,
            },
        },
        reconnect_interval_seconds=2,
        maximum_active_seconds=maximum_active_seconds,
    )


def make_service(
    maximum_active_seconds: float | None = 5.0,
) -> tuple[OutputMqttService, FakeOutputDriver, FakeMqttClient]:
    """Build an output service with in-memory GPIO and MQTT collaborators."""

    driver = FakeOutputDriver()
    client = FakeMqttClient()
    service = OutputMqttService(
        "cooling_valve_enable",
        make_config(maximum_active_seconds),
        MqttConfig(broker="mosquitto"),
        driver,
        client,
    )
    return service, driver, client


def message(payload: bytes, *, retain: bool = False, topic: str | None = None) -> object:
    """Build one MQTT-message-shaped command object."""

    return SimpleNamespace(
        topic=topic or "home/output/cooling_valve_enable/set",
        payload=payload,
        retain=retain,
    )


def test_discovery_exposes_a_non_optimistic_home_assistant_switch() -> None:
    """Describe commands, verified state, availability, and stable identity."""

    payload = output_discovery_payload("cooling_valve_enable", make_config())
    expected = {
        "command_topic": "home/output/cooling_valve_enable/set",
        "state_topic": "home/output/cooling_valve_enable/state",
        "availability_topic": "home/output/cooling_valve_enable/availability",
        "unique_id": "labpulse_output_cooling_valve_enable",
        "default_entity_id": "switch.labpulse_output_cooling_valve_enable",
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise AssertionError(f"incorrect discovery {key}: {payload.get(key)!r}")
    if payload["retain"] is not False or payload["qos"] != 1:
        raise AssertionError("Home Assistant commands are not non-retained QoS 1")
    if payload["optimistic"] is not False:
        raise AssertionError("Home Assistant switch does not wait for GPIO readback")


def test_connect_publishes_discovery_safe_state_and_availability() -> None:
    """Expose the switch only after hardware is held in its safe state."""

    service, driver, client = make_service()
    with patch.object(output_service.time, "monotonic", return_value=10.0):
        service._maintain_output()
    service.on_connect(client, None, None, 0, None)

    if not driver.connected or driver.states != [False]:
        raise AssertionError("hardware was not initialized to safe before MQTT availability")
    if client.subscriptions != [("home/output/cooling_valve_enable/set", 1)]:
        raise AssertionError(f"unexpected output subscription: {client.subscriptions!r}")
    topics = [item["topic"] for item in client.published]
    if topics != [
        "homeassistant/switch/labpulse_output_cooling_valve_enable/config",
        "home/output/cooling_valve_enable/state",
        "home/output/cooling_valve_enable/availability",
    ]:
        raise AssertionError(f"unexpected startup publications: {topics!r}")
    discovery = json.loads(str(client.published[0]["payload"]))
    if discovery["name"] != "Cooling Valve Enable":
        raise AssertionError("configured output label was not discovered")
    if client.published[1]["payload"] != "OFF" or client.published[2]["payload"] != "online":
        raise AssertionError("safe startup state and availability were not published")


def test_run_loop_registers_offline_will_and_uses_short_keepalive() -> None:
    """Bound MQTT-loss detection and publish offline when the process disappears."""

    service, driver, client = make_service()
    client.stop_after_loop_start = service.stop
    with patch.object(output_service.time, "monotonic", return_value=10.0):
        service.run_forever()
    if client.will != {
        "topic": "home/output/cooling_valve_enable/availability",
        "payload": "offline",
        "qos": 1,
        "retain": True,
    }:
        raise AssertionError(f"unexpected output Last Will: {client.will!r}")
    if client.connected_to != ("mosquitto", 1883, 15) or not client.loop_started:
        raise AssertionError("output MQTT loop did not use the bounded keepalive")
    if driver.state is not False or driver.close_count != 1:
        raise AssertionError("run-loop shutdown did not release output safely")


def test_live_commands_change_state_but_retained_and_invalid_commands_do_not() -> None:
    """Accept exact live ON/OFF commands and reject replay-prone payloads."""

    service, driver, client = make_service()
    with patch.object(output_service.time, "monotonic", return_value=10.0):
        service._maintain_output()
        service.on_connect(client, None, None, 0, None)
        service.on_message(client, None, message(b"ON"))
        service.on_message(client, None, message(b"OFF", retain=True))
        service.on_message(client, None, message(b"on"))
        service.on_message(client, None, message(b"OFF", topic="other/topic"))
    if driver.state is not True or driver.states != [False, True]:
        raise AssertionError(f"unsafe command was accepted: {driver.states!r}")
    if client.published[-1]["payload"] != "ON":
        raise AssertionError("verified ON state was not published")
    if parse_output_command("OFF") is not False or parse_output_command(b"ON") is not True:
        raise AssertionError("valid output commands were parsed incorrectly")


def test_mqtt_disconnect_immediately_forces_safe_state() -> None:
    """Remove command authority and force the output safe before reconnecting."""

    service, driver, client = make_service()
    with patch.object(output_service.time, "monotonic", return_value=10.0):
        service._maintain_output()
        service.on_connect(client, None, None, 0, None)
        service.on_message(client, None, message(b"ON"))
        service.on_disconnect(client, None, None, 7, None)
    if driver.state is not False or driver.states[-1] is not False:
        raise AssertionError("MQTT disconnect did not force the safe state")


def test_maximum_active_time_forces_safe_without_extension() -> None:
    """Expire an active output even if repeated ON commands attempt to extend it."""

    service, driver, client = make_service(maximum_active_seconds=5.0)
    with patch.object(output_service.time, "monotonic", return_value=10.0):
        service._maintain_output()
        service.on_connect(client, None, None, 0, None)
        service.on_message(client, None, message(b"ON"))
    with patch.object(output_service.time, "monotonic", return_value=13.0):
        service.on_message(client, None, message(b"ON"))
        service._maintain_output()
    if driver.state is not True:
        raise AssertionError("output expired before the original safety deadline")
    with patch.object(output_service.time, "monotonic", return_value=15.1):
        service._maintain_output()
    if driver.state is not False or client.published[-1]["payload"] != "OFF":
        raise AssertionError("maximum active timer did not force and publish safe state")


def test_hardware_failure_goes_offline_and_retries_after_interval() -> None:
    """Reject commands while faulted and reconnect hardware on the configured timer."""

    service, driver, client = make_service()
    driver.fail_connect = True
    with patch.object(output_service.time, "monotonic", return_value=10.0):
        service._maintain_output()
        service.on_connect(client, None, None, 0, None)
    if client.published[-1]["payload"] != "offline":
        raise AssertionError("unavailable GPIO was not published offline")
    service.on_message(client, None, message(b"ON"))
    if driver.state is not False:
        raise AssertionError("command changed an unavailable output")

    driver.fail_connect = False
    with patch.object(output_service.time, "monotonic", return_value=11.9):
        service._maintain_output()
    if driver.connect_count != 1:
        raise AssertionError("hardware retried before reconnect interval")
    with patch.object(output_service.time, "monotonic", return_value=12.1):
        service._maintain_output()
    if driver.connect_count != 2 or client.published[-1]["payload"] != "online":
        raise AssertionError("hardware did not recover after reconnect interval")


def test_failed_readback_never_publishes_available() -> None:
    """Keep the switch unavailable when its initial GPIO verification fails."""

    service, driver, client = make_service()
    with patch.object(output_service.time, "monotonic", return_value=10.0):
        service._maintain_output()
    driver.fail_read = True
    service.on_connect(client, None, None, 0, None)
    availability = [
        item["payload"]
        for item in client.published
        if item["topic"] == "home/output/cooling_valve_enable/availability"
    ]
    if availability != ["offline"]:
        raise AssertionError(f"failed output readback published unsafe availability: {availability!r}")


def test_shutdown_forces_safe_and_flushes_offline_state() -> None:
    """Return safe before release and flush retained offline availability."""

    service, driver, client = make_service()
    with patch.object(output_service.time, "monotonic", return_value=10.0):
        service._maintain_output()
        service.on_connect(client, None, None, 0, None)
        service.on_message(client, None, message(b"ON"))
        service.close()
        service.close()
    if driver.state is not False or driver.close_count != 1:
        raise AssertionError("output shutdown was not safe and idempotent")
    offline = client.published[-1]
    if offline["payload"] != "offline" or not offline["result"].waited:
        raise AssertionError("shutdown availability was not retained and flushed")
    if not client.loop_stopped or not client.disconnected:
        raise AssertionError("MQTT client was not closed")


def test_output_configuration_separates_actuators_and_detects_line_conflicts() -> None:
    """Keep output drivers out of sensors and reject duplicate GPIO ownership."""

    base = {
        "mqtt": {"broker": "mosquitto"},
        "setups": {"test_setup": {}},
        "services": {},
        "outputs": {
            "cooling_valve_enable": {
                "label": "Cooling Valve Enable",
                "driver": {
                    "type": "labpulse.gpio_output",
                    "options": {"gpio_line": 18, "safe_state": False},
                },
                "maximum_active_seconds": 30,
            }
        },
    }
    config = LabPulseConfig.model_validate(base)
    if config.outputs["cooling_valve_enable"].maximum_active_seconds != 30:
        raise AssertionError("validated output timing was not retained")

    sensor_with_output_driver = {
        **base,
        "outputs": {},
        "services": {
            "wrong": {
                "label": "Wrong",
                "driver": {
                    "type": "labpulse.gpio_output",
                    "options": {"gpio_line": 18},
                },
                "measurements": {"state": {"setups": ["test_setup"]}},
            }
        },
    }
    try:
        LabPulseConfig.model_validate(sensor_with_output_driver)
    except ValueError as error:
        if "top-level outputs" not in str(error):
            raise
    else:
        raise AssertionError("output driver was accepted as a sensor service")

    conflicting = {
        **base,
        "services": {
            "contact": {
                "label": "Contact",
                "driver": {
                    "type": "labpulse.gpio_input",
                    "options": {"gpio_line": 18},
                },
                "measurements": {"state": {"setups": ["test_setup"]}},
            }
        },
    }
    try:
        LabPulseConfig.model_validate(conflicting)
    except ValueError as error:
        if "both use /dev/gpiochip0 line 18" not in str(error):
            raise
    else:
        raise AssertionError("duplicate GPIO line ownership was accepted")


def test_maximum_active_time_requires_false_safe_state() -> None:
    """Reject a watchdog policy whose target is itself logically active."""

    try:
        OutputConfig(
            label="Unsafe timer",
            driver={
                "type": "labpulse.gpio_output",
                "options": {"gpio_line": 18, "safe_state": True},
            },
            maximum_active_seconds=10,
        )
    except ValueError as error:
        if "safe_state: false" not in str(error):
            raise
    else:
        raise AssertionError("active safe state was accepted with an active-time limit")
