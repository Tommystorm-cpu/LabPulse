# Home Assistant Rewrite Brief

This brief is the implementation reference for the next `labpulse_homeassistant`
rewrite. It captures the agreed model from planning discussions.

## Goals

- Keep `~/labpulse-ha/config.yaml` as the user-edited source of truth.
- Keep the Home Assistant dashboard editable in the Home Assistant UI.
- Reduce Python code in `labpulse_homeassistant/`.
- Move readable Home Assistant behavior into template YAML files.
- Use stable LabPulse MQTT discovery IDs so dashboard entities are predictable.
- Keep `config.yaml` focused on hardware, labels, readings, and display
  metadata. Alarm values live in Home Assistant helpers.
- Avoid backwards compatibility and migration layers. LabPulse is not in live use
  yet, so implement the clean current model directly.

## Responsibility Split

LabPulse Python services publish facts:

- MQTT discovery config
- sensor readings
- service status/health

Home Assistant owns operator behavior:

- thresholds
- alarm state
- alert/recovery automations
- notification text
- dashboard layout

The generator connects these two worlds by reading `config.yaml`, rendering Home
Assistant YAML/templates, and optionally creating or restoring the editable
dashboard storage file.

## Stable Entity Naming

MQTT discovery should use stable machine IDs for both `unique_id` and
`object_id`, and it should set `default_entity_id` to the desired Home
Assistant entity ID. Home Assistant uses `default_entity_id`, not the discovery
topic object ID, when deciding the preferred `entity_id`.

For service `pressure_monitor` and reading `pressure`:

```text
unique_id: labpulse_pressure_monitor_pressure
object_id: labpulse_pressure_monitor_pressure
default_entity_id: sensor.labpulse_pressure_monitor_pressure
expected entity_id: sensor.labpulse_pressure_monitor_pressure
```

For service status:

```text
unique_id: labpulse_pressure_monitor_status
object_id: labpulse_pressure_monitor_status
default_entity_id: sensor.labpulse_pressure_monitor_status
expected entity_id: sensor.labpulse_pressure_monitor_status
```

Friendly names remain human-readable:

```text
name: Pressure
device.name: Air Pressure Sensor Hub
```

Generated Home Assistant helpers should follow the same stable pattern:

```text
binary_sensor.labpulse_pressure_monitor_pressure_alarm
input_boolean.labpulse_pressure_monitor_pressure_alert_active
input_number.labpulse_pressure_monitor_pressure_minimum_threshold
input_number.labpulse_pressure_monitor_pressure_maximum_threshold
input_number.labpulse_pressure_monitor_alert_delay_seconds
input_number.labpulse_pressure_monitor_recovery_delay_seconds
```

The generator does not read Home Assistant's entity registry. Stable MQTT
`default_entity_id` values are the clean source of expected sensor entity IDs.

## Generated Files

The live Raspberry Pi folder should look like:

```text
~/labpulse-ha/
  config.yaml
  compose.yaml
  generate_compose.sh
  generate_homeassistant_config.sh
  homeassistant/
    config/
      configuration.yaml
      labpulse_entity_map.yaml
      packages/
        labpulse_generated.yaml
      .storage/
        lovelace
  homeassistant_backups/
    dashboard-YYYYMMDD-HHMMSS/
      lovelace
    dashboard-latest/
      lovelace
```

Normal generation updates:

- `homeassistant/config/configuration.yaml`
- `homeassistant/config/packages/labpulse_generated.yaml`
- `homeassistant/config/labpulse_entity_map.yaml`

Normal generation must not touch:

- `homeassistant/config/.storage/lovelace`

Dashboard commands are the only commands that modify `.storage/lovelace`.

## Proposed Package Layout

The rewritten generator should be small and template-oriented:

```text
docker_refactor/labpulse_homeassistant/
  generator.py
  config_io.py
  model.py
  render.py
  dashboard.py
  alarm.py
  template_utils.py
  templates/
    configuration.yaml.j2
    package.yaml.j2
    initial_lovelace.json.j2
    entity_map.yaml.j2
    dashboard_seed.yaml
    alarm_logic.yaml
```

`model.py` should normalize enabled services/readings into a simple render
model. Templates should be responsible for the visible Home Assistant YAML/JSON
shape.

The model should not parse per-reading alarm policy from `config.yaml`.
Threshold helper defaults are inferred from reading names and units, then edited
in Home Assistant after generation.

`dashboard_seed.yaml` should own the starter dashboard layout. Python should
only expand the seed over enabled services/readings and fill placeholders such
as `{service.status_entity_id}` or `{reading.alarm_entity_id}`.

`alarm_logic.yaml` should own the generated alarm/helper/automation shapes.
Python should only expand the seed over enabled services/readings. This keeps
future features such as mute controls, re-arm timers, trigger-reset deadbands,
and alternate notification actions approachable as YAML edits.

## Generated Home Assistant Package

`packages/labpulse_generated.yaml` should contain:

- `input_number` helpers for thresholds
- `input_number` helpers for alert/recovery delays
- `input_boolean` helpers for active alert memory
- `template` binary sensors for alarm state
- `automation` entries for alert notifications
- `automation` entries for recovery notifications

These sections are generated from
`docker_refactor/labpulse_homeassistant/templates/alarm_logic.yaml`.

Every reading should get a minimum helper, a maximum helper, and one visible
range-check alarm binary sensor. For readings that are usually "minimum only",
such as pressure and flow, the generated maximum starts very high and can be
edited in Home Assistant if needed.

Prefer visible template binary sensors over embedding threshold logic directly
inside automation triggers. For example:

```yaml
template:
  - binary_sensor:
      - name: "LabPulse Pressure Alarm"
        unique_id: "labpulse_pressure_monitor_pressure_alarm"
        device_class: problem
        state: >
          {{ states('sensor.labpulse_pressure_monitor_pressure') | float(0)
             < states('input_number.labpulse_pressure_monitor_pressure_minimum_threshold') | float(0)
             or states('sensor.labpulse_pressure_monitor_pressure') | float(0)
             > states('input_number.labpulse_pressure_monitor_pressure_maximum_threshold') | float(0) }}

automation:
  - alias: "LabPulse Pressure Alert"
    mode: single
    trigger:
      - platform: state
        entity_id: binary_sensor.labpulse_pressure_monitor_pressure_alarm
        to: "on"
        for:
          seconds: >
            {{ states('input_number.labpulse_pressure_monitor_alert_delay_seconds') | int(2) }}
```

This makes alarm state inspectable in Home Assistant Developer Tools and easy to
place on the dashboard.

Recovery notifications must only fire after a matching alert has actually been
registered. Each reading therefore gets an active-alert boolean:

```yaml
input_boolean:
  labpulse_pressure_monitor_pressure_alert_active:
    name: Pressure Alert Active
    initial: false
```

Alert automations check that this boolean is `off`, turn it `on`, then notify.
Recovery automations check that it is `on`, turn it `off`, then notify. This
prevents startup or normal healthy readings from producing continuous recovery
notifications.

## Dashboard Model

The dashboard must remain editable in the Home Assistant UI.

The generator may write:

```text
homeassistant/config/.storage/lovelace
```

but only when a dashboard command explicitly asks it to. The generated Lovelace
document is a starter dashboard, not the ongoing source of truth after the user
edits the dashboard in Home Assistant.

The starter dashboard should include useful default sections/cards, but day to
day dashboard layout is managed in Home Assistant itself. To change what a fresh
or reset dashboard looks like, edit
`docker_refactor/labpulse_homeassistant/templates/dashboard_seed.yaml`.

Within each sensor section, reading tiles should use short local names such as
`Pressure` or `Flow 1` because the sensor hub is already implied by the section.
Reading and alarm-state tiles should be half-width so they can sit side by side.
The generated alert-active input booleans should live in their own
`Alert Memory` card so that card can be removed easily after debugging.

## Command Behavior

### No Flag

```bash
./generate_homeassistant_config.sh
```

Behavior:

- regenerate generated Home Assistant YAML/config/entity map
- never create, overwrite, reset, backup, or load the dashboard
- preserve `.storage/lovelace` exactly as it is

### Reset Dashboard

```bash
./generate_homeassistant_config.sh --reset-dashboard
```

Behavior:

- regenerate generated Home Assistant YAML/config/entity map
- create or replace `.storage/lovelace` with the generated starter dashboard
- do not make an automatic backup

This is used for first setup and for intentionally discarding the current UI
dashboard layout.

### Backup Dashboard

```bash
./generate_homeassistant_config.sh --backup-dashboard
```

Behavior:

- copy current `.storage/lovelace` to a timestamped dashboard backup
- update `homeassistant_backups/dashboard-latest/lovelace`
- regenerate generated Home Assistant YAML/config/entity map
- do not modify the live dashboard

### Load Dashboard

```bash
./generate_homeassistant_config.sh --load-dashboard
```

Behavior:

- restore `homeassistant_backups/dashboard-latest/lovelace` to `.storage/lovelace`
- regenerate generated Home Assistant YAML/config/entity map
- do not reset the dashboard from templates
- do not make an automatic backup

### Backup Then Reset Dashboard

```bash
./generate_homeassistant_config.sh --backup-dashboard --reset-dashboard
```

Behavior:

- backup current `.storage/lovelace`
- regenerate generated Home Assistant YAML/config/entity map
- replace `.storage/lovelace` with the generated starter dashboard

This is the explicit safe path before resetting a hand-edited dashboard.

## Flag Conflicts

The script should reject ambiguous combinations:

```text
--reset-dashboard + --load-dashboard
--backup-dashboard + --load-dashboard
```

The script should allow:

```text
--backup-dashboard + --reset-dashboard
```

because that is an explicit backup followed by an explicit reset.

## First Setup Workflow

Fresh Raspberry Pi setup:

```bash
./setup_container_fs.sh
cd ~/labpulse-ha
nano config.yaml
./generate_compose.sh
./generate_homeassistant_config.sh --reset-dashboard
docker compose up -d --build
```

Then configure MQTT in Home Assistant:

```text
Settings -> Devices & services -> Add integration -> MQTT
Broker: 127.0.0.1
Port: 1883
```

LabPulse services publish MQTT discovery. Home Assistant creates stable entities
such as:

```text
sensor.labpulse_pressure_monitor_pressure
sensor.labpulse_pressure_monitor_status
binary_sensor.labpulse_pressure_monitor_pressure_alarm
```

After first setup, edit the dashboard in the Home Assistant UI.

## Day-To-Day Workflow

After the dashboard has been seeded and edited:

```bash
cd ~/labpulse-ha
nano config.yaml
./generate_compose.sh
./generate_homeassistant_config.sh
docker compose up -d --build
```

Then add/rearrange any new entities in the Home Assistant UI as needed.

Use backup/load/reset dashboard commands only when deliberately managing the
editable dashboard state.

## Entity Map

Generate `homeassistant/config/labpulse_entity_map.yaml` on every run. It should
be a human-readable debug file that maps each service/reading to generated IDs:

```yaml
pressure_monitor:
  status:
    mqtt_unique_id: labpulse_pressure_monitor_status
    expected_entity_id: sensor.labpulse_pressure_monitor_status
  pressure:
    mqtt_unique_id: labpulse_pressure_monitor_pressure
    expected_entity_id: sensor.labpulse_pressure_monitor_pressure
    alarm_entity_id: binary_sensor.labpulse_pressure_monitor_pressure_alarm
    active_alert: input_boolean.labpulse_pressure_monitor_pressure_alert_active
    minimum_threshold: input_number.labpulse_pressure_monitor_pressure_minimum_threshold
    maximum_threshold: input_number.labpulse_pressure_monitor_pressure_maximum_threshold
    alert_delay: input_number.labpulse_pressure_monitor_alert_delay_seconds
    recovery_delay: input_number.labpulse_pressure_monitor_recovery_delay_seconds
```

This file is for debugging dashboard/entity problems. It should not be required
as an input to Home Assistant.

## Implementation Checklist

1. Update MQTT discovery IDs in `labpulse_common/homeassistant_mqtt.py`.
2. Replace the current dictionary-heavy Home Assistant generator with a render
   model and templates.
3. Generate `labpulse_generated.yaml` from `package.yaml.j2` and
   `alarm_logic.yaml`.
4. Generate `labpulse_entity_map.yaml` from `entity_map.yaml.j2`.
5. Generate `.storage/lovelace` from `dashboard_seed.yaml` wrapped by
   `initial_lovelace.json.j2` only for `--reset-dashboard`.
6. Replace current dashboard flags with:
   - `--reset-dashboard`
   - `--backup-dashboard`
   - `--load-dashboard`
7. Enforce dashboard flag conflicts.
8. Update setup/docs to use `--reset-dashboard` for first setup.
9. Add/update lightweight tests for:
   - stable MQTT `unique_id` and `object_id`
   - render model naming
   - generated package contents
   - no-flag dashboard preservation
   - reset/backup/load dashboard behavior
   - conflicting flag errors

## Non-Goals

- No backwards compatibility for old generated files.
- No aliases for old flag names unless explicitly requested.
- No support for old friendly/entity-prefix fallback dashboard IDs.
- No automatic dashboard backup during reset.
- No day-to-day writes to `.storage/lovelace`.
