import time
import json
import board
import adafruit_dht
import paho.mqtt.client as mqtt

# ----- Configuration -----
DHT_PIN = board.D4
dht_device = adafruit_dht.DHT11(DHT_PIN)

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
DISCOVERY_PREFIX = "homeassistant"
STATE_TOPIC = "home/sensor/dht11"
DEVICE_ID = "dht11_pi_sensor"

client = mqtt.Client()

def publish_discovery():
	temp_config = {
		"name": "Room Temperature",
		"state_topic": STATE_TOPIC,
		"unit_of_measurement": "C",
		"value_template": "{{ value_json.temperature }}",
		"unique_id": "room_temperature_dht11",
		"device_class": "temperature",
		"device": {
			"identifiers": [DEVICE_ID],
			"name": "DHT11 Sensor",
			"model": "DHT11",
			"manufacturer": "Adafruit"
		}
	}
	humidity_config = {
		"name": "Room Humidity",
		"state_topic": STATE_TOPIC,
		"unit_of_measurement": "%",
		"value_template": "{{ value_json.humidity }}",
		"unique_id": "room_humidity_dht11",
		"device_class": "humidity",
		"device": {
			"identifiers": [DEVICE_ID],
			"name": "DHT11 Sensor",
			"model": "DHT11",
			"manufacturer": "Adafruit"
		}
	}
	client.publish(f"{DISCOVERY_PREFIX}/sensor/{DEVICE_ID}/temperature/config", json.dumps(temp_config), retain=True)
	client.publish(f"{DISCOVERY_PREFIX}/sensor/{DEVICE_ID}/humidity/config", json.dumps(humidity_config), retain=True)
	print("MQTT discovery messages published")


def read_and_publish():
	try:
		temperature = dht_device.temperature
		humidity = dht_device.humidity

		if humidity is not None and temperature is not None:
			payload = {
				"temperature": round(temperature, 1),
				"humidity": round(humidity, 1)
			}
			client.publish(STATE_TOPIC, json.dumps(payload))
			print(f"Published state: {payload}")
		else:
			print("Sensor returned None")
	except RuntimeError as error:
		print(f"RuntimeError: {error}")
	except Exception as error:
		dht_device.exit()
		raise error



def main():
	client.connect(MQTT_BROKER, MQTT_PORT, 60)
	client.loop_start()

	publish_discovery()

	try:
		while True:
			read_and_publish()
			time.sleep(3)
	except KeyboardInterrupt:
		print("Exiting...")
	finally:
		client.loop_stop()
		client.disconnect()
		dht_device.exit()

if __name__ == "__main__":
	main()
