# Home Assistant Backup, Restore, And Reset

LabPulse preserves the editable Home Assistant dashboard by default.

Normal generation:

```bash
cd ~/labpulse-ha
./generate_homeassistant_config.sh
```

updates generated YAML files but does not touch:

```text
homeassistant/config/.storage/lovelace
```

That file is Home Assistant's editable dashboard storage file.

## What Is Backed Up

The LabPulse backup command backs up only:

```text
homeassistant/config/.storage/lovelace
```

It does not back up:

- Home Assistant users
- authentication files
- tokens
- all of `.storage`
- database/history
- MQTT integration config entries

This is intentional. The command is for saving dashboard layout before layout
experiments.

## Back Up The Current Dashboard

```bash
cd ~/labpulse-ha
./generate_homeassistant_config.sh --backup-dashboard
```

This writes:

```text
homeassistant_backups/dashboard-YYYYMMDD-HHMMSS/lovelace
homeassistant_backups/dashboard-latest/lovelace
```

It also regenerates the normal generated Home Assistant YAML files:

```text
homeassistant/config/configuration.yaml
homeassistant/config/packages/labpulse_generated.yaml
homeassistant/config/labpulse_entity_map.yaml
```

It does not modify the live dashboard.

## Restore The Latest Dashboard Backup

```bash
cd ~/labpulse-ha
./generate_homeassistant_config.sh --load-dashboard
docker compose restart homeassistant
```

This copies:

```text
homeassistant_backups/dashboard-latest/lovelace
```

to:

```text
homeassistant/config/.storage/lovelace
```

It also regenerates generated YAML.

## Reset To The Generated Starter Dashboard

```bash
cd ~/labpulse-ha
./generate_homeassistant_config.sh --reset-dashboard
docker compose restart homeassistant
```

This replaces:

```text
homeassistant/config/.storage/lovelace
```

with a newly generated dashboard from:

```text
docker_refactor/labpulse_homeassistant/templates/dashboard/dashboard_seed.yaml
```

Use this when you intentionally want to discard the current live dashboard
layout.

## Safe Experiment Command

When experimenting with dashboard seed changes, use:

```bash
cd ~/labpulse-ha
./generate_homeassistant_config.sh --backup-dashboard --reset-dashboard
docker compose restart homeassistant
```

This saves the current dashboard first, then replaces it with the generated
starter dashboard.

## Rejected Flag Combinations

These combinations are rejected because they are ambiguous:

```text
--reset-dashboard --load-dashboard
--backup-dashboard --load-dashboard
```

This combination is allowed:

```text
--backup-dashboard --reset-dashboard
```

because it explicitly means "save current dashboard, then replace it."

## Fresh Home Assistant Config Reset

If you need to wipe the whole Home Assistant config folder and regenerate a
clean LabPulse setup:

```bash
cd ~/labpulse-ha
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

including `.storage`, users, dashboard state, integrations, generated packages,
and UI-managed YAML files.

After this reset, open Home Assistant and add the MQTT integration again:

```text
Settings -> Devices & services -> Add integration -> MQTT
Broker: 127.0.0.1
Port: 1883
```

## Which Command Should I Use?

| Situation | Command |
| --- | --- |
| Regenerate YAML after config change | `./generate_homeassistant_config.sh` |
| Save dashboard before UI experiments | `./generate_homeassistant_config.sh --backup-dashboard` |
| Restore last saved dashboard | `./generate_homeassistant_config.sh --load-dashboard` |
| Replace dashboard with generated seed | `./generate_homeassistant_config.sh --reset-dashboard` |
| Safely inspect a new seed layout | `./generate_homeassistant_config.sh --backup-dashboard --reset-dashboard` |

For layout editing details, see
[HOME_ASSISTANT_DASHBOARDS_AND_AUTOMATIONS.md](HOME_ASSISTANT_DASHBOARDS_AND_AUTOMATIONS.md).
