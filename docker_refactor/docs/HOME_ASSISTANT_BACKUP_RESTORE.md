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
~/labpulse-ha/generate_homeassistant_config.sh
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
homeassistant/config/packages/labpulse_thresholds.yaml
homeassistant/config/labpulse_alarm_cards.yaml
homeassistant/config/.storage/lovelace
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

The dashboard is generated into Home Assistant's UI storage:

```text
homeassistant/config/.storage/lovelace
```

That means it appears as a normal editable Home Assistant dashboard, not a
YAML-mode dashboard.

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

preserves the existing UI dashboard.

After MQTT has discovered the LabPulse devices, rebuild the dashboard from Home
Assistant's real entity registry with:

```bash
./generate_homeassistant_config.sh --refresh-dashboard
```

This is useful when the dashboard shows `Entity not found`. The generator reads:

```text
homeassistant/config/.storage/core.entity_registry
```

and uses the entity IDs Home Assistant actually assigned to the MQTT devices.

To intentionally wipe the entire Home Assistant config folder and regenerate it
from `config.yaml`, stop Home Assistant and use:

```bash
docker compose stop homeassistant
./generate_homeassistant_config.sh --fresh-homeassistant
docker compose up -d homeassistant
```

This removes everything under:

```text
~/labpulse-ha/homeassistant/config/
```

including hidden `.storage` files, old dashboards, old helper definitions, and
old generated packages. Use `--backup-homeassistant-ui` first if there is a UI
layout you might want back.

## Backup The Current Home Assistant UI

After editing dashboards in Home Assistant, run:

```bash
cd ~/labpulse-ha
./generate_homeassistant_config.sh --backup-homeassistant-ui
```

Short form:

```bash
./generate_homeassistant_config.sh --backup-ha-ui
```

This creates a timestamped backup:

```text
~/labpulse-ha/homeassistant_backups/ui-YYYYMMDD-HHMMSS/
```

It also refreshes:

```text
~/labpulse-ha/homeassistant_backups/ui-latest/
```

The backup includes the editable dashboard storage file and LabPulse YAML
config, but it does not copy Home Assistant auth/account storage.

## Restore The Latest UI Backup

To restore the latest saved Home Assistant UI/config state:

```bash
cd ~/labpulse-ha
./generate_homeassistant_config.sh --restore-homeassistant-ui
```

Short form:

```bash
./generate_homeassistant_config.sh --restore-ha-ui
```

Do not combine:

```bash
--fresh-homeassistant
--restore-homeassistant-ui
```

Those two options conflict because one clears generated Home Assistant state
while the other restores it.

## Recommended Pattern

1. Run `setup_container_fs.sh` once.
2. Edit `~/labpulse-ha/config.yaml`.
3. Run `./generate_compose.sh`.
4. Run `./generate_homeassistant_config.sh`.
5. Restart Home Assistant or run `docker compose up -d --build`.
6. Edit the dashboard in the Home Assistant UI.
7. Save the edited UI state with `./generate_homeassistant_config.sh --backup-homeassistant-ui`.
