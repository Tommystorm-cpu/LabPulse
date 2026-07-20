# Home Assistant Generator Package

`labpulse_homeassistant` converts the validated LabPulse config into Home
Assistant core configuration, alarm helpers/automations, a diagnostic entity
map, and the registered YAML-mode LabPulse dashboard.

For the full execution path, render models, placeholders, dashboard behavior,
and alarm state machine, read
[Code internals](../docs/CODE_INTERNALS.md#home-assistant-generator).

## Public entry point

Operators use the wrapper from the live `~/labpulse-ha` directory:

```bash
./generate_homeassistant_config.sh
```

The wrapper handles paths and generated-file permissions before invoking:

```bash
python3 -m labpulse_homeassistant
```

## Package map

```text
__main__.py
  package entry point

cli.py
  load config, build the canonical inventory/model, orchestrate outputs

models.py
  RenderModel, ServiceModel, ReadingModel, MqttEntity, and ThresholdModel

model_builder.py
  config/inventory normalization, stable generated IDs, and threshold bounds

paths.py
  GeneratorPaths and all generated output locations

write_yaml.py
  configuration.yaml, entity map, and preservation of UI-owned YAML files

alarm.py
  expand alarm seed rules into the generated Home Assistant package

yaml_dashboard.py
  render the active Monitor, Alarm Setup, and Diagnostics YAML dashboard

template_utils.py
  recursive LabPulse placeholder expansion and output-file writes

../labpulse_common/sms_templates.yaml
  shared alert, formatting, and subscription-command SMS wording

templates/core/
  outer core/entity-map templates

templates/alarm/
  package shell and editable alarm_logic.yaml seed

templates/dashboard/
  reusable native-card fragments in cards.yaml
```

## Delimiter rule

```text
[[ ... ]]     expanded by LabPulse Python during generation
{{ ... }}     evaluated by Home Assistant at runtime
{% ... %}     evaluated by Home Assistant at runtime
```

Do not replace Home Assistant Jinja delimiters with LabPulse placeholders.

## Dashboard behavior

Normal generation replaces `homeassistant/config/labpulse-dashboard.yaml`.
Home Assistant registers it as the YAML-mode
`labpulse-monitor` dashboard through generated `configuration.yaml`. Layout
changes therefore belong in config, dashboard code, or templates rather than
the Home Assistant UI. There is no storage-backed dashboard fallback, backup,
restore, reset, or entity-synchronization mode.

Monitor and Alarm Setup use explicit logical setup projections; Diagnostics
uses physical service ownership. Alarm timing belongs to each reading. The
generated Bulk Timing script can copy its three timing values to all ordinary
readings or one setup after dashboard confirmation. Dedicated power telemetry
does not participate in setup grouping.

## Primary editing points

- Change alarm helpers, zones, transitions, or notifications in
  `templates/alarm/alarm_logic.yaml`.
- Change every user-facing SMS title/message in
  `../labpulse_common/sms_templates.yaml`.
- Change dashboard projection and assembly in `yaml_dashboard.py`.
- Change reusable dashboard fragments in `templates/dashboard/`.
- Change render types in `models.py` and construction/defaults in
  `model_builder.py`.
- Change output assembly only in the owning renderer.

Run `testing/test_homeassistant_entities.py` and
`testing/test_homeassistant_generator.py`, plus
`testing/test_yaml_dashboard.py` and `testing/test_notification_context.py`,
after changes.
