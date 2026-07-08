# LabPulse Home Assistant Generator

This package generates the Home Assistant side of LabPulse from the live
`~/labpulse-ha/config.yaml` file.

The normal user command is still the shell wrapper:

```bash
./generate_homeassistant_config.sh
```

That wrapper handles shell-level tasks such as backup, restore, fresh wipes,
and path setup. It then runs:

```bash
python3 -m labpulse_homeassistant.generator
```

## File Map

`generator.py`

Coordinates the generation flow. It does not build YAML itself. It calls the
other modules in order: read config, read Home Assistant entity registry, build
the generated structures, then write files.

`config_io.py`

Reads command-line arguments passed by `generate_homeassistant_config.sh` and
loads the LabPulse YAML config.

`models.py`

Defines shared data containers:

- `GeneratorPaths`: all filesystem paths used by the generator.
- `GeneratorOptions`: flags such as fresh Home Assistant and dashboard refresh.
- `EntityRegistry`: Home Assistant MQTT entity lookup data.
- `ReadingContext`: generated names and entity IDs for one sensor reading.
- `GeneratedConfig`: in-memory Home Assistant helpers, automations, and cards.

`entities.py`

Reads Home Assistant's `.storage/core.entity_registry` file and finds the real
MQTT entity IDs that Home Assistant created. This prevents the dashboard from
guessing wrong entity names when MQTT discovery has already run.

`readings.py`

Defines reading defaults and threshold helpers. This is where parser readings
such as pressure, flow, and temperature get default units, threshold modes, and
Home Assistant `input_number` helper definitions.

`automations.py`

Builds the Home Assistant alert and recovery automations. It owns the template
conditions, alert/recovery notification messages, and active-alert boolean
behavior.

`dashboard.py`

Builds dashboard cards and dashboard sections. It owns tiles, heading cards,
alarm settings cards, and the section names/icons such as Pump Room,
Cryogenics, and Air Pressure.

`builder.py`

Turns enabled services from `config.yaml` into one complete `GeneratedConfig`.
This module connects the pieces together for each service: status tile, reading
tiles, threshold helpers, alert booleans, automations, and alarm setting cards.

`writer.py`

Writes the generated files into the Home Assistant config directory:

- `configuration.yaml`
- `packages/labpulse_thresholds.yaml`
- `labpulse_alarm_cards.yaml`
- `.storage/lovelace`

It also preserves the editable dashboard unless the user requested a fresh
Home Assistant setup or dashboard refresh.

`naming.py`

Small shared helpers for converting config names into safe slugs and readable
titles.

`__init__.py`

Marks this folder as a Python package.

## Generation Flow

```text
generate_homeassistant_config.sh
  -> python3 -m labpulse_homeassistant.generator
    -> config_io.parse_args()
    -> config_io.load_labpulse_config()
    -> entities.load_entity_registry()
    -> builder.build_generated_config()
      -> readings.configured_readings()
      -> entities.status_entity_id()
      -> readings.build_reading_context()
      -> readings.make_threshold_entities()
      -> automations.make_alert_automation()
      -> automations.make_recovery_automation()
      -> dashboard.make_sensor_section()
    -> writer.write_generated_files()
```

## Source Of Truth

The generator reads sensor/service definitions from:

```text
~/labpulse-ha/config.yaml
```

The repo copy at `docker_refactor/config.yaml` is only the starter template.

## Design Rule

Python services publish MQTT readings and health. Home Assistant owns dashboard
layout, thresholds, alert state, and local user-facing notifications.
