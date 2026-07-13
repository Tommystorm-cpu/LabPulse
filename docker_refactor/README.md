# LabPulse Docker Refactor

This folder contains the Docker-based LabPulse runtime for the Raspberry Pi.
It runs:

- Home Assistant for the operator dashboard, threshold helpers, and automations.
- Mosquitto for MQTT.
- One `labpulse-sms` container for alert delivery.
- One Python sensor container for each enabled sensor hub in `config.yaml`.

Source ownership is split between `labpulse_common` (shared validated config
and contracts), `labpulse_hardware` (drivers and MQTT publishing),
`labpulse_homeassistant` (dashboard/alarm generation), and `labpulse_sms`
(alert delivery).

The live Raspberry Pi system is generated into:

```text
~/labpulse-ha/
```

After the first bootstrap, edit the live file:

```text
~/labpulse-ha/config.yaml
```

Do not edit `docker_refactor/config.yaml` to change a running Pi. The repo copy
is only a starter template.

## Start Here

Read [docs/README.md](docs/README.md) for the full documentation map.

The shortest useful path is:

1. [docs/HAPPY_PATH_SETUP.md](docs/HAPPY_PATH_SETUP.md)
2. [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
3. [docs/HOME_ASSISTANT_DASHBOARDS_AND_AUTOMATIONS.md](docs/HOME_ASSISTANT_DASHBOARDS_AND_AUTOMATIONS.md)
4. [docs/CODE_READING_GUIDE.md](docs/CODE_READING_GUIDE.md)

## Normal Workflow

```bash
cd ~/LabPulse/docker_refactor
./setup_container_fs.sh

cd ~/labpulse-ha
nano config.yaml
./generate_compose.sh
./generate_homeassistant_config.sh
docker compose up -d --build
```

For fake USB testing:

```bash
cd ~/LabPulse/docker_refactor
./setup_container_fs.sh -fake_usb
cd ~/labpulse-ha
python3 simulate_serial.py start
```

Change simulated behavior while the background service is running:

```bash
python3 simulate_serial.py set pump_room.flow1 danger-low
python3 simulate_serial.py set pump_room.flow1 recover
python3 simulate_serial.py set pump_room.flow1 stale
python3 simulate_serial.py set room_environment.temperature danger-high
```

Inspect or clear the in-memory scenarios with:

```bash
python3 simulate_serial.py status
python3 simulate_serial.py clear pump_room.flow1
python3 simulate_serial.py reset
```

Then in another terminal:

```bash
docker compose up -d --build
```

## Editing Dashboards And Automations

Live dashboard layout is edited in the Home Assistant UI.

The generated starter dashboard, used only when `--reset-dashboard` is passed,
comes from:

```text
labpulse_homeassistant/templates/dashboard/dashboard_seed.yaml
```

Generated alarm helpers, binary sensors, and alert/recovery automations come
from:

```text
labpulse_homeassistant/templates/alarm/alarm_logic.yaml
```

See [docs/HOME_ASSISTANT_DASHBOARDS_AND_AUTOMATIONS.md](docs/HOME_ASSISTANT_DASHBOARDS_AND_AUTOMATIONS.md)
for the detailed editing guide.
