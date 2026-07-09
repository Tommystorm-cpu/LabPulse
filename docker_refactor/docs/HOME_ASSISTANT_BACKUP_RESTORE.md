# Home Assistant Config Workflow

LabPulse uses a one-time setup script to create the live Raspberry Pi folder:

```text
~/labpulse-ha/
```

After that, normal work should happen from that folder.

## One-Time Setup

Run this from the repository checkout on the Raspberry Pi:

```bash
./setup_container_fs.sh
```

The setup script creates or refreshes:

```text
~/labpulse-ha/config.yaml
~/labpulse-ha/compose.yaml
~/labpulse-ha/generate_compose.sh
~/labpulse-ha/generate_homeassistant_config.sh
~/labpulse-ha/homeassistant/config/
~/labpulse-ha/labpulse-python/
~/labpulse-ha/mosquitto/
```

It also automatically runs:

```bash
~/labpulse-ha/generate_compose.sh
~/labpulse-ha/generate_homeassistant_config.sh --reset-dashboard
```

## Day-To-Day Workflow

After setup, work from:

```bash
cd ~/labpulse-ha
```

Edit the live hardware config:

```bash
nano config.yaml
```

Then regenerate Docker Compose:

```bash
./generate_compose.sh
```

And regenerate Home Assistant config:

```bash
./generate_homeassistant_config.sh
```

Then restart or recreate the containers as needed:

```bash
docker compose up -d --build
```

## What Home Assistant Config Is Generated

The Home Assistant generator creates:

```text
homeassistant/config/configuration.yaml
homeassistant/config/packages/labpulse_generated.yaml
homeassistant/config/labpulse_entity_map.yaml
homeassistant/config/.storage/lovelace only when --reset-dashboard is used
```

The generated `configuration.yaml` includes the main Home Assistant pieces
LabPulse needs:

```yaml
homeassistant:
  packages: !include_dir_named packages

default_config:
frontend:
history:
logbook:
my:
mobile_app:
system_health:
```

MQTT broker connection settings are not generated in `configuration.yaml`
because current Home Assistant versions configure the MQTT broker through the
MQTT integration UI/config entry. After a fresh setup, add MQTT in Home
Assistant:

```text
Settings -> Devices & services -> Add integration -> MQTT
```

Use:

```text
Broker: 127.0.0.1
Port: 1883
```

Passwords and Home Assistant user accounts are not generated. Those remain
managed by Home Assistant.

## Editable Dashboard

The starter dashboard is generated into Home Assistant's UI storage:

```text
homeassistant/config/.storage/lovelace
```

That means it appears as a normal editable Home Assistant dashboard, not a
YAML-mode dashboard.

The seed layout comes from:

```text
docker_refactor/labpulse_homeassistant/templates/dashboard_seed.yaml
```

Edit that repository seed when changing what `--reset-dashboard` creates.

The generator creates a layout with:

- System Health
- Pump Room
- Cryogenics
- Air Pressure
- all known sensor readings from enabled services
- compact alarm setting cards for thresholds and delays

If a user has already edited the dashboard in Home Assistant, running:

```bash
./generate_homeassistant_config.sh
```

preserves the existing UI dashboard exactly.

To intentionally replace the editable dashboard with the generated starter
dashboard, run:

```bash
./generate_homeassistant_config.sh --reset-dashboard
```

Stable MQTT discovery IDs mean generated entities use predictable IDs such as:

```text
sensor.labpulse_pressure_monitor_pressure
binary_sensor.labpulse_pressure_monitor_pressure_alarm
```

When a dashboard entity looks wrong, inspect:

```text
homeassistant/config/labpulse_entity_map.yaml
```

To completely wipe the old Home Assistant config folder before installing the
new generated setup, stop Home Assistant and remove the config folder:

```bash
docker compose stop homeassistant
rm -rf ~/labpulse-ha/homeassistant/config
mkdir -p ~/labpulse-ha/homeassistant/config
./generate_homeassistant_config.sh --reset-dashboard
docker compose up -d homeassistant
```

This removes everything under:

```text
~/labpulse-ha/homeassistant/config/
```

including hidden `.storage` files, dashboards, helper definitions, and generated
package files. Use `--backup-dashboard` first if there is a dashboard
layout you might want back.

## Backup The Current Dashboard

After editing dashboards in Home Assistant, run:

```bash
cd ~/labpulse-ha
./generate_homeassistant_config.sh --backup-dashboard
```

This creates a timestamped backup:

```text
~/labpulse-ha/homeassistant_backups/dashboard-YYYYMMDD-HHMMSS/
```

It also refreshes:

```text
~/labpulse-ha/homeassistant_backups/dashboard-latest/
```

The backup includes only the editable dashboard storage file. It does not copy
Home Assistant auth/account storage.

## Load The Latest Dashboard Backup

To restore the latest saved editable dashboard:

```bash
cd ~/labpulse-ha
./generate_homeassistant_config.sh --load-dashboard
```

Do not combine:

```bash
--reset-dashboard
--load-dashboard
```

Those two options conflict because one replaces the dashboard with the generated
starter layout while the other restores the latest saved dashboard.

## Recommended Pattern

1. Run `setup_container_fs.sh` once.
2. Edit `~/labpulse-ha/config.yaml`.
3. Run `./generate_compose.sh`.
4. Run `./generate_homeassistant_config.sh`.
5. Restart Home Assistant or run `docker compose up -d --build`.
6. Edit the dashboard in the Home Assistant UI.
7. Save the edited dashboard with `./generate_homeassistant_config.sh --backup-dashboard`.
