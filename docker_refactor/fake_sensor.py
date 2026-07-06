import random
import time
import paho.mqtt.client as mqtt
from labpulse_common.config import load_config
import json

sys_config = load_config()
cfg = sys_config.pressure_monitor
mqtt_cfg = sys_config.mqtt

MQTT_BROKER = mqtt_cfg.broker
MQTT_PORT = mqtt_cfg.port

SENSOR_ID = "fake_sensor"

STATE_TOPIC = f"home/sensor/{SENSOR_ID}/state"

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="PressureMonitor")

def read_fake_sensor():
    return {
        "pressure_bar": round(random.uniform(0.95, 1.10), 3),
        "temperature_c": round(random.uniform(20.0, 24.0), 1),
        "pump_running": random.choice([True, True, True, False]),
    }

def publish_discovery():
    # 1. Generate the actual Sensor Reading
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

def publish_readings(reading):
    mqtt_client.publish(STATE_TOPIC, reading)

def main():
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()

    publish_discovery()

    while True:
        reading = read_fake_sensor()["pressure_bar"]
        publish_readings(reading)
        print(reading)
        time.sleep(1)

if __name__ == "__main__":
    main()
