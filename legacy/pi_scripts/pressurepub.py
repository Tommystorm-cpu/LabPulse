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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("PressureMonitor")

# === DYNAMIC CONFIGURATION ===
sys_config = load_config()
cfg = sys_config.pressure_monitor
mqtt_cfg = sys_config.mqtt

SENSOR_ID = "pneumatic_air_pressure"
SERIAL_PORT = cfg.serial_port
BAUD_RATE = cfg.baud_rate
MQTT_BROKER = mqtt_cfg.broker
MQTT_PORT = mqtt_cfg.port
MIN_READINGS = cfg.min_readings_under_threshold

# MQTT Topics
STATE_TOPIC = f"home/sensor/{SENSOR_ID}/state"
THRESHOLD_SET_TOPIC = f"home/sensor/{SENSOR_ID}/set_threshold"
THRESHOLD_STATE_TOPIC = f"home/sensor/{SENSOR_ID}/threshold_state"

alert_state = False
low_count = 0
recovery_count = 0

# Initialize SMS Engine
sms_manager = LabPulseSMS(sys_config.sms.recipients)
mqtt_client = mqtt.Client(client_id="PressureMonitor")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT Broker.")
        # Listen for the slider moving in Home Assistant
        client.subscribe(THRESHOLD_SET_TOPIC)
    else:
        logger.error(f"Failed to connect to MQTT. Code: {rc}")

def on_message(client, userdata, msg):
    payload = msg.payload.decode('utf-8')
    try:
        new_val = float(payload)
        thresholds = load_all_thresholds()
        if SENSOR_ID not in thresholds:
            thresholds[SENSOR_ID] = {}
        thresholds[SENSOR_ID]["min"] = new_val
        save_all_thresholds(thresholds)
        logger.info(f"Updated threshold for {SENSOR_ID} -> {new_val}")
        
        # Echo the change back so the HA slider visually updates
        mqtt_client.publish(THRESHOLD_STATE_TOPIC, new_val, retain=True)
    except ValueError:
        logger.error(f"Invalid threshold value: {payload}")

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

def publish_discovery():
    # 1. Generate the actual Sensor Reading
    sensor_payload = {
        "name": "Air Pressure",
        "state_topic": STATE_TOPIC,
        "unit_of_measurement": "bar",
        "unique_id": f"{SENSOR_ID}_reading",
        "device": {
            "identifiers": ["pressure_arduino"],
            "name": "Air Pressure Sensor Hub"
        }
    }
    mqtt_client.publish(f"homeassistant/sensor/{SENSOR_ID}/config", json.dumps(sensor_payload), retain=True)

    # 2. Generate the strictly-linked Threshold Slider
    slider_payload = {
        "name": "Air Pressure Alert Threshold",
        "command_topic": THRESHOLD_SET_TOPIC,
        "state_topic": THRESHOLD_STATE_TOPIC,
        "min": 0.0,
        "max": 10.0,
        "step": 0.1,
        "unit_of_measurement": "bar",
        "unique_id": f"{SENSOR_ID}_threshold_slider",
        "device": {
            "identifiers": ["pressure_arduino"],
            "name": "Air Pressure Sensor Hub"
        }
    }
    mqtt_client.publish(f"homeassistant/number/{SENSOR_ID}_threshold/config", json.dumps(slider_payload), retain=True)
    
    # Sync the slider to the saved JSON config on boot
    current_threshold = load_all_thresholds().get(SENSOR_ID, {}).get("min", cfg.default_threshold_bar)
    mqtt_client.publish(THRESHOLD_STATE_TOPIC, current_threshold, retain=True)

def evaluate_pressure(value):
    """Evaluates pneumatic stability and fires UX-optimized SMS."""
    global alert_state, low_count, recovery_count
    
    thresholds = load_all_thresholds()
    min_limit = thresholds.get(SENSOR_ID, {}).get("min", cfg.default_threshold_bar)

    if value < min_limit:
        recovery_count = 0
        low_count += 1
        if low_count >= MIN_READINGS and not alert_state:
            alert_state = True
            timestamp = datetime.now().strftime("%H:%M:%S")
            
            msg = (
                f"🚨 [PNEUMATICS] ALERT\n"
                f"Time: {timestamp}\n"
                f"Sensor: Main Air Pressure\n"
                f"Reading: {value:.2f} bar (Limit: {min_limit:.2f} bar)\n"
                f"Action: Check lab air compressor and main supply valves."
            )
            logger.warning(msg.replace('\n', ' | '))
            sms_manager.broadcast(msg)
            
    else:
        low_count = 0
        if alert_state:
            recovery_count += 1
            if recovery_count >= MIN_READINGS:
                alert_state = False
                timestamp = datetime.now().strftime("%H:%M:%S")
                
                msg = (
                    f"✅ [PNEUMATICS] RECOVERY\n"
                    f"Time: {timestamp}\n"
                    f"Sensor: Main Air Pressure\n"
                    f"Reading: {value:.2f} bar (Restored above {min_limit:.2f} bar)\n"
                    f"Status: Pressure stabilized."
                )
                logger.info(msg.replace('\n', ' | '))
                sms_manager.broadcast(msg)

def main():
    logger.info("Initializing Pressure Monitor Service...")
    health_tracker = ServiceHealthTracker(mqtt_client, "pressure_monitor")
    
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        publish_discovery()
    except Exception as e:
        logger.error(f"MQTT Boot Error: {e}")
        sys.exit(1)

    while True:
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
            logger.info("Hardware connected.")
            
            while True:
                line = ser.readline().decode('utf-8').strip()
                health_tracker.update()
                
                if not line:
                    continue
                
                try:
                    # Math Fix: Scale raw Arduino output by 10x to match physical reality
                    val = round(float(line) * 10.0, 2)
                    mqtt_client.publish(STATE_TOPIC, val)
                    evaluate_pressure(val)
                except ValueError:
                    continue
                    
        except serial.SerialException:
            logger.error("Hardware disconnected. Retrying in 5s...")
            time.sleep(5)

if __name__ == '__main__':
    main()
