# Home Assistant Dashboards And Automations

This is the main guide for editing LabPulse dashboard and automation layout.

LabPulse uses Home Assistant in two modes:

1. Generated files that are recreated from `config.yaml` and repository templates.
2. Live UI state that users edit inside Home Assistant.

Understanding that boundary prevents accidental loss of dashboard work.

## The Core Rule

Live dashboard layout is edited in the Home Assistant UI.

Generated starter layout is edited in:

```text
docker_refactor/labpulse_homeassistant/templates/dashboard_seed.yaml
```

Generated alarm helpers and automations are edited in:

```text
docker_refactor/labpulse_homeassistant/templates/alarm_logic.yaml
```

Normal generation preserves the live Home Assistant dashboard:

```bash
cd ~/labpulse-ha
./generate_homeassistant_config.sh
```

Only this command replaces the editable dashboard:

```bash
./generate_homeassistant_config.sh --reset-dashboard
```

## Generated Files

The generator writes:

```text
homeassistant/config/configuration.yaml
homeassistant/config/packages/labpulse_generated.yaml
homeassistant/config/labpulse_entity_map.yaml
```

It creates these if missing and then leaves them alone:

```text
homeassistant/config/automations.yaml
homeassistant/config/scripts.yaml
homeassistant/config/scenes.yaml
```

It writes this only with `--reset-dashboard`:

```text
homeassistant/config/.storage/lovelace
```

`.storage/lovelace` is Home Assistant's editable dashboard storage document.
Once it exists, Home Assistant owns it.

## What To Edit For Each Task

| Task | Edit |
| --- | --- |
| Move cards on the running dashboard | Home Assistant UI |
| Add a one-off card for the running system | Home Assistant UI |
| Save a UI dashboard before experimenting | `./generate_homeassistant_config.sh --backup-dashboard` |
| Restore the latest saved UI dashboard | `./generate_homeassistant_config.sh --load-dashboard` |
| Change what a fresh/reset dashboard looks like | `dashboard_seed.yaml` |
| Change threshold helper names/defaults/ranges | `alarm_logic.yaml` and sometimes `model.py` |
| Add mute controls, deadband, or extra alarm conditions | `alarm_logic.yaml` |
| Change default entity IDs | `homeassistant_mqtt.py`, `model.py`, and tests |
| Change dashboard section names/order/icons | `~/labpulse-ha/config.yaml` |
| Change live threshold values | Home Assistant dashboard helpers |

## Live Dashboard Editing

After setup, open Home Assistant:

```text
http://<raspberry-pi-ip>:8123
```

Edit the dashboard using Home Assistant's normal dashboard editor.

Then save a backup:

```bash
cd ~/labpulse-ha
./generate_homeassistant_config.sh --backup-dashboard
```

This copies the current editable dashboard file to:

```text
~/labpulse-ha/homeassistant_backups/dashboard-YYYYMMDD-HHMMSS/lovelace
~/labpulse-ha/homeassistant_backups/dashboard-latest/lovelace
```

The backup intentionally stores only the dashboard, not Home Assistant auth,
users, tokens, or the entire `.storage` folder.

## Reset Dashboard Editing

The reset dashboard is a seed. It is useful for:

- first bootstrap
- recovering from a messy dashboard
- changing the default layout for future deployments
- testing generated card layout against a changed config

The seed file is:

```text
docker_refactor/labpulse_homeassistant/templates/dashboard_seed.yaml
```

The generator loads it in:

```text
labpulse_homeassistant/dashboard.py
```

Then it expands it over the enabled services and readings from `config.yaml`.

## Dashboard Seed Structure

Current top-level sections:

```yaml
lovelace:
  version: 1
  minor_version: 1
  key: lovelace
  view:
    title: LabPulse
    path: labpulse
    type: sections

system_health:
  heading_card: ...
  status_tile: ...

service_sections:
  heading_card: ...
  status_tile: ...
  reading_tile: ...
  alarm_tile: ...
  include_alarm_settings_card: true
  include_alert_memory_card: true

alarm_settings_card:
  ...

alert_memory_card:
  ...
```

The generated dashboard uses a Home Assistant `sections` view. The Python code
creates:

- one System Health section
- one section for each enabled service
- service status tile
- one reading tile per configured reading
- one alarm tile per configured reading
- optional alarm settings card per service
- optional alert memory card per service

## Dashboard Placeholders

The seed supports placeholders in strings:

```text
{service.name}
{service.service_id}
{service.label}
{service.section}
{service.icon}
{service.status_entity_id}
{service.alert_delay_entity}
{service.recovery_delay_entity}

{reading.name}
{reading.label}
{reading.reading_id}
{reading.expected_entity_id}
{reading.alarm_entity_id}
{reading.active_alert_entity}
{reading.minimum_threshold_entity}
{reading.maximum_threshold_entity}
```

Example:

```yaml
reading_tile:
  type: tile
  entity: "{reading.expected_entity_id}"
  name: "{reading.label}"
  grid_options:
    columns: 6
```

For pressure, this becomes something like:

```yaml
type: tile
entity: sensor.labpulse_pressure_monitor_pressure
name: Pressure
grid_options:
  columns: 6
```

## How To Change A Reset Dashboard Layout

1. Edit:

   ```text
   docker_refactor/labpulse_homeassistant/templates/dashboard_seed.yaml
   ```

2. Re-run setup or copy the updated generator package into the live folder:

   ```bash
   cd ~/LabPulse/docker_refactor
   ./setup_container_fs.sh
   ```

   For fake USB testing:

   ```bash
   ./setup_container_fs.sh -fake_usb
   ```

3. Reset the dashboard intentionally:

   ```bash
   cd ~/labpulse-ha
   ./generate_homeassistant_config.sh --backup-dashboard --reset-dashboard
   docker compose restart homeassistant
   ```

4. Open Home Assistant and inspect the dashboard.

Use `--backup-dashboard --reset-dashboard` when experimenting with an existing
dashboard you might want to restore.

## Alarm Logic Overview

Alarm logic is generated into:

```text
homeassistant/config/packages/labpulse_generated.yaml
```

The source template is:

```text
docker_refactor/labpulse_homeassistant/templates/alarm_logic.yaml
```

The generator loads it in:

```text
labpulse_homeassistant/alarm.py
```

Every reading gets:

- minimum threshold helper
- maximum threshold helper
- visible template binary sensor
- active-alert memory boolean
- alert automation
- recovery automation

Every service with readings gets:

- alert delay helper
- recovery delay helper

## Why Alert Memory Exists

The alarm binary sensor means:

```text
the current reading is outside its threshold range
```

The active-alert input boolean means:

```text
an alert notification has already fired for this alarm
```

Recovery automations check that the active-alert boolean is on before sending a
recovery notification. This prevents healthy startup states from repeatedly
sending "recovered" messages.

## Alarm Seed Structure

Current top-level sections:

```yaml
input_numbers:
  service:
    - id: ...
      config: ...
  reading:
    - id: ...
      config: ...

input_booleans:
  reading:
    - id: ...
      config: ...

binary_sensors:
  reading:
    - name: ...
      unique_id: ...
      state: ...

automations:
  reading:
    - alias: ...
      trigger: ...
      condition: ...
      action: ...
    - alias: ...
      trigger: ...
      condition: ...
      action: ...
```

`service` entries expand once per enabled service.

`reading` entries expand once per configured reading.

## Changing Threshold Defaults

Default threshold values are inferred in:

```text
labpulse_homeassistant/model.py
```

Look for:

```python
THRESHOLD_DEFAULTS
reading_defaults()
build_threshold()
```

The current default families are:

```text
temp
hum
flow
pressure
generic
```

If you only want to change the helper shape, label, range, or mode, edit:

```text
alarm_logic.yaml
```

If you want to change the inferred default numeric values, edit:

```text
model.py
```

Once helpers exist in Home Assistant, changing the generated initial value may
not overwrite Home Assistant's stored state. Tune live thresholds in the
dashboard.

## Adding A Mute Control

A typical mute feature belongs in Home Assistant, not Python.

The likely steps are:

1. Add an `input_boolean` in `alarm_logic.yaml`, probably under `service` or `reading`.
2. Add a condition to alert automations requiring the mute boolean to be off.
3. Add the mute boolean to `dashboard_seed.yaml` so reset dashboards expose it.
4. Regenerate Home Assistant config.
5. Reset the dashboard only if you want the generated layout to include the new control.

For a per-service mute, the helper ID might follow:

```text
input_boolean.labpulse_pump_room_alerts_muted
```

For a per-reading mute:

```text
input_boolean.labpulse_pump_room_flow1_alert_muted
```

Prefer per-service controls unless operators need per-reading control.

## Adding Deadband Or Re-Arm Logic

Start in:

```text
alarm_logic.yaml
```

Possible approaches:

- add a deadband `input_number`
- change the template binary sensor state expression
- add an automation condition
- add another memory boolean if the state machine needs it

Keep the current separation:

```text
Python publishes values.
Home Assistant decides alarm behavior.
```

## Backup, Load, Reset Commands

Normal generation:

```bash
./generate_homeassistant_config.sh
```

Back up current editable dashboard and regenerate generated YAML:

```bash
./generate_homeassistant_config.sh --backup-dashboard
```

Restore latest saved editable dashboard and regenerate generated YAML:

```bash
./generate_homeassistant_config.sh --load-dashboard
```

Replace editable dashboard with generated seed:

```bash
./generate_homeassistant_config.sh --reset-dashboard
```

Back up current dashboard, then replace it with generated seed:

```bash
./generate_homeassistant_config.sh --backup-dashboard --reset-dashboard
```

Rejected combinations:

```text
--reset-dashboard --load-dashboard
--backup-dashboard --load-dashboard
```

## Debugging Dashboard Problems

If a card says an entity is missing:

1. Wait for the relevant sensor container to publish MQTT discovery.
2. Inspect:

   ```text
   ~/labpulse-ha/homeassistant/config/labpulse_entity_map.yaml
   ```

3. Compare the card entity ID with the map.
4. Check the service logs:

   ```bash
   docker compose logs -f labpulse-<service>
   ```

5. Check MQTT discovery:

   ```bash
   docker run --rm -it --network host eclipse-mosquitto:2 \
     mosquitto_sub -h 127.0.0.1 -p 1883 -t 'homeassistant/#' -v
   ```

If a reset dashboard does not reflect seed changes, confirm the updated
`labpulse_homeassistant/` package was copied into `~/labpulse-ha/` and that you
used `--reset-dashboard`.

If live UI edits disappear, check whether someone ran `--reset-dashboard`.
Normal generation does not overwrite `.storage/lovelace`.
