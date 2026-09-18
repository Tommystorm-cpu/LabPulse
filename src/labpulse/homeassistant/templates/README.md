# Home Assistant templates

These Jinja templates render native Home Assistant YAML. LabPulse uses
`[% ... %]` for statements and `[[ ... ]]` for values so Home Assistant's
later `{% ... %}` and `{{ ... }}` expressions survive generation.

| Path | Behaviour |
|---|---|
| `configuration.yaml.j2` | Enable packages, UI files and generated dashboard |
| `dashboard.yaml.j2` | Assemble dashboard views |
| `dashboard/` | Monitor, System Status, alarm setup and setup/power/custom views |
| `dashboard/alarm_setup/` | Bulk editor, targets and notification controls |
| `dashboard/setup_subviews/` | Setup headings and measurement cards |
| `alarm/alarm_package.yaml.j2` | Assemble the alarm package |
| `alarm/helpers.yaml.j2` | Persistent settings and state helpers |
| `alarm/derived_entities.yaml.j2` | Reading-presence, dangerous-value and history entities |
| `alarm/scripts.yaml.j2` | Bulk editing and central incident notification scripts |
| `alarm/automations/` | Installation, measurement, service, custom and power state machines |

Measurement alarms require enough dangerous history to enter Danger and
continuous safe recovery beyond deadband to return to Normal. Missing
readings and service health are separate. Power has an outage/restoration
lifecycle. Mutes suppress delivery, not state calculation; Test mode selects
test recipients.

Templates consume prepared records from `alarm.py`. Keep identity and grouping
in the render model but recognizable Home Assistant behaviour in final-shaped
YAML. Rendering must not access hardware or make network calls. The generated
YAML deliberately includes MQTT actions which Home Assistant executes later,
such as publishing an SMS request. Do not manage `.storage` here.

## Two passes through Jinja

Jinja inserts values into text. LabPulse runs the first pass during generation;
Home Assistant evaluates the remaining expressions while the system runs.
For a record whose entity ID is `sensor.labpulse_pressure_monitor_pressure`:

```jinja
{{ states('[[ measurement.entity_id ]]') | float(0) }}
```

LabPulse produces:

```jinja
{{ states('sensor.labpulse_pressure_monitor_pressure') | float(0) }}
```

Home Assistant later reads that entity's current value. Generation did not
sample the pressure. `[[ ... ]]` and `[% ... %]` are LabPulse expressions and
statements; `{{ ... }}` and `{% ... %}` survive for Home Assistant. `{# ... #}`
comments are removed during generation. `yaml_scalar` quotes inserted values
where needed so labels do not accidentally become YAML syntax.

## Follow an alarm through the templates

Read [`alarm_package.yaml.j2`](alarm/alarm_package.yaml.j2) for the include
order, then follow these pieces:

1. [`helpers.yaml.j2`](alarm/helpers.yaml.j2) declares thresholds, timing,
   alarm state and separate notification/SMS-request flags.
2. [`derived_entities.yaml.j2`](alarm/derived_entities.yaml.j2) turns live
   readings and settings into availability, danger-history and recovery checks.
3. [`measurement_state.yaml.j2`](alarm/automations/measurement_state.yaml.j2)
   uses those checks to enter Danger or recover. Natural triggers respond to
   the condition becoming true; startup reevaluates it after restart; resend
   asks to repeat an already active warning. Source-service outages block the
   danger path. Recovery requires a continuously safe interval.
4. [`scripts.yaml.j2`](alarm/scripts.yaml.j2) decides whether to create a
   persistent notification or publish an SMS request. Mutes gate delivery;
   the caller owns alarm state. Separate flags remember what was requested,
   so opening a dashboard notification is not mistaken for sending an SMS.
5. Closing an incident dismisses its problem even while muted. Recovery
   notification/SMS eligibility depends on the corresponding opening flag and
   current mutes. These flags do not acknowledge delivery to a phone.

[`service_health.yaml.j2`](alarm/automations/service_health.yaml.j2) handles
source outages separately, suppressing subordinate missing-reading incidents.
Power and missing-reading templates have their own confirmation/recovery paths.
For a change, inspect the generated YAML and the owning tests, then use a real
Home Assistant instance to check timing; parsing alone cannot exercise it.

Render and parse representative output after changes and update focused tests.
See the package [README](../README.md), [User Guide](../../../../docs/USER_GUIDE.md)
and [Development](../../../../docs/DEVELOPMENT.md).
