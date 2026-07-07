import json
import logging
import random
import time

import serial
import paho.mqtt.client as mqtt

from labpulse_common.config import load_config
from labpulse_common.logging_config import configure_logging

configure_logging("fake_sensor")
logger = logging.getLogger("FakeSensor")

sys_config = load_config()
cfg = sys_config.services["pressure_monitor"]
mqtt_cfg = sys_config.mqtt

MQTT_BROKER = mqtt_cfg.broker
MQTT_PORT = mqtt_cfg.port

SENSOR_ID = "fake_sensor"

STATE_TOPIC = f"home/sensor/{SENSOR_ID}/state"

def read_fake_sensor() -> dict[str, object]:
    """Return a synthetic pressure-style reading for manual MQTT testing."""

    return {
        "pressure_bar": round(random.uniform(0.95, 1.10), 3),
        "temperature_c": round(random.uniform(20.0, 24.0), 1),
        "pump_running": random.choice([True, True, True, False]),
    }

def create_mqtt_client() -> mqtt.Client:
    """Create the MQTT client used by this legacy smoke-test script."""

    return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="PressureMonitor")


def open_serial_port() -> object:
    """Open the configured pressure-monitor serial port."""

    return serial.Serial(
        cfg.serial_port,
        cfg.baud_rate,
        timeout=2,
    )


def publish_discovery(mqtt_client: mqtt.Client) -> None:
    """Publish the Home Assistant discovery payload for the legacy fake sensor."""

    # This file predates the generic publisher in homeassistant_mqtt.py and is
    # kept as a simple manual smoke-test script.
    sensor_payload = {
        "name": "Air Pressure",
        "state_topic": STATE_TOPIC,
        "unit_of_measurement": "bar",
        "unique_id": f"{SENSOR_ID}_reading",
        "device": {
            "identifiers": ["fake_arduino"],
            "name": "Fake Sensor Hub"
        }
    }
    mqtt_client.publish(f"homeassistant/sensor/{SENSOR_ID}/config", json.dumps(sensor_payload), retain=True)

def publish_readings(mqtt_client: mqtt.Client, reading: float) -> None:
    """Publish one pressure reading to the fake sensor state topic."""

    mqtt_client.publish(STATE_TOPIC, reading)

def main() -> None:
    """Run the legacy pressure-only fake sensor publisher forever."""

    mqtt_client = create_mqtt_client()
    ser = open_serial_port()

    logger.info("Connecting to MQTT broker %s:%s", MQTT_BROKER, MQTT_PORT)
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()

    publish_discovery(mqtt_client)
    logger.info("Published Home Assistant discovery for %s", SENSOR_ID)
    logger.info("Reading pressure data from %s at %s baud", cfg.serial_port, cfg.baud_rate)

    while True:
        line = ser.readline().decode("utf-8").strip()

        if not line:
            continue

        pressure_bar = round(float(line) * 10.0, 2)

        publish_readings(mqtt_client, pressure_bar)
        logger.info("Published pressure reading: %s bar", pressure_bar)

if __name__ == "__main__":
    main()
