import sys
import time
import json
import logging
import smbus2
import paho.mqtt.client as mqtt
from datetime import datetime
from labpulse_common.config import load_config
from labpulse_common.sms import LabPulseSMS
from labpulse_common.mqtt_health import ServiceHealthTracker

# === SETUP LOGGING ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger("PowerMonitor")

# === DYNAMIC CONFIGURATION ===
sys_config = load_config()
cfg = sys_config.ups_monitor
mqtt_cfg = sys_config.mqtt

MQTT_BROKER = mqtt_cfg.broker
MQTT_PORT = mqtt_cfg.port
I2C_ADDR = cfg.i2c_addr
BASE_TOPIC = cfg.mqtt_base_topic
VOLTAGE_MIN = cfg.voltage_min
VOLTAGE_MAX = cfg.voltage_max

# Initialize SMS Engine
sms_manager = LabPulseSMS(sys_config.sms.recipients)

# I2C Bus setup
I2C_BUS = 1
try:
    bus = smbus2.SMBus(I2C_BUS)
except Exception as e:
    logger.error(f"Failed to access I2C Bus: {e}")
    sys.exit(1)

mqtt_client = mqtt.Client(client_id=cfg.mqtt_client_id)

def read_voltage():
    """Reads raw voltage from INA219 via I2C."""
    try:
        bus.write_byte(I2C_ADDR, 0x02)
        time.sleep(0.05)
        data = bus.read_i2c_block_data(I2C_ADDR, 0x02, 2)
        raw_val = (data[0] << 8) | data[1]
        raw_val = raw_val >> 3
        voltage = raw_val * 0.004
        return round(voltage, 2)
    except Exception as e:
        logger.error(f"I2C Voltage Read Error: {e}")
        return None

def read_current():
    """Reads raw shunt voltage to calculate current (mA) from INA219."""
    try:
        bus.write_byte(I2C_ADDR, 0x01)
        time.sleep(0.05)
        data = bus.read_i2c_block_data(I2C_ADDR, 0x01, 2)
        raw_val = (data[0] << 8) | data[1]
        if raw_val > 32767:
            raw_val -= 65536
        # Assuming standard 0.1 ohm shunt resistor
        current_ma = raw_val * 0.1  
        return round(current_ma, 1)
    except Exception as e:
        logger.error(f"I2C Current Read Error: {e}")
        return 0.0

def publish_discovery():
    sensors = [
        {"id": "voltage", "name": "UPS Voltage", "unit": "V"},
        {"id": "battery_level", "name": "UPS Battery Level", "unit": "%"},
        {"id": "power_status", "name": "Power Grid Status", "unit": ""},
        {"id": "current", "name": "UPS Battery Current", "unit": "mA"},
        {"id": "charging_status", "name": "UPS Charging Status", "unit": ""}
    ]
    
    for s in sensors:
        topic = f"homeassistant/sensor/ups_{s['id']}/config"
        payload = {
            "name": s['name'],
            "state_topic": f"{BASE_TOPIC}/{s['id']}",
            "unit_of_measurement": s['unit'],
            "unique_id": f"ups_{s['id']}",
            "device": {
                "identifiers": ["pi_ups_monitor"],
                "name": "Raspberry Pi UPS"
            }
        }
        mqtt_client.publish(topic, json.dumps(payload), retain=True)

def main():
    logger.info("Initializing Power Monitor Service...")
    health_tracker = ServiceHealthTracker(mqtt_client, "power_monitor")
    
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        publish_discovery()
    except Exception as e:
        logger.error(f"MQTT Boot Error: {e}")
        sys.exit(1)

    tracking_outage = False
    outage_start_time = None

    while True:
        health_tracker.update()
        
        voltage = read_voltage()
        current = read_current()
        
        if voltage is not None:
            # Calculate rough percentage
            percent = ((voltage - VOLTAGE_MIN) / (VOLTAGE_MAX - VOLTAGE_MIN)) * 100
            percent = max(0, min(100, round(percent, 1)))
            
            # Determine Charging Status based on current flow direction
            if current > 50.0:
                charge_status = "charging"
            elif current < -50.0:
                charge_status = "discharging"
            else:
                charge_status = "idle"
            
            # Publish all stats
            mqtt_client.publish(f"{BASE_TOPIC}/voltage", voltage)
            mqtt_client.publish(f"{BASE_TOPIC}/battery_level", percent)
            mqtt_client.publish(f"{BASE_TOPIC}/current", current)
            mqtt_client.publish(f"{BASE_TOPIC}/charging_status", charge_status)

            # Evaluate Power Status (Alerts)
            if voltage < (VOLTAGE_MAX - 0.2):
                mqtt_client.publish(f"{BASE_TOPIC}/power_status", "BATTERY")
                
                if not tracking_outage:
                    tracking_outage = True
                    outage_start_time = time.time()
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    
                    msg = (
                        f"⚡ [POWER SYSTEM] ALERT\n"
                        f"Time: {timestamp}\n"
                        f"Sensor: Main Grid\n"
                        f"Reading: Voltage dropped to {voltage}V\n"
                        f"Action: Check lab circuit breakers. System running on UPS battery."
                    )
                    logger.warning(msg.replace('\n', ' | '))
                    sms_manager.broadcast(msg)
            else:
                mqtt_client.publish(f"{BASE_TOPIC}/power_status", "MAINS")
                
                if tracking_outage:
                    outage_duration = round(time.time() - outage_start_time, 2)
                    tracking_outage = False
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    
                    msg = (
                        f"✅ [POWER SYSTEM] RECOVERY\n"
                        f"Time: {timestamp}\n"
                        f"Sensor: Main Grid\n"
                        f"Reading: Power restored (Outage lasted {outage_duration}s)\n"
                        f"Status: Operating normally on mains power."
                    )
                    logger.info(msg.replace('\n', ' | '))
                    sms_manager.broadcast(msg)

        time.sleep(2)  # Read every 2 seconds

if __name__ == '__main__':
    main()
