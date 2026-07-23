import serial
import time
import json
import paho.mqtt.client as mqtt
import threading
import subprocess
import queue
import os
from datetime import datetime

# === CONFIGURATION ===
SENSOR_PREFIX = 'pump_'  # Change to 'turbo_' or anything else
SERIAL_PORT = '/dev/ttyACM0' # Change to the actual port of the specific Arduino
BAUD_RATE = 9600
MQTT_BROKER = 'localhost'
MQTT_PORT = 1883

THRESHOLD_CONFIG_FILE = '/home/monitorpi/Desktop/threshold_config.json'
PHONE_NUMBERS_FILE = '/home/monitorpi/Desktop/Phone_Numbers.json'

FLOW_SENSORS = [f'{SENSOR_PREFIX}flow1', f'{SENSOR_PREFIX}flow2']
TEMP_SENSORS = [f'{SENSOR_PREFIX}temp{i}' for i in range(4)]
MIN_READINGS_UNDER_THRESHOLD = 3

# === GLOBALS ===
sms_queue = queue.Queue()
mqtt_client = mqtt.Client()
alert_state = {sensor: False for sensor in FLOW_SENSORS + TEMP_SENSORS}
low_count = {sensor: 0 for sensor in FLOW_SENSORS + TEMP_SENSORS}
recovery_count = {sensor: 0 for sensor in FLOW_SENSORS + TEMP_SENSORS}
thresholds = {}

# === MQTT TOPICS ===
STATE_TOPICS = {
    **{f"{SENSOR_PREFIX}temp{i}": f"homeassistant/sensor/{SENSOR_PREFIX}temp{i}/state" for i in range(4)},
    f"{SENSOR_PREFIX}flow1": f"homeassistant/sensor/{SENSOR_PREFIX}flow1/state",
    f"{SENSOR_PREFIX}flow2": f"homeassistant/sensor/{SENSOR_PREFIX}flow2/state"
}

DISCOVERY_TOPICS = {
    f"{SENSOR_PREFIX}temp{i}": f"homeassistant/sensor/{SENSOR_PREFIX}temp{i}/config" for i in range(4)
}
DISCOVERY_TOPICS.update({
    f"{SENSOR_PREFIX}flow1": f"homeassistant/sensor/{SENSOR_PREFIX}flow1/config",
    f"{SENSOR_PREFIX}flow2": f"homeassistant/sensor/{SENSOR_PREFIX}flow2/config",
})

# === UTILITY FUNCTIONS ===
def get_timestamp():
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")

def load_thresholds():
    if os.path.exists(THRESHOLD_CONFIG_FILE):
        with open(THRESHOLD_CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_thresholds():
    with open(THRESHOLD_CONFIG_FILE, 'w') as f:
        json.dump(thresholds, f, indent=2)

def load_recipients():
    with open(PHONE_NUMBERS_FILE, 'r') as f:
        return json.load(f).get('recipients', [])

SMS_PHONE_NUMBERS = load_recipients()
thresholds = load_thresholds()

def get_sensor_threshold(sensor):
    return thresholds.get(sensor, {})

def set_sensor_threshold(sensor, key, value):
    if sensor not in thresholds:
        thresholds[sensor] = {}
    thresholds[sensor][key] = value
    save_thresholds()

# === SMS SYSTEM ===
def sms_sender_worker():
    while True:
        phone_number, message = sms_queue.get()
        try:
            send_sms(phone_number, message)
        except Exception as e:
            print(f"[SMS ERROR] {e}")
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

def broadcast_sms(message):
    for number in SMS_PHONE_NUMBERS:
        sms_queue.put((number, message))

# === THRESHOLD DISCOVERY ===
def publish_threshold_discovery():
    for flow in ['flow1', 'flow2']:
        full_id = SENSOR_PREFIX + flow
        discovery = {
            "name": f"{full_id.upper()} Alert Threshold",
            "state_topic": f"{full_id}/threshold/state",
            "command_topic": f"{full_id}/threshold/set",
            "min": 0,
            "max": 100,
            "step": 0.5,
            "unit_of_measurement": "L/min",
            "unique_id": f"{full_id}_threshold_slider"
        }
        mqtt_client.publish(f"homeassistant/number/{full_id}_threshold/config", json.dumps(discovery), retain=True)
        current = get_sensor_threshold(full_id).get("min", 0)
        mqtt_client.publish(f"{full_id}/threshold/state", str(current), retain=True)

    for i in range(4):
        for bound in ['min', 'max']:
            temp = f"{SENSOR_PREFIX}temp{i}"
            topic_base = f"{temp}_{bound}"
            discovery = {
                "name": f"{temp.upper()} {bound.capitalize()} Temp",
                "state_topic": f"{topic_base}/state",
                "command_topic": f"{topic_base}/set",
                "min": -50,
                "max": 100,
                "step": 0.5,
                "unit_of_measurement": "C",
                "unique_id": f"{topic_base}_threshold"
            }
            mqtt_client.publish(f"homeassistant/number/{topic_base}/config", json.dumps(discovery), retain=True)
            val = get_sensor_threshold(temp).get(bound, 0)
            mqtt_client.publish(f"{topic_base}/state", str(val), retain=True)

# === MQTT CALLBACKS ===
def on_connect(client, userdata, flags, rc):
    print("Connected to MQTT broker")
    for flow in ['flow1', 'flow2']:
        mqtt_client.subscribe(f"{SENSOR_PREFIX}{flow}/threshold/set")
    for i in range(4):
        for bound in ['min', 'max']:
            mqtt_client.subscribe(f"{SENSOR_PREFIX}temp{i}_{bound}/set")

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode().strip()
    try:
        val = float(payload)
    except ValueError:
        print(f"[MQTT] Invalid payload: {payload}")
        return

    for flow in ['flow1', 'flow2']:
        full_id = SENSOR_PREFIX + flow
        if topic == f"{full_id}/threshold/set":
            set_sensor_threshold(full_id, "min", val)
            mqtt_client.publish(f"{full_id}/threshold/state", str(val), retain=True)
            print(f"[MQTT] Updated {flow} threshold to {val}")

    for i in range(4):
        for bound in ['min', 'max']:
            temp_id = f"{SENSOR_PREFIX}temp{i}"
            if topic == f"{temp_id}_{bound}/set":
                set_sensor_threshold(temp_id, bound, val)
                mqtt_client.publish(f"{temp_id}_{bound}/state", str(val), retain=True)
                print(f"[MQTT] Updated {temp_id} {bound} to {val}")

# === SENSOR EVALUATION ===
def evaluate_threshold(sensor, value):
    t = get_sensor_threshold(sensor)
    timestamp = get_timestamp()

    breached = False
    if sensor in FLOW_SENSORS:
        breached = value < t.get("min", 0)
    elif sensor in TEMP_SENSORS:
        breached = value < t.get("min", -999) or value > t.get("max", 999)

    if not alert_state[sensor]:
        if breached:
            low_count[sensor] += 1
            recovery_count[sensor] = 0
            if low_count[sensor] >= MIN_READINGS_UNDER_THRESHOLD:
                broadcast_sms(f"!! {timestamp}: {sensor.upper()} reading {value:.2f} triggered alert.")
                alert_state[sensor] = True
                low_count[sensor] = 0
        else:
            low_count[sensor] = 0
    else:
        if not breached:
            recovery_count[sensor] += 1
            low_count[sensor] = 0
            if recovery_count[sensor] >= MIN_READINGS_UNDER_THRESHOLD:
                broadcast_sms(f"-- {timestamp}: {sensor.upper()} reading {value:.2f} has recovered.")
                alert_state[sensor] = False
                recovery_count[sensor] = 0
        else:
            recovery_count[sensor] = 0

# === MAIN FUNCTION ===
def main():
    threading.Thread(target=sms_sender_worker, daemon=True).start()

    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()

    for i in range(4):
        sensor_id = f"{SENSOR_PREFIX}temp{i}"
        mqtt_client.publish(DISCOVERY_TOPICS[sensor_id], json.dumps({
            "name": f"{SENSOR_PREFIX.capitalize()}Temperature Sensor {i}",
            "state_topic": STATE_TOPICS[sensor_id],
            "unit_of_measurement": "C",
            "device_class": "temperature",
            "unique_id": sensor_id
        }), retain=True)

    for flow in ['flow1', 'flow2']:
        sensor_id = SENSOR_PREFIX + flow
        mqtt_client.publish(DISCOVERY_TOPICS[sensor_id], json.dumps({
            "name": f"{SENSOR_PREFIX.capitalize()}Water Flow Rate {flow[-1]}",
            "state_topic": STATE_TOPICS[sensor_id],
            "unit_of_measurement": "L/min",
            "unique_id": sensor_id
        }), retain=True)

    publish_threshold_discovery()

    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)

    while True:
        try:
            line = ser.readline().decode('utf-8').strip()
            if not line:
                continue

            print(f"Raw: {line}")

            if line.startswith("Temp0:"):
                for part in line.split("  "):
                    if ":" in part:
                        label, value = part.split(":")
                        key = SENSOR_PREFIX + label.strip().lower()
                        val = float(value.replace("C", "").strip())
                        mqtt_client.publish(STATE_TOPICS[key], val)
                        evaluate_threshold(key, val)

            elif line.startswith("Flow1:"):
                for section in line.split("|"):
                    for item in section.split(","):
                        if ":" in item:
                            label, value = item.strip().split(":")
                            key = SENSOR_PREFIX + label.strip().lower()
                            if key in FLOW_SENSORS:
                                val = float(value.replace("L/min", "").strip())
                                mqtt_client.publish(STATE_TOPICS[key], val)
                                evaluate_threshold(key, val)

        except Exception as e:
            print(f"[ERROR] {e}")

        time.sleep(1)

if __name__ == '__main__':
    main()
