import serial
import time
import json
import paho.mqtt.client as mqtt

SERIAL_PORT = '/dev/ttyACM0'  # Update this if needed
BAUD_RATE = 9600

MQTT_BROKER = 'localhost'
MQTT_PORT = 1883

# MQTT topics
DISCOVERY_TOPIC_FLOW = 'homeassistant/sensor/water_flow/config'
DISCOVERY_TOPIC_VOLUME = 'homeassistant/sensor/water_volume/config'
STATE_TOPIC_FLOW = 'homeassistant/sensor/water_flow/state'
STATE_TOPIC_VOLUME = 'homeassistant/sensor/water_volume/state'

client = mqtt.Client()
client.connect(MQTT_BROKER, MQTT_PORT, 60)
print("Connected to MQTT broker")

# Home Assistant discovery configs
client.publish(DISCOVERY_TOPIC_FLOW, json.dumps({
    "name": "Water Flow Rate",
    "state_topic": STATE_TOPIC_FLOW,
    "unit_of_measurement": "L/min",
    "device_class": "water",
    "unique_id": "water_flow_sensor_1"
}), retain=True)

client.publish(DISCOVERY_TOPIC_VOLUME, json.dumps({
    "name": "Total Water Volume",
    "state_topic": STATE_TOPIC_VOLUME,
    "unit_of_measurement": "L",
    "device_class": "volume",
    "unique_id": "water_volume_sensor_1"
}), retain=True)

# Read and parse serial data
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
time.sleep(2)  # wait for Arduino reset

while True:
    try:
        line = ser.readline().decode('utf-8').strip()
        if line.startswith("FlowRate:"):
            print(f"Raw: {line}")
            parts = line.split(",")
            flow = parts[0].split(":")[1]
            total = parts[1].split(":")[1]
            client.publish(STATE_TOPIC_FLOW, flow)
            client.publish(STATE_TOPIC_VOLUME, total)
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(5)
