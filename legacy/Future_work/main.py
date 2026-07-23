import time
import json
import logging
import sys
import paho.mqtt.client as mqtt

from labpulse_common.config import load_config
from labpulse_common.sensor_factory import SensorFactory
from labpulse_common.mqtt_health import ServiceHealthTracker
# If you ported over your SMS/Thresholds, you can import them here too!

# === SETUP LOGGING ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("LabPulseHub")

# === GLOBALS ===
DISCOVERY_TOPICS = set()
STATE_TOPICS = {}

def publish_discovery(mqtt_client, sensor_key):
    """Pushes Home Assistant auto-discovery configs dynamically."""
    if sensor_key in DISCOVERY_TOPICS:
        return

    unit = ""
    if "temp" in sensor_key: unit = "C"
    elif "hum" in sensor_key: unit = "%"
    elif "press" in sensor_key: unit = "bar"
    elif "flow" in sensor_key: unit = "L/min"
    elif "volt" in sensor_key: unit = "V"

    discovery_payload = {
        "name": sensor_key.replace("_", " ").title(),
        "state_topic": STATE_TOPICS[sensor_key],
        "unit_of_measurement": unit,
        "unique_id": sensor_key,
        "device": {
            "identifiers": ["labpulse_universal_hub"],
            "name": "LabPulse V2 Master Hub"
        }
    }
    discovery_topic = f"homeassistant/sensor/{sensor_key}/config"
    mqtt_client.publish(discovery_topic, json.dumps(discovery_payload), retain=True)
    DISCOVERY_TOPICS.add(sensor_key)

def main():
    logger.info("Initializing LabPulse v2.0 Master Hub...")

    # 1. Load the Pydantic Blueprint
    config = load_config()

    # 2. Setup universal MQTT Connection
    mqtt_client = mqtt.Client(client_id="LabPulseMaster")
    try:
        mqtt_client.connect(config.mqtt.broker, config.mqtt.port, 60)
        mqtt_client.loop_start()
        logger.info(f"Connected to Universal MQTT Broker at {config.mqtt.broker}")
    except Exception as e:
        logger.error(f"MQTT Boot Error: {e}")
        sys.exit(1)

    health_tracker = ServiceHealthTracker(mqtt_client, "labpulse_master_hub")

    # 3. Spin up the Factory and Load Drivers
    factory = SensorFactory()
    active_sensors = factory.build_all(config)

    if not active_sensors:
        logger.error("CRITICAL: No sensors were successfully loaded. Halting Hub.")
        sys.exit(1)

    # 4. Connect Hardware safely
    for sensor_id, driver in active_sensors.items():
        driver.setup()

    logger.info("====================================")
    logger.info("      LABPULSE SYSTEM IS LIVE       ")
    logger.info("====================================")

    # 5. The Master Execution Loop
    try:
        while True:
            health_tracker.update()

            for sensor_id, driver in active_sensors.items():
                # Blindly ask the driver for data (The Phase 1 Contract in action!)
                data = driver.read()

                if data:
                    for metric_name, value in data.items():
                        # Auto-generate topics and push discovery
                        if metric_name not in STATE_TOPICS:
                            STATE_TOPICS[metric_name] = f"home/sensor/{metric_name}/state"
                            publish_discovery(mqtt_client, metric_name)

                        # Publish standard format to MQTT
                        mqtt_client.publish(STATE_TOPICS[metric_name], value)
                        
            # Wait 2 seconds before polling all hardware again
            time.sleep(2.0)

    except KeyboardInterrupt:
        logger.info("Shutdown signal received.")
    finally:
        # 6. Graceful Disconnect (Releases all USB and I2C ports)
        logger.info("Disconnecting all hardware...")
        for sensor_id, driver in active_sensors.items():
            driver.disconnect()
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        logger.info("LabPulse Master Hub Offline.")

if __name__ == '__main__':
    main()