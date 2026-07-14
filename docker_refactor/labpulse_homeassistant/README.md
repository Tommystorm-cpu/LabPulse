# Home Assistant Generator Package

`labpulse_homeassistant` converts the validated LabPulse config into Home
Assistant core configuration, alarm helpers/automations, a diagnostic entity
map, and an optional starter dashboard.

For the full execution path, render models, placeholders, entity resolution,
dashboard behavior, and alarm state machine, read
[Code internals](../docs/CODE_INTERNALS.md#home-assistant-generator).

## Public entry point

Operators use the wrapper from the live `~/labpulse-ha` directory:

```bash
./generate_homeassistant_config.sh
```

The wrapper handles paths, permissions, dashboard backup/restore/reset, and
optional registry access before invoking:

```bash
python3 -m labpulse_homeassistant
```

## Package map

```text
__main__.py
  package entry point

cli.py
  load config, build model, optionally resolve registry, orchestrate outputs

data_models.py
  RenderModel, ServiceModel, ReadingModel, EntityReference, ThresholdModel,
  GeneratorPaths, stable generated IDs, and threshold defaults

write_yaml.py
  configuration.yaml, entity map, and preservation of UI-owned YAML files

alarm.py
  expand alarm seed rules into the generated Home Assistant package

dashboard.py
  create/reset starter Lovelace storage or surgically synchronize entity IDs

entity_registry.py
  query Home Assistant by (platform, unique_id) and overlay actual entity IDs

template_utils.py
  recursive [[ service... ]]/[[ reading... ]] expansion and output-file writes

templates/core/
  outer core/entity-map templates

templates/alarm/
  package shell and editable alarm_logic.yaml seed

templates/dashboard/
  Lovelace shell and editable dashboard_seed.yaml seed
```

## Delimiter rule

```text
[[ ... ]]     expanded by LabPulse Python during generation
{{ ... }}     evaluated by Home Assistant at runtime
{% ... %}     evaluated by Home Assistant at runtime
```

Do not replace Home Assistant Jinja delimiters with LabPulse placeholders.

## Dashboard behavior

Normal generation preserves the active Overview store resolved through
`.storage/lovelace_dashboards` (or legacy `.storage/lovelace`). Use
`--reset-dashboard` only to intentionally replace it from
`templates/dashboard/dashboard_seed.yaml`. Backup, restore, entity-resolution,
and synchronization commands are documented in
[Setup and troubleshooting](../docs/SETUP_AND_TROUBLESHOOTING.md#dashboard-safety-and-commands).

## Primary editing points

- Change alarm helpers, zones, transitions, or notifications in
  `templates/alarm/alarm_logic.yaml`.
- Change the reset-dashboard structure in
  `templates/dashboard/dashboard_seed.yaml`.
- Change entity modelling/defaults in `data_models.py`.
- Change output assembly only in the owning renderer.

Run `testing/test_homeassistant_entities.py` and
`testing/test_homeassistant_generator.py` after changes.
