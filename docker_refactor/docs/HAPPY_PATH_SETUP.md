# LabPulse Happy Path Setup

This is the normal setup and update path for running LabPulse on a Raspberry Pi
with Docker Compose, Home Assistant, Mosquitto, SMS, and one Python container
per enabled sensor hub.

The important rule is:

```text
Run setup_container_fs.sh from the repo.
After that, work from ~/labpulse-ha.
```

## Starting Point

Use this guide when you have:

- a Raspberry Pi
- Docker and Docker Compose installed
- this repository cloned on the Pi
- real Arduino USB sensor hubs, or fake USB serial testing

The live runtime folder will be:

```text
~/labpulse-ha/
```

The live config will be:

```text
~/labpulse-ha/config.yaml
```

Do not edit this repo file for the running Pi:

```text
docker_refactor/config.yaml
```

It is only copied as a starter when the live config does not exist.

## One-Time Bootstrap

From the repository checkout:

```bash
cd ~/LabPulse/docker_refactor
chmod +x setup_container_fs.sh
./setup_container_fs.sh
```

For fake USB testing:

```bash
./setup_container_fs.sh -fake_usb
```

The setup script creates or updates:

```text
~/labpulse-ha/config.yaml
~/labpulse-ha/compose.yaml
~/labpulse-ha/generate_compose.sh
~/labpulse-ha/generate_homeassistant_config.sh
~/labpulse-ha/labpulse-python/
~/labpulse-ha/labpulse_homeassistant/
~/labpulse-ha/homeassistant/config/
~/labpulse-ha/mosquitto/
~/labpulse-ha/logs/
```

It also runs:

```bash
~/labpulse-ha/generate_compose.sh
~/labpulse-ha/generate_homeassistant_config.sh --reset-dashboard
```

The first run seeds the editable Home Assistant dashboard. Later normal
generation preserves dashboard edits.

## Edit The Live Config

After setup:

```bash
cd ~/labpulse-ha
nano config.yaml
```

Use this file for:

- enabling or disabling services
- serial USB paths
- driver and parser selection
- device names
- reading names, labels, units, and device classes
- dashboard section names, icons, and order
- SMS recipients and backend

Tune alarm thresholds and delays in Home Assistant after the helpers are
generated. Threshold values do not live in `config.yaml`.

For real hardware, use stable USB paths:

```yaml
services:
  pressure_monitor:
    serial_port: "/dev/serial/by-id/usb-Arduino_..."
```

Avoid:

```text
/dev/ttyACM0
/dev/ttyUSB0
```

Those can change after reboot or unplug/replug.

## Regenerate Generated Files

After changing `config.yaml`:

```bash
cd ~/labpulse-ha
./generate_compose.sh
./generate_homeassistant_config.sh
docker compose config
```

`generate_compose.sh` updates:

```text
compose.yaml
```

`generate_homeassistant_config.sh` updates:

```text
homeassistant/config/configuration.yaml
homeassistant/config/packages/labpulse_generated.yaml
homeassistant/config/labpulse_entity_map.yaml
```

Normal Home Assistant generation does not overwrite the editable dashboard.

## Start LabPulse

```bash
cd ~/labpulse-ha
docker compose up -d --build
```

Check containers:

```bash
docker compose ps
```

Expected names:

```text
labpulse-homeassistant
labpulse-mqtt
labpulse-sms
labpulse-pressure-monitor
labpulse-pump-room
labpulse-turbo-pump
```

Disabled services will not have containers.

## Configure Home Assistant

Open:

```text
http://<raspberry-pi-ip>:8123
```

Create the Home Assistant user when prompted.

Add MQTT:

```text
Settings -> Devices & services -> Add integration -> MQTT
```

Use:

```text
Broker: 127.0.0.1
Port: 1883
```

Home Assistant uses host networking, so `127.0.0.1:1883` reaches Mosquitto on
the Pi.

## Wait For Discovery

LabPulse services publish MQTT discovery for:

- each service status entity
- each configured reading once that reading is seen

Expected entity IDs look like:

```text
sensor.labpulse_pressure_monitor_status
sensor.labpulse_pressure_monitor_pressure
binary_sensor.labpulse_pressure_monitor_pressure_alarm
input_number.labpulse_pressure_monitor_pressure_minimum_threshold
input_number.labpulse_pressure_monitor_pressure_maximum_threshold
```

If a dashboard card cannot find an entity, inspect:

```text
~/labpulse-ha/homeassistant/config/labpulse_entity_map.yaml
```

## Use And Edit The Dashboard

The generated dashboard is a normal Home Assistant UI dashboard.

Edit the live layout in the Home Assistant UI.

After edits, back it up:

```bash
cd ~/labpulse-ha
./generate_homeassistant_config.sh --backup-dashboard
```

To intentionally replace the dashboard with the generated starter layout:

```bash
./generate_homeassistant_config.sh --backup-dashboard --reset-dashboard
docker compose restart homeassistant
```

## Normal Update Loop

For day-to-day changes:

```bash
cd ~/labpulse-ha
nano config.yaml
./generate_compose.sh
./generate_homeassistant_config.sh
docker compose up -d --build
```

Then use the Home Assistant UI to arrange any new entities.

## Fake USB Test Path

Terminal 1:

```bash
cd ~/LabPulse/docker_refactor
./setup_container_fs.sh -fake_usb
./simulate_arduinos.sh
```

Terminal 2:

```bash
cd ~/labpulse-ha
docker compose up -d --build
docker compose logs -f
```

Fake serial paths:

```text
/tmp/labpulse-fake-serial/pressure
/tmp/labpulse-fake-serial/pump_room
/tmp/labpulse-fake-serial/turbo_pump
```

Alarm scenarios are available from the simulator. For example, this drives pump
room flow 1 below the default minimum threshold:

```bash
./simulate_arduinos.sh --scenario pump_room.flow1=danger-low
```

Once the simulator is running, use the live scenario file to change state
without recreating the fake serial devices:

```bash
printf 'pump_room.flow1=danger-low\n' > /tmp/labpulse-fake-serial/scenarios.txt
printf 'pump_room.flow1=recover\n' > /tmp/labpulse-fake-serial/scenarios.txt
```

To test stale detection without breaking the fake serial link:

```bash
printf 'pump_room.flow1=stale\n' > /tmp/labpulse-fake-serial/scenarios.txt
```

Wait for Home Assistant's danger ratio window and recovery timer when checking
the state machine. For stale tests, wait for the service stale timeout helper.

For fake DHT11 input on a test Pi, enable `room_environment` with:

```yaml
driver: gpio
gpio_sensor: fake_dht11
fake_state_file: "/tmp/labpulse-fake-dht11/room_environment.env"
```

Then change the fake DHT values live:

```bash
printf 'mode=live\ntemperature=21.5\nhumidity=48.0\n' \
  > /tmp/labpulse-fake-dht11/room_environment.env
```

Stopping and restarting `simulate_arduinos.sh` simulates USB devices
disappearing and returning.

## Useful Logs

All logs:

```bash
docker compose logs -f
```

Focused logs:

```bash
docker compose logs -f homeassistant
docker compose logs -f mosquitto
docker compose logs -f labpulse-sms
docker compose logs -f labpulse-pressure-monitor
docker compose logs -f labpulse-pump-room
docker compose logs -f labpulse-turbo-pump
```

Persistent Python logs:

```text
~/labpulse-ha/logs/pressure_monitor.log
~/labpulse-ha/logs/pump_room.log
~/labpulse-ha/logs/turbo_pump.log
~/labpulse-ha/logs/sms.log
```

## Common Fixes

If Home Assistant MQTT setup fails, remove any old YAML-based MQTT broker config
from `configuration.yaml` and add MQTT through the UI.

If Python containers cannot connect to MQTT, check:

```yaml
mqtt:
  broker: "mosquitto"
```

If entities are missing, wait for sensor readings and check:

```text
~/labpulse-ha/homeassistant/config/labpulse_entity_map.yaml
```

If a sensor hub is missing, check:

```bash
ls -l /dev/serial/by-id/
docker compose logs labpulse-<service-name>
```

Then update `~/labpulse-ha/config.yaml` with the correct serial path and
regenerate.
