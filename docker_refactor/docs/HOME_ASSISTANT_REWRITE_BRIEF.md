# Home Assistant Generator Internals

This file used to be a rewrite brief. It now documents the current generator
implementation.

For day-to-day dashboard and automation editing, read:

```text
HOME_ASSISTANT_DASHBOARDS_AND_AUTOMATIONS.md
```

## Generator Goal

The Home Assistant generator connects `config.yaml` to Home Assistant files.
It does not replace Home Assistant as the operator UI.

The generator owns:

- stable entity/helper ID prediction
- generated Home Assistant package YAML
- generated entity map
- default `configuration.yaml`
- starter dashboard creation when explicitly reset

Home Assistant owns:

- live dashboard edits
- helper state values
- MQTT integration setup
- users and auth
- history/logbook data

## Entry Point

Shell wrapper:

```text
generate_homeassistant_config.sh
```

Python entry point:

```text
labpulse_homeassistant/cli.py
```

Flow:

```text
generate_homeassistant_config.sh
  -> parse dashboard flags
  -> optionally back up dashboard
  -> optionally load dashboard backup
  -> check config directory is writable
  -> python3 -m labpulse_homeassistant
    -> generator.parse_args()
    -> labpulse_common.config.load_config()
    -> model.build_render_model()
    -> render.render_core()
    -> alarm.render_alarm()
    -> dashboard.render_dashboard()
```

## Package Files

```text
labpulse_homeassistant/
  __main__.py
  cli.py
  data_models.py
  write_yaml.py
  dashboard.py
  alarm.py
  template_utils.py
  templates/
    core/
      configuration.yaml.j2
      entity_map.yaml.j2
    alarm/
      package.yaml.j2
      alarm_logic.yaml
    dashboard/
      initial_lovelace.json.j2
      dashboard_seed.yaml
```

## Model Layer

`data_models.py` converts the shared validated `LabPulseConfig` into Home
Assistant-specific render dataclasses:

```text
GeneratorPaths
ThresholdModel
ReadingModel
ServiceModel
RenderModel
```

The model layer owns:

- slugging service and reading keys
- sorting enabled services by display order
- deriving stable IDs
- deriving expected Home Assistant entity IDs
- inferring default threshold helper values
- creating template-friendly objects

It does not own Home Assistant YAML layout. That belongs to templates.

## Stable IDs

For service `pressure_monitor` and reading `pressure`:

```text
stable ID:
  labpulse_pressure_monitor_pressure

sensor:
  sensor.labpulse_pressure_monitor_pressure

alarm:
  binary_sensor.labpulse_pressure_monitor_pressure_alarm

minimum helper:
  input_number.labpulse_pressure_monitor_pressure_minimum_threshold

maximum helper:
  input_number.labpulse_pressure_monitor_pressure_maximum_threshold

active-alert memory:
  input_boolean.labpulse_pressure_monitor_pressure_alert_active
```

The MQTT publisher must generate matching IDs in:

```text
labpulse_hardware/homeassistant_publisher.py
```

If these two sides drift, dashboards and automations will point at entities
that Home Assistant does not create.

## Render Layer

`write_yaml.py` writes:

```text
configuration.yaml
labpulse_entity_map.yaml
```

It also ensures these files exist:

```text
automations.yaml
scripts.yaml
scenes.yaml
```

Those files are managed by Home Assistant's UI editors, so the generator never
overwrites them after creation.

`dashboard.py` writes `.storage/lovelace` only when its `reset_dashboard`
argument is true. `alarm.py` writes
`packages/labpulse_generated.yaml`.

## Dashboard Layer

`dashboard.py` loads:

```text
templates/dashboard/dashboard_seed.yaml
```

It creates one Home Assistant `sections` dashboard view with:

- system health section
- one service section per enabled service
- status tiles
- reading tiles
- alarm tiles
- optional alarm settings cards
- optional alert memory cards

It uses `template_utils.expand_template()` to replace placeholders such as:

```text
[[ service.section ]]
[[ service.status_entity_id ]]
[[ reading.expected_entity_id ]]
[[ reading.alarm_entity_id ]]
```

## Alarm Layer

`alarm.py` loads:

```text
templates/alarm/alarm_logic.yaml
```

It expands seed items over services and readings, then renders package sections:

```yaml
input_number:
input_boolean:
template:
automation:
```

Every reading gets a min/max range alarm and an active-alert memory boolean.
The memory boolean allows recovery notifications to fire only after an alert
has previously fired.

## Template Expansion

`template_utils.py` expands placeholders recursively through dictionaries,
lists, keys, and string values.

Supported placeholder roots:

```text
[[ service.... ]]
[[ reading.... ]]
```

The expander deliberately leaves Home Assistant Jinja intact:

```yaml
{{ states('sensor.example') }}
```

This is why the seed files can contain both LabPulse placeholders and Home
Assistant Jinja templates.

## Command Modes

Normal:

```bash
./generate_homeassistant_config.sh
```

Preserves dashboard and regenerates generated YAML.

Reset:

```bash
./generate_homeassistant_config.sh --reset-dashboard
```

Replaces `.storage/lovelace` with the generated starter dashboard.

Backup:

```bash
./generate_homeassistant_config.sh --backup-dashboard
```

Copies current `.storage/lovelace` into `homeassistant_backups/`.

Load:

```bash
./generate_homeassistant_config.sh --load-dashboard
```

Restores `homeassistant_backups/dashboard-latest/lovelace`.

## Tests To Update When Editing

When changing generator behavior, check:

```text
testing/test_homeassistant_generator.py
testing/test_homeassistant_entities.py
testing/test_homeassistant_publisher.py
```

Use tests as executable contracts for:

- stable entity IDs
- generated package contents
- dashboard reset behavior
- dashboard preservation behavior
- backup/load flag behavior
- MQTT discovery payloads
