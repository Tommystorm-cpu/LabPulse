# LabPulse Home Assistant Generator

This package generates the Home Assistant side of LabPulse from the live
`~/labpulse-ha/config.yaml` file.

For the full dashboard and automation editing guide, read:

```text
docker_refactor/docs/HOME_ASSISTANT_DASHBOARDS_AND_AUTOMATIONS.md
```

The normal user command is the shell wrapper:

```bash
./generate_homeassistant_config.sh
```

That wrapper handles dashboard backup/load/reset flags and path setup. It then
runs:

```bash
python3 -m labpulse_homeassistant.generator
```

## File Map

`generator.py`

Coordinates the generation flow: read config, normalize the render model, and
render files.

`config_io.py`

Reads command-line arguments passed by `generate_homeassistant_config.sh` and
loads the LabPulse YAML config.

`model.py`

Defines the normalized render model: services, readings, default helper ranges,
stable `labpulse_*` entity IDs, and generated helper IDs.

`render.py`

Renders template files and writes:

- `configuration.yaml`
- `packages/labpulse_generated.yaml`
- `labpulse_entity_map.yaml`
- `.storage/lovelace` only when `--reset-dashboard` is used

`dashboard.py`

Expands the editable dashboard seed YAML over the enabled services/readings and
returns the Lovelace storage document used by `--reset-dashboard`.

`alarm.py`

Expands the editable alarm logic seed YAML over the enabled services/readings
and returns the generated package sections for helpers, template binary sensors,
and automations.

`template_utils.py`

Expands placeholders such as `{service.label}` and `{reading.alarm_entity_id}`
inside editable seed YAML files. Home Assistant Jinja like `{{ states(...) }}`
is left intact.

`templates/`

Contains the readable Home Assistant artifacts:

- `configuration.yaml.j2`
- `package.yaml.j2`
- `entity_map.yaml.j2`
- `initial_lovelace.json.j2`
- `dashboard_seed.yaml`
- `alarm_logic.yaml`

`dashboard_seed.yaml` is the file to edit when changing the initial dashboard
layout created by `--reset-dashboard`. It contains card templates such as the
system-health section, per-service heading/status tiles, reading/alarm tile
rules, alarm settings cards, and the optional alert-memory card. The Python
code only expands placeholders such as `{service.section}` and
`{reading.expected_entity_id}`.

`alarm_logic.yaml` is the file to edit when changing generated alarm behavior.
It contains the seed rules for threshold helpers, alert-memory booleans,
template alarm binary sensors, and alert/recovery automations. Future features
such as mute controls, re-arm timers, trigger-reset deadbands, or alternate
notification services should usually start as edits to this YAML file.

`__init__.py`

Marks this folder as a Python package.

## Generation Flow

```text
generate_homeassistant_config.sh
  -> python3 -m labpulse_homeassistant.generator
    -> config_io.parse_args()
    -> config_io.load_labpulse_config()
    -> model.build_render_model()
    -> render.render_all()
      -> alarm.package_context()
      -> dashboard.lovelace_document() only for --reset-dashboard
```

## Dashboard Flags

Normal generation preserves the editable Home Assistant dashboard:

```bash
./generate_homeassistant_config.sh
```

Use `--reset-dashboard` to create or replace `.storage/lovelace` with the
generated starter dashboard:

```bash
./generate_homeassistant_config.sh --reset-dashboard
```

Use `--backup-dashboard` and `--load-dashboard` to save and restore the editable
dashboard. The script rejects ambiguous combinations such as
`--reset-dashboard --load-dashboard`.

## Source Of Truth

The generator reads sensor/service definitions from:

```text
~/labpulse-ha/config.yaml
```

The repo copy at `docker_refactor/config.yaml` is only the starter template.

Keep `config.yaml` focused on hardware, labels, and display metadata. Alarm
threshold values and delays are Home Assistant helpers, so they are edited from
the dashboard after generation.

## Design Rule

Python services publish MQTT readings and health with stable `labpulse_*`
`unique_id`, `object_id`, and `default_entity_id` discovery values. Home
Assistant owns dashboard layout, thresholds, template alarm binary sensors, and
local user-facing notifications.

Every reading gets the same Home Assistant alarm shape: a minimum threshold, a
maximum threshold, and a range-check binary sensor. Readings that are mostly
"minimum only", such as pressure or flow, use a high default maximum that can be
edited or ignored in Home Assistant.

Each generated reading has a template alarm binary sensor and an input boolean
that remembers whether an alert has already fired. Recovery automations require
that boolean to be on before sending a recovery notification, which prevents
healthy startup states from producing recovery spam. The starter dashboard keeps
those booleans in a separate `Alert Memory` card for easy removal.
