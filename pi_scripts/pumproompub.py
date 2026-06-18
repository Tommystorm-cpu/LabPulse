import sys
import time
import json
import logging
import serial
import paho.mqtt.client as mqtt
from datetime import datetime
from labpulse_common.config import load_config, load_all_thresholds, save_all_thresholds
from labpulse_common.sms import LabPulseSMS
from labpulse_common.mqtt_health import ServiceHealthTracker

# === SETUP LOGGING ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PumpRoom")

# === DYNAMIC CONFIGURATION ===
sys_config = load_config()
cfg = sys_config.pump_room
mqtt_cfg = sys_config.mqtt

SENSOR_PREFIX = 'pump_'
SERIAL_PORT = cfg.serial_port
BAUD_RATE = cfg.baud_rate
MQTT_BROKER = mqtt_cfg.broker
MQTT_PORT = mqtt_cfg.port
MIN_READINGS_UNDER_THRESHOLD = cfg.min_readings_under_threshold

# Tracking states
alert_state = {}
low_count = {}
recovery_count = {}
STATE_TOPICS = {}
DISCOVERY_TOPICS = {}

# Initialize SMS Engine
sms_manager = LabPulseSMS(sys_config.sms.recipients)
mqtt_client = mqtt.Client(client_id="PumpRoomMonitor")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT Broker.")
        client.subscribe("home/sensor/+/set_threshold")
    else:
        logger.error(f"Failed to connect to MQTT. Code: {rc}")

def on_message(client, userdata, msg):
    """Intercepts Home Assistant slider changes and saves them to thresholds.json"""
    topic = msg.topic
    payload = msg.payload.decode('utf-8')
    sensor_id = topic.split('/')[2]
    
    try:
        new_val = float(payload)
        thresholds = load_all_thresholds()
        if sensor_id not in thresholds:
            thresholds[sensor_id] = {}
        thresholds[sensor_id]["min"] = new_val
        save_all_thresholds(thresholds)
        logger.info(f"Updated threshold for {sensor_id} -> {new_val}")
    except ValueError:
        logger.error(f"Invalid threshold value received: {payload}")

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def get_sensor_threshold(sensor_id):
    thresholds = load_all_thresholds()
    return thresholds.get(sensor_id, {"min": 0.0})

def publish_discovery(sensor_id):
    """Pushes Home Assistant auto-discovery configs."""
    unit = ""
    if "temp" in sensor_id:
        unit = "C"
    elif "hum" in sensor_id:
        unit = "%"
    elif "press" in sensor_id:
        unit = "bar"
    elif "flow" in sensor_id:
        unit = "L/min"

    discovery_payload = {
        "name": sensor_id.replace("_", " ").title(),
        "state_topic": STATE_TOPICS[sensor_id],
        "unit_of_measurement": unit,
        "unique_id": sensor_id,
        "device": {
            "identifiers": ["pump_room_arduino"],
            "name": "Pump Room Sensor Hub"
        }
    }
    mqtt_client.publish(DISCOVERY_TOPICS[sensor_id], json.dumps(discovery_payload), retain=True)

def evaluate_threshold(sensor_id, value):
    """Evaluates if the current reading breaches limits and fires UX-optimized SMS."""
    threshold = get_sensor_threshold(sensor_id)
    min_limit = threshold.get("min", 0.0)

    if sensor_id not in alert_state:
        alert_state[sensor_id] = False
        low_count[sensor_id] = 0
        recovery_count[sensor_id] = 0

    if value < min_limit:
        recovery_count[sensor_id] = 0
        low_count[sensor_id] += 1
        if low_count[sensor_id] >= MIN_READINGS_UNDER_THRESHOLD and not alert_state[sensor_id]:
            alert_state[sensor_id] = True
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            # Format multi-line for clean mobile UX
            msg = (
                f"🚨 [PUMP ROOM] ALERT\n"
                f"Time: {timestamp}\n"
                f"Sensor: {sensor_id.replace('_', ' ').upper()}\n"
                f"Reading: {value} (Limit: {min_limit})\n"
                f"Action: Inspect physical water lines and chiller."
            )
            # Flatten the string for the terminal log, but send the multi-line SMS
            logger.warning(msg.replace('\n', ' | '))
            sms_manager.broadcast(msg)
            
    else:
        low_count[sensor_id] = 0
        if alert_state[sensor_id]:
            recovery_count[sensor_id] += 1
            if recovery_count[sensor_id] >= MIN_READINGS_UNDER_THRESHOLD:
                alert_state[sensor_id] = False
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                msg = (
                    f"✅ [PUMP ROOM] RECOVERY\n"
                    f"Time: {timestamp}\n"
                    f"Sensor: {sensor_id.replace('_', ' ').upper()}\n"
                    f"Reading: {value} (Restored above {min_limit})\n"
                    f"Status: System normalized."
                )
                logger.info(msg.replace('\n', ' | '))
                sms_manager.broadcast(msg)

def main():
    logger.info("Initializing Pump Room Service...")
    
    # Initialize the health watchdog
    health_tracker = ServiceHealthTracker(mqtt_client, "pump_room_monitor")
    
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        logger.error(f"MQTT Boot Error: {e}")
        sys.exit(1)

    while True:
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
            logger.info("Hardware connected.")
            
            while True:
                line = ser.readline().decode('utf-8').strip()
                
                # Tell Home Assistant the loop is running and hardware is active
                health_tracker.update()
                
                if not line:
                    continue

                # Example parsers
                if line.startswith("Temp0:"):
                    for part in line.split("  "):
                        if ":" in part:
                            label, val_str = part.split(":")
                            key = SENSOR_PREFIX + label.strip().lower()
                            try:
                                val = float(val_str.replace("C", "").strip())
                            except ValueError:
                                continue
                            
                            if key not in STATE_TOPICS:
                                STATE_TOPICS[key] = f"home/sensor/{key}/state"
                                DISCOVERY_TOPICS[key] = f"homeassistant/sensor/{key}/config"
                                publish_discovery(key)
                                
                            mqtt_client.publish(STATE_TOPICS[key], val)
                            evaluate_threshold(key, val)
                            
        except serial.SerialException:
            logger.error("Hardware disconnected. Retrying in 5s...")
            time.sleep(5)

if __name__ == '__main__':
    main()
