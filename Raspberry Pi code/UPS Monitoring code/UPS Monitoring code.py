import smbus2
import time
import json
from paho.mqtt.client import Client
from datetime import datetime
import threading
import subprocess  # for running mmcli commands
import queue

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
VOLTAGE_MIN = 6.0
VOLTAGE_MAX = 7.92

# List of phone numbers to send SMS to
SMS_PHONE_NUMBERS = [
    "+447955656806", # Matt's Number
    "+447474510525" # Sam's Number
]
# Global SMS message queue
sms_queue = queue.Queue()

def sms_sender_worker():
    while True:
        phone_number, message = sms_queue.get()
        try:
            send_sms(phone_number, message)
        except:
            print("[DEBUG] Failed to send SMS")
        finally:
            sms_queue.task_done()

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
    bus_voltage = ((raw_bus_voltage >> 3) * 4) / 1000.0
    raw_current = read_word(REG_CURRENT)
    current = twos_complement(raw_current, 16)
    current_mA = current * 0.1
    return bus_voltage, current_mA

def calculate_battery_percentage(voltage):
    voltage = max(min(voltage, VOLTAGE_MAX), VOLTAGE_MIN)
    percent = (voltage - VOLTAGE_MIN) / (VOLTAGE_MAX - VOLTAGE_MIN) * 100
    return round(min(percent, 100))

def determine_charging_status(current_mA):
    if current_mA > 40:
        return "Charging..."
    elif current_mA < -49:
        return "Discharging..."
    else:
        return "idle"

def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")

def on_disconnect(client, userdata, rc):
    print(f"Disconnected with result code {rc}")

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
            "icon": "mdi:battery-charging",
            "payload_on": "Charging...",
            "payload_off": "Discharging...",
            "payload_available": "idle",
        },
        {
            "name": "UPS Last Outage Duration",
            "state_topic": f"{MQTT_BASE_TOPIC}/last_outage_duration",
            "unit_of_measurement": "s",
            "device_class": "duration",
            "unique_id": "ups_last_outage_duration_sensor",
            "device": base_device,
            "icon": "mdi:clock-outline"
        },
        {
            "name": "Date of Last Outage",
            "state_topic": f"{MQTT_BASE_TOPIC}/last_outage_date",
            "unique_id": "ups_last_outage_date_sensor",
            "device": base_device,
            "icon": "mdi:calendar-clock"
        }
    ]

    for sensor in sensors:
        topic = f"homeassistant/sensor/{sensor['unique_id']}/config"
        client.publish(topic, json.dumps(sensor), retain=True)

def send_sms(phone_number: str, message: str):
    try:
        print(f"Creating SMS to {phone_number}")
        result = subprocess.run(
            ['mmcli', '-m', '0', '--messaging-create-sms', f'text="{message}",number={phone_number}'],
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


def main():
    threading.Thread(target=sms_sender_worker, daemon=True).start()
    calibrate_ina219()
    tracking_outage = False
    init_time = None
    confirm_in_progress = False
    outage_check_in_progress = False
    outage_sms_sent = False
    lock = threading.Lock()
    outage_start_str = None

    client = Client(client_id=MQTT_CLIENT_ID)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_publish = on_publish

    client.connect(MQTT_BROKER, MQTT_PORT)
    client.loop_start()

    publish_discovery(client)

    print("Monitoring UPS HAT battery status. Press Ctrl+C to exit.")

    def confirm_power_restored(num_checks=3, delay=0.5):
        for _ in range(num_checks):
            time.sleep(delay)
            _, current_mA_check = read_voltage_current()
            if determine_charging_status(current_mA_check) == "Discharging...":
                return False
        return True

    def confirm_power_out(init_time, required_duration=0.25, timeout=1.0):
        check_interval = 0.01
        print(f"[DEBUG] Starting power outage confirmation at {init_time:.3f}")
        while time.time() - init_time < timeout:
            time.sleep(check_interval)
            _, current_mA_check = read_voltage_current()
            if determine_charging_status(current_mA_check) != "Discharging...":
                print(f"[DEBUG] Power restored during confirmation at {time.time():.3f}")
                return False
            if time.time() - init_time >= required_duration:
                print(f"[DEBUG] Outage confirmed at {time.time():.3f} (duration met)")
                return True
        print(f"[DEBUG] Outage confirmation timed out at {time.time():.3f}")
        return False


    def confirm_and_send_outage_sms():
        nonlocal outage_check_in_progress, outage_sms_sent, init_time, outage_start_str
        print("[DEBUG] Outage confirmation thread started.")
        if confirm_power_out(init_time):
            with lock:
                if tracking_outage:
                    outage_start_str = datetime.fromtimestamp(init_time).strftime("%d/%m/%Y %H:%M:%S")
                    print("[DEBUG] Outage verified. Sending SMS...")
                    broadcast_sms(f"Power outage detected at {outage_start_str} for at least 0.25s. System running on batteries.")
                    outage_sms_sent = True
        else:
            print("[DEBUG] Outage was too brief or recovered quickly. No SMS sent.")
        outage_check_in_progress = False


    def confirm_and_publish():
        nonlocal tracking_outage, init_time, confirm_in_progress, outage_sms_sent, outage_start_str
        if confirm_power_restored():
            final_time = time.time()
            with lock:
                if tracking_outage and init_time is not None:
                    discharging_time = final_time - init_time - 1.5
                    outage_start_str = datetime.fromtimestamp(init_time).strftime("%d/%m/%Y %H:%M:%S")
                    outage_end_str = datetime.fromtimestamp(final_time).strftime("%d/%m/%Y %H:%M:%S")
                    print(f"Power was disconnected for {discharging_time:.3f}s")
                    client.publish(f"{MQTT_BASE_TOPIC}/last_outage_duration", f"{discharging_time:.3f}", retain=True)
                    client.publish(f"{MQTT_BASE_TOPIC}/last_outage_date", outage_start_str, retain=True)
                    tracking_outage = False
                    init_time = None
                    if outage_sms_sent:
                        sms_msg = f"Power restored after {discharging_time:.2f} seconds at {outage_end_str}."
                        threading.Thread(target=broadcast_sms, args=(sms_msg,), daemon=True).start()
                    else:
                        print("[DEBUG] Power restored but outage SMS was never sent, skipping SMS.")
        else:
            print("Power still discharging during confirmation, continue tracking.")
        confirm_in_progress = False


    try:
        while True:
            bus_voltage, current_mA = read_voltage_current()
            battery_percent = calculate_battery_percentage(bus_voltage)
            status = determine_charging_status(current_mA)

            print(f"Battery Voltage: {bus_voltage:.2f} V")
            print(f"Current: {current_mA:.1f} mA")
            print(f"Status: {status}")
            print(f"Battery Percentage: {battery_percent}%")

            with lock:
                if status == "Discharging..." and not tracking_outage and not confirm_in_progress and not outage_check_in_progress:
                    init_time = time.time()
                    tracking_outage = True
                    outage_sms_sent = False
                    outage_check_in_progress = True
                    threading.Thread(target=confirm_and_send_outage_sms, daemon=True).start()

                elif status != "Discharging..." and tracking_outage and not confirm_in_progress:
                    confirm_in_progress = True
                    threading.Thread(target=confirm_and_publish, daemon=True).start()

            client.publish(f"{MQTT_BASE_TOPIC}/voltage", f"{bus_voltage:.2f}", retain=True)
            client.publish(f"{MQTT_BASE_TOPIC}/current", f"{current_mA:.1f}", retain=True)
            client.publish(f"{MQTT_BASE_TOPIC}/percentage", str(battery_percent), retain=True)
            client.publish(f"{MQTT_BASE_TOPIC}/status", status, retain=True)

            print("----------------------------")
            time.sleep(0.03)

    except KeyboardInterrupt:
        print("Exiting monitoring script.")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()


