import serial
import time
import json
import paho.mqtt.client as mqtt

# Serial port where Arduino is connected
SERIAL_PORT = '/dev/ttyACM0'  # Change if your device is different
BAUD_RATE = 9600

# MQTT broker settings
MQTT_BROKER = 'localhost'
MQTT_PORT = 1883

# MQTT topics for Home Assistant discovery and state updates
DISCOVERY_TOPIC = 'homeassistant/sensor/air_pressure/config'
STATE_TOPIC = 'homeassistant/sensor/air_pressure/state'

def main():
    # Setup serial connection to Arduino
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # wait for Arduino to reset

    # Setup MQTT client and connect
    client = mqtt.Client()
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    print("Connected to MQTT broker")

    # Home Assistant MQTT discovery payload
    discovery_payload = {
        "name": "Air Pressure",
        "state_topic": STATE_TOPIC,
        "unit_of_measurement": "MPa",
        "device_class": "pressure",
        "unique_id": "air_pressure_sensor_1"
    }

    # Publish discovery config once with retain=True so HA remembers sensor
    client.publish(DISCOVERY_TOPIC, json.dumps(discovery_payload), retain=True)

    # Read serial lines and publish pressure data
    while True:
        line = ser.readline().decode('utf-8').strip()
        if line:
            print(f"Pressure: {line} MPa")
            client.publish(STATE_TOPIC, line)
        time.sleep(1)

if __name__ == '__main__':
    main()

