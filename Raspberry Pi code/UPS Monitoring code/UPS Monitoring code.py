import smbus2
import time
import json
from paho.mqtt.client import Client

# I2C and INA219 constants
I2C_ADDR = 0x42
REG_CONFIG = 0x00
REG_SHUNT_VOLTAGE = 0x01
REG_BUS_VOLTAGE = 0x02
REG_POWER = 0x03
REG_CURRENT = 0x04
REG_CALIBRATION = 0x05

# MQTT details
MQTT_BROKER = 'localhost'
MQTT_PORT = 1883
MQTT_CLIENT_ID = 'PowerMonitor'
MQTT_BASE_TOPIC = 'home/power/ups'

# Battery voltage range for percentage calculation
VOLTAGE_MIN = 6.0  # Battery voltage at 0%
VOLTAGE_MAX = 8.4  # Battery voltage at 100%

bus = smbus2.SMBus(1)

def twos_complement(val, bits):
  if val & (1 << (bits - 1)):
    val -= 1 << bits
  return val

def read_word(reg):
  result = bus.read_word_data(I2C_ADDR, reg)
  return ((result & 0xFF) << 8) | (result >> 8)

def calibrate_ina219():
  calibration = 4096
  bus.write_word_data(I2C_ADDR, REG_CALIBRATION, ((calibration & 0xFF) << 8) | (calibration >> 8))
  config = 0x399F
  bus.write_word_data(I2C_ADDR, REG_CONFIG, ((config & 0xFF) << 8) | (config >> 8))

def read_voltage_current():
  raw_bus_voltage = read_word(REG_BUS_VOLTAGE)
  bus_voltage = ((raw_bus_voltage >> 3) * 4) / 1000.0 # Volts
  raw_current = read_word(REG_CURRENT)
  current = twos_complement(raw_current, 16)
  current_mA = current * 0.1
  return bus_voltage, current_mA

def calculate_battery_percentage(voltage):
  # Clamp voltage to min/max range
  voltage = max(min(voltage, VOLTAGE_MAX), VOLTAGE_MIN)
  percent = (voltage - VOLTAGE_MIN) / (VOLTAGE_MAX - VOLTAGE_MIN) * 100
  return round(percent)

def determine_charging_status(current_mA):
  if current_mA > 10:
    return "Charging..."
  elif current_mA < -45:
    return "Discharging..."
  else:
    return "idle"

def on_connect(client, userdata, flags, reasonCode, properties):
  print(f"Connected with result code {reasonCode}")

def on_disconnect(client, userdata, reasonCode, properties):
  print(f"Disconnected: {reasonCode}")

def on_publish(client, userdata, mid):
  print(f"Message {mid} published.")

def publish_discovery(client):
  base_device = {
    "identifiers": ["ups_hardware_1"],
    "name": "UPS Battery Monitor",
    "manufacturer": "Waveshare",
    "model": "UPS HAT INA219",
  }

  sensors = [
    {
      "name": "UPS Battery Voltage",
      "state_topic": f"{MQTT_BASE_TOPIC}/voltage",
      "unit_of_measurement": "V",
      "device_class": "voltage",
      "unique_id": "ups_voltage_sensor",
      "device": base_device,
    },
    {
      "name": "UPS Battery Current",
      "state_topic": f"{MQTT_BASE_TOPIC}/current",
      "unit_of_measurement": "mA",
      "device_class": "current",
      "unique_id": "ups_current_sensor",
      "device": base_device,
    },
    {
      "name": "UPS Battery Percentage",
      "state_topic": f"{MQTT_BASE_TOPIC}/percentage",
      "unit_of_measurement": "%",
      "device_class": "battery",
      "unique_id": "ups_percentage_sensor",
      "device": base_device,
    },
    {
      "name": "UPS Battery Charging Status",
      "state_topic": f"{MQTT_BASE_TOPIC}/status",
      "unique_id": "ups_status_sensor",
      "device": base_device,
      "icon": "mdi:battery-charging", # optional icon for HA
      "payload_on": "charging",
      "payload_off": "discharging",
      "payload_available": "idle",
    },
  ]

  for sensor in sensors:
    topic = f"homeassistant/sensor/{sensor['unique_id']}/config"
    client.publish(topic, json.dumps(sensor), retain=True)

def main():
  calibrate_ina219()
  client = Client(client_id=MQTT_CLIENT_ID)
  client.on_connect = on_connect
  client.on_disconnect = on_disconnect
  client.on_publish = on_publish
  client.connect(MQTT_BROKER, MQTT_PORT)
  client.loop_start()

  publish_discovery(client)

  print("Monitoring UPS HAT battery status. Press Ctrl+C to exit.")
  try:
    while True:
      bus_voltage, current_mA = read_voltage_current()
      battery_percent = calculate_battery_percentage(bus_voltage)
      status = determine_charging_status(current_mA)

      print(f"Battery Voltage: {bus_voltage:.2f} V")
      print(f"Current: {current_mA:.1f} mA")
      print(f"Status: {status}")
      print(f"Battery Percentage: {battery_percent}%")

      client.publish(f"{MQTT_BASE_TOPIC}/voltage", f"{bus_voltage:.2f}", retain=True)
      client.publish(f"{MQTT_BASE_TOPIC}/current", f"{current_mA:.1f}", retain=True)
      client.publish(f"{MQTT_BASE_TOPIC}/percentage", str(battery_percent), retain=True)
      client.publish(f"{MQTT_BASE_TOPIC}/status", status, retain=True)

      print("----------------------------")
      time.sleep(0.5)

  except KeyboardInterrupt:
    print("Exiting monitoring script.")
  finally:
    client.loop_stop()
    client.disconnect()

if __name__ == "__main__":
  main()
