# LabPulse Happy Path Setup

This is the normal setup path for running LabPulse on a Raspberry Pi with
Docker Compose, Home Assistant, Mosquitto, and one Python container per enabled
sensor hub.

The important rule is:

```text
Run setup_container_fs.sh once.
After that, work from ~/labpulse-ha.
```

## 1. Starting Point

Use this guide when you have:

- a Raspberry Pi
- Docker and Docker Compose installed
- this LabPulse repository cloned on the Pi
- Arduino sensor hubs connected by USB, or fake USB serial testing enabled

The live runtime folder will be:

```text
~/labpulse-ha/
```

The live config file will be:

```text
~/labpulse-ha/config.yaml
```

Do not edit the repo template for the running system:

```text
docker_refactor/config.yaml
```

That file is only copied as a starter.

## 2. One-Time Bootstrap

From the repository checkout on the Raspberry Pi:

```bash
cd ~/LabPulse/docker_refactor
chmod +x setup_container_fs.sh
./setup_container_fs.sh
```

For fake USB serial testing instead of real Arduinos:

```bash
./setup_container_fs.sh -fake_usb
```

The setup script creates:

```text
~/labpulse-ha/config.yaml
~/labpulse-ha/compose.yaml
~/labpulse-ha/generate_compose.sh
~/labpulse-ha/generate_homeassistant_config.sh
~/labpulse-ha/homeassistant/config/
~/labpulse-ha/mosquitto/
~/labpulse-ha/labpulse-python/
~/labpulse-ha/logs/
```

It also automatically runs:

```bash
~/labpulse-ha/generate_compose.sh
~/labpulse-ha/generate_homeassistant_config.sh --reset-dashboard
```

## 3. Edit The Live Config

After setup, move into the live folder:

```bash
cd ~/labpulse-ha
```

Edit:

```bash
nano config.yaml
```

Use this file for hardware, enabled services, serial paths, reading names, and
labels. Tune alarm thresholds and delays later in Home Assistant; those values
are dashboard-editable helpers, not `config.yaml` fields.

For real hardware, set stable USB paths such as:

```yaml
services:
  pressure_monitor:
    enabled: true
    serial_port: "/dev/serial/by-id/usb-Arduino_..."
```

Avoid final deployments that depend on:

```text
/dev/ttyUSB0
/dev/ttyACM0
```

Those names can change when devices are unplugged/replugged.

## 4. Regenerate Files

Whenever `config.yaml` changes, regenerate Compose:

```bash
./generate_compose.sh
```

Regenerate Home Assistant config:

```bash
./generate_homeassistant_config.sh
```

Check the generated Compose file:

```bash
docker compose config
```

## 5. Start LabPulse

Build and start the stack:

```bash
docker compose up -d --build
```

Check containers:

```bash
docker compose ps
```

Follow logs:

```bash
docker compose logs -f
```

Useful focused logs:

```bash
docker compose logs -f homeassistant
docker compose logs -f mosquitto
docker compose logs -f labpulse-pressure-monitor
docker compose logs -f labpulse-pump-room
docker compose logs -f labpulse-turbo-pump
```

## 6. Configure Home Assistant

Open Home Assistant in a browser:

```text
http://<raspberry-pi-ip>:8123
```

Create the Home Assistant user account when prompted.

Then add MQTT:

```text
Settings -> Devices & services -> Add integration -> MQTT
```

Use:

```text
Broker: 127.0.0.1
Port: 1883
```

Home Assistant uses host networking in the generated Compose setup, so
`127.0.0.1:1883` reaches Mosquitto on the Pi.

## 7. Wait For MQTT Discovery

The LabPulse Python services publish Home Assistant MQTT discovery messages for:

- service status
- each sensor reading
- newly seen readings from multi-line hubs

Wait for each Arduino hub to emit a full cycle of readings.

LabPulse uses stable MQTT discovery IDs, so entities should appear with names
like:

```text
sensor.labpulse_pressure_monitor_pressure
sensor.labpulse_pressure_monitor_status
binary_sensor.labpulse_pressure_monitor_pressure_alarm
```

If a dashboard card does not match an entity, inspect:

```text
~/labpulse-ha/homeassistant/config/labpulse_entity_map.yaml
```

## 8. Use The Dashboard

The generated dashboard is a normal editable Home Assistant UI dashboard, not a
YAML-mode dashboard.

It includes:

- System Health
- Pump Room
- Cryogenics
- Air Pressure
- current readings
- alarm threshold controls
- alert/recovery delay controls

Threshold logic lives in Home Assistant. The Python services only publish
readings and status.

## 9. Save Dashboard Edits

After editing the dashboard in Home Assistant, save a backup:

```bash
cd ~/labpulse-ha
./generate_homeassistant_config.sh --backup-dashboard
```

This writes:

```text
~/labpulse-ha/homeassistant_backups/dashboard-latest/
```

It avoids copying Home Assistant auth/account storage.

## 10. Restore Dashboard Edits

To restore the latest saved Home Assistant UI/config backup:

```bash
cd ~/labpulse-ha
./generate_homeassistant_config.sh --load-dashboard
docker compose restart homeassistant
```

## 11. Fresh Home Assistant Reset

If Home Assistant config gets messy and you want a clean generated setup:

```bash
cd ~/labpulse-ha
docker compose stop homeassistant
rm -rf ~/labpulse-ha/homeassistant/config
mkdir -p ~/labpulse-ha/homeassistant/config
./generate_homeassistant_config.sh --reset-dashboard
docker compose up -d homeassistant
```

This wipes everything under:

```text
~/labpulse-ha/homeassistant/config/
```

Then it regenerates the LabPulse Home Assistant config from `config.yaml`.

After a fresh reset, add the MQTT integration again in the Home Assistant UI.

## 12. Normal Update Loop

For day-to-day changes:

```bash
cd ~/labpulse-ha
nano config.yaml
./generate_compose.sh
./generate_homeassistant_config.sh
docker compose up -d --build
```

If new sensors/entities appear, add or arrange them in the Home Assistant UI
dashboard. Normal generation does not overwrite your edited dashboard.

## 13. Fake USB Test Path

For simulator testing:

```bash
cd ~/LabPulse/docker_refactor
./setup_container_fs.sh -fake_usb
./simulate_arduinos.sh
```

In another terminal:

```bash
cd ~/labpulse-ha
docker compose up -d --build
```

The fake serial paths are:

```text
/tmp/labpulse-fake-serial/pressure
/tmp/labpulse-fake-serial/pump_room
/tmp/labpulse-fake-serial/turbo_pump
```

## 14. Quick Health Checks

Container status:

```bash
docker compose ps
```

Live container resource usage:

```bash
docker stats
```

Pi memory:

```bash
free -h
```

Disk usage:

```bash
df -h
docker system df
```

Home Assistant logs:

```bash
docker compose logs homeassistant
```

LabPulse service logs:

```bash
docker compose logs labpulse-pump-room
docker compose logs labpulse-pressure-monitor
docker compose logs labpulse-turbo-pump
```

## 15. Common Fixes

If Home Assistant says MQTT config is invalid, remove any YAML like:

```yaml
mqtt:
  broker: 127.0.0.1
  port: 1883
```

Configure MQTT through the Home Assistant UI instead.

If dashboard cards say `Entity not found`, wait for MQTT discovery and compare
the card entity IDs with:

```text
~/labpulse-ha/homeassistant/config/labpulse_entity_map.yaml
```

If old dashboards keep coming back, stop Home Assistant before wiping config:

```bash
docker compose stop homeassistant
rm -rf ~/labpulse-ha/homeassistant/config
mkdir -p ~/labpulse-ha/homeassistant/config
./generate_homeassistant_config.sh --reset-dashboard
docker compose up -d homeassistant
```

If a sensor hub is missing, check:

```bash
ls -l /dev/serial/by-id/
docker compose logs labpulse-<service-name>
```

Then update `~/labpulse-ha/config.yaml` with the correct serial path.
