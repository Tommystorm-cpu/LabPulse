# Home Assistant templates

These Jinja templates render native Home Assistant YAML. LabPulse uses
`[% ... %]` for statements and `[[ ... ]]` for values so Home Assistant's
later `{% ... %}` and `{{ ... }}` expressions survive generation.

| Path | Behaviour |
|---|---|
| `configuration.yaml.j2` | Enable packages, UI files and generated dashboard |
| `dashboard.yaml.j2` | Assemble dashboard views |
| `dashboard/` | Monitor, diagnostics, alarm setup and setup/power/custom views |
| `dashboard/alarm_setup/` | Bulk editor, targets and notification controls |
| `dashboard/setup_subviews/` | Setup headings and measurement cards |
| `alarm/alarm_package.yaml.j2` | Assemble the alarm package |
| `alarm/helpers.yaml.j2` | Persistent settings and state helpers |
| `alarm/derived_entities.yaml.j2` | Availability, dangerous-value and history entities |
| `alarm/scripts.yaml.j2` | Bulk editing and central incident notification scripts |
| `alarm/automations/` | Installation, measurement, service, custom and power state machines |

Measurement alarms require enough dangerous history to enter Danger and
continuous safe recovery beyond deadband to return to Normal. Reading
availability and service health are separate. Power has an outage/restoration
lifecycle. Mutes suppress delivery, not state calculation; Test mode selects
test recipients.

Templates consume prepared records from `alarm.py`. Keep identity and grouping
in the render model but recognizable Home Assistant behaviour in final-shaped
YAML. Never access hardware, files or MQTT here or manage `.storage`.

Render and parse representative output after changes and update focused tests.
See the package [README](../README.md), [User Guide](../../../../docs/USER_GUIDE.md)
and [Development](../../../../docs/DEVELOPMENT.md).
