import serial
import time
import json
import paho.mqtt.client as mqtt
import threading
import subprocess
import queue
import os
from datetime import datetime

# --- CONFIGURATION ---
SERIAL_PORT = '/dev/ttyACM0' # Change to the port of your arduino!
BAUD_RATE = 9600
MQTT_BROKER = 'localhost'
MQTT_PORT = 1883

DISCOVERY_TOPIC = 'homeassistant/sensor/air_pressure/config'
STATE_TOPIC = 'homeassistant/sensor/air_pressure/state'

# For configurable threshold
CONFIG_FILE = '/home/monitorpi/Desktop/threshold_config.json'  # Set to your full config file path!
THRESHOLD_DISCOVERY_TOPIC = 'homeassistant/number/air_pressure_threshold/config'
THRESHOLD_STATE_TOPIC = 'air_pressure/threshold/state'
THRESHOLD_COMMAND_TOPIC = 'air_pressure/threshold/set'

def load_threshold_from_file(sensor_type="pressure"):
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                sensor_config = data.get(sensor_type, {})
                return float(sensor_config.get("threshold", DEFAULT_PRESSURE_THRESHOLD_BAR))
    except Exception as e:
        print(f"[DEBUG] Failed to load threshold for '{sensor_type}' from file: {e}")
    return DEFAULT_PRESSURE_THRESHOLD_BAR

def save_threshold_to_file(value, sensor_type="pressure"):
    try:
        config_data = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config_data = json.load(f)

        # Update just the threshold for the specific sensor
        if sensor_type not in config_data:
            config_data[sensor_type] = {}

        config_data[sensor_type]["threshold"] = value

        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=2)

        print(f"[DEBUG] Saved {sensor_type} threshold {value} to {CONFIG_FILE}")
    except Exception as e:
        print(f"[DEBUG] Failed to save threshold for '{sensor_type}': {e}")

def load_recipients(path='/home/monitorpi/Desktop/Phone_Numbers.json'):
    with open(path, 'r') as f:
        return json.load(f)['recipients']

SMS_PHONE_NUMBERS = load_recipients()
DEFAULT_PRESSURE_THRESHOLD_BAR = 0.0
MIN_READINGS_UNDER_THRESHOLD = 3

# --- GLOBALS ---
pressure_alert_active = False
sms_queue = queue.Queue()
low_pressure_count = 0
recovery_count = 0
current_threshold = load_threshold_from_file("pressure")


mqtt_client = mqtt.Client()


# --- SMS FUNCTIONS ---
def sms_sender_worker():
    while True:
        phone_number, message = sms_queue.get()
        try:
            send_sms(phone_number, message)
        except Exception as e:
            print(f"[DEBUG] Failed to send SMS to {phone_number}: {e}")
        finally:
            sms_queue.task_done()

def get_modem_index():
    try:
        result = subprocess.run(["mmcli", "-L"], capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            if "/Modem/" in line:
                # Extract index number from path like /org/freedesktop/ModemManager1/Modem/7
                parts = line.strip().split('/')
                return parts[-1].split()[0]  # '7'
    except subprocess.CalledProcessError as e:
        print(f"Failed to list modems: {e.stderr}")
    return None

def send_sms(phone_number: str, message: str):
    try:
        MODEM_INDEX = get_modem_index()
        if not MODEM_INDEX:
            print("No modem found.")
            return
        print(f"Creating SMS to {phone_number}")
        result = subprocess.run(
            ['mmcli', '-m', MODEM_INDEX, '--messaging-create-sms', f'text="{message}",number={phone_number}'],
            capture_output=True, text=True, timeout=10
        )

        sms_path = None
        for line in result.stdout.splitlines():
            if "Successfully created new SMS" in line:
                sms_path = line.split()[-1].strip()
                break

        if not sms_path:
            print("Failed to extract SMS path from mmcli output.")
            return

        print(f"Sending SMS via {sms_path}")
        subprocess.run(["mmcli", "-s", sms_path, "--send"], check=True)
        print(f"SMS sent to {phone_number}")

    except subprocess.CalledProcessError as e:
        print(f"Error sending SMS to {phone_number}:\n{e.stderr.strip()}")

def broadcast_sms(message: str):
    for number in SMS_PHONE_NUMBERS:
        sms_queue.put((number, message))


# --- PRESSURE DROP DETECTION ---
def get_timestamp():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")

def check_pressure_threshold(pressure_bar):
    global pressure_alert_active, low_pressure_count, recovery_count

    timestamp = get_timestamp()

    if not pressure_alert_active:
        if pressure_bar < current_threshold:
            low_pressure_count += 1
            recovery_count = 0  # reset recovery counter
            print(f"[DEBUG] Low pressure count: {low_pressure_count}")
        else:
            low_pressure_count = 0  # reset if pressure goes back up

        if low_pressure_count >= MIN_READINGS_UNDER_THRESHOLD:
            print(f"[{timestamp}] !! Pressure dropped below threshold ({current_threshold} bar) {MIN_READINGS_UNDER_THRESHOLD} times in a row !!")
            broadcast_sms(f"!! {timestamp}: Air pressure dropped below {current_threshold:.2f} bar for {MIN_READINGS_UNDER_THRESHOLD} consecutive readings. !!")
            pressure_alert_active = True
            low_pressure_count = 0  # reset after sending alert

    else:
        if pressure_bar >= current_threshold:
            recovery_count += 1
            low_pressure_count = 0  # reset low counter
            print(f"[DEBUG] Recovery count: {recovery_count}")
        else:
            recovery_count = 0  # reset if pressure dips again

        if recovery_count >= MIN_READINGS_UNDER_THRESHOLD:
            print(f"[{timestamp}] Pressure has recovered to {pressure_bar:.2f} bar confirmed.")
            broadcast_sms(f"-- {timestamp}: Air pressure has recovered to {pressure_bar:.2f} bar (threshold: {current_threshold:.2f} bar). --")
            pressure_alert_active = False
            recovery_count = 0  # reset after restore



# --- MQTT CALLBACKS ---
def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT broker")
    client.subscribe(THRESHOLD_COMMAND_TOPIC)

def on_message(client, userdata, msg):
    global current_threshold
    try:
        new_val = float(msg.payload.decode())
        current_threshold = new_val
        print(f"[DEBUG] Updated SMS pressure threshold to {current_threshold} bar")
        save_threshold_to_file(current_threshold, "pressure")
        publish_threshold_state()
    except ValueError:
        print(f"[DEBUG] Invalid threshold received: {msg.payload.decode()}")



def publish_threshold_state():
    mqtt_client.publish(THRESHOLD_STATE_TOPIC, str(current_threshold), retain=True)


def publish_threshold_discovery():
    discovery_payload = {
        "name": "Air Pressure SMS Threshold",
        "state_topic": THRESHOLD_STATE_TOPIC,
        "command_topic": THRESHOLD_COMMAND_TOPIC,
        "min": 0,
        "max": 10,
        "step": 0.1,
        "unit_of_measurement": "bar",
        "unique_id": "air_pressure_sms_threshold",
        "device": {
            "identifiers": ["air_pressure_device"],
            "name": "Air Pressure Monitor",
            "model": "Pressure v1",
            "manufacturer": "YourLab"
        }
    }
    mqtt_client.publish(THRESHOLD_DISCOVERY_TOPIC, json.dumps(discovery_payload), retain=True)
    publish_threshold_state()


# --- MAIN LOOP ---
def main():
    global mqtt_client

    threading.Thread(target=sms_sender_worker, daemon=True).start()

    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)

    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()

    # Pressure sensor discovery
    discovery_payload = {
        "name": "Air Pressure",
        "state_topic": STATE_TOPIC,
        "unit_of_measurement": "bar",
        "device_class": "pressure",
        "unique_id": "air_pressure_sensor_1",
        "device": {
            "identifiers": ["air_pressure_device"],
            "name": "Air Pressure Monitor",
            "model": "Pressure v1",
            "manufacturer": "YourLab"
        }
    }
    mqtt_client.publish(DISCOVERY_TOPIC, json.dumps(discovery_payload), retain=True)

    # Threshold config discovery
    publish_threshold_discovery()

    # Loop
    while True:
        line = ser.readline().decode('utf-8').strip()
        if line:
            try:
                pressure_mpa = float(line)
                pressure_bar = pressure_mpa * 10
                print(f"Pressure: {pressure_bar:.2f} bar")

                mqtt_client.publish(STATE_TOPIC, pressure_bar)
                check_pressure_threshold(pressure_bar)
            except ValueError:
                print(f"[DEBUG] Invalid reading: {line}")
        time.sleep(1)


if __name__ == '__main__':
    main()

