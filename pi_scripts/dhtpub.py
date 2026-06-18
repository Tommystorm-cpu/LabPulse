import sys
import time
import json
import logging
import adafruit_dht
import board
import paho.mqtt.client as mqtt
from labpulse_common.config import load_config
from labpulse_common.mqtt_health import ServiceHealthTracker

# === LOGGING SETUP ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("DHT11Monitor")

# === DYNAMIC CONFIGURATION (Pydantic Dot-Notation) ===
sys_config = load_config()
cfg = sys_config.dht11
mqtt_cfg = sys_config.mqtt

MQTT_BROKER = mqtt_cfg.broker
MQTT_PORT = mqtt_cfg.port
DISCOVERY_PREFIX = "homeassistant"
STATE_TOPIC = cfg.state_topic
DEVICE_ID = cfg.device_id

# Initialize DHT Device safely
DHT_PIN = getattr(board, cfg.pin)
dht_device = adafruit_dht.DHT11(DHT_PIN)

mqtt_client = mqtt.Client(client_id="DHT11Monitor")

def publish_discovery():
    temp_config = {
        "name": "Room Temperature",
        "state_topic": STATE_TOPIC,
        "unit_of_measurement": "C",
        "value_template": "{{ value_json.temperature }}",
        "unique_id": "room_temperature_dht11",
        "device": {"identifiers": [DEVICE_ID], "name": "DHT11 Sensor", "model": "DHT11", "manufacturer": "Adafruit"},
    }
    humidity_config = {
        "name": "Room Humidity",
        "state_topic": STATE_TOPIC,
        "unit_of_measurement": "%",
        "value_template": "{{ value_json.humidity }}",
        "unique_id": "room_humidity_dht11",
        "device": {"identifiers": [DEVICE_ID], "name": "DHT11 Sensor", "model": "DHT11", "manufacturer": "Adafruit"},
    }
    mqtt_client.publish(f"{DISCOVERY_PREFIX}/sensor/{DEVICE_ID}/temperature/config", json.dumps(temp_config), retain=True)
    mqtt_client.publish(f"{DISCOVERY_PREFIX}/sensor/{DEVICE_ID}/humidity/config", json.dumps(humidity_config), retain=True)
    logger.info("MQTT discovery messages published")

def read_and_publish():
    try:
        temperature = dht_device.temperature
        humidity = dht_device.humidity

        if humidity is not None and temperature is not None:
            payload = {"temperature": round(temperature, 1), "humidity": round(humidity, 1)}
            mqtt_client.publish(STATE_TOPIC, json.dumps(payload))
        else:
            logger.warning("Sensor returned None")

    except RuntimeError as error:
        logger.warning(f"DHT timing error (common): {error.args[0]}")
    except Exception as error:
        logger.error(f"Unexpected DHT error: {error}", exc_info=True)

def main():
    logger.info("Initializing DHT11 Monitor Service...")
    health_tracker = ServiceHealthTracker(mqtt_client, "dht11_monitor")

    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        publish_discovery()
    except Exception as e:
        logger.error(f"MQTT Boot Error: {e}")
        sys.exit(1)

    try:
        while True:
            # Tell Home Assistant the loop is running
            health_tracker.update()
            
            try:
                read_and_publish()
            except Exception as e:
                logger.error(f"Minor processing error: {e}", exc_info=True)

            time.sleep(3)

    except KeyboardInterrupt:
        logger.info("Exiting cleanly via KeyboardInterrupt...")
    except Exception as e:
        logger.error(f"Unexpected crash in main loop: {e}", exc_info=True)
    finally:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        dht_device.exit()
        logger.info("Service shut down successfully.")

if __name__ == "__main__":
    main()
