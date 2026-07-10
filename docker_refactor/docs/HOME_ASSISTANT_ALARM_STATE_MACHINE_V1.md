# Home Assistant Alarm State Machine V1

This document defines the first advanced LabPulse alarm model to implement in
Home Assistant.

The goal is to replace the current simple threshold alarm logic with a clearer,
more robust state machine while keeping the system understandable and editable
from the native Home Assistant UI.

## Design Goals

- Keep `config.yaml` focused on hardware, service names, reading names, labels,
  units, and display hints.
- Keep alarm state and alarm tuning in Home Assistant.
- Use native Home Assistant helpers, sensors, automations, and dashboard cards.
- Avoid custom Lovelace cards for v1.
- Avoid a separate alarm policy JSON/YAML file for v1.
- Avoid Critical alarm level for v1.
- Make the main dashboard easy to read.
- Put noisier tuning controls on a separate Alarm Setup view.
- Support per-reading alarm mute.
- Suppress notifications while muted, but keep calculating and displaying alarm
  state.
- Replace the old simple alarm logic completely. No backwards compatibility is
  required.

## State Model

Each generated reading has one alarm state:

```text
Normal
Danger
Sensor Fault
```

The current state is stored in a Home Assistant `input_select`:

```text
input_select.labpulse_<service>_<reading>_alarm_state
```

Example:

```text
input_select.labpulse_pressure_monitor_pressure_alarm_state
```

The state machine is per reading. A service with six readings gets six alarm
state helpers.

## Alarm Modes

Each reading has an editable alarm mode helper:

```text
input_select.labpulse_<service>_<reading>_alarm_mode
```

Options:

```text
Disabled
Low Only
High Only
Range
```

Meaning:

- `Disabled`: reading never enters Danger due to thresholds. It can still enter
  Sensor Fault if its data is missing, stale, unavailable, or nonsensical.
- `Low Only`: values below the minimum threshold are dangerous.
- `High Only`: values above the maximum threshold are dangerous.
- `Range`: values below the minimum or above the maximum are dangerous.

Default inference can be generated from reading names:

- `flow*`: `Low Only`
- `pressure*`: `Low Only`
- `temp*`: `Range`
- `hum*`: `Range`
- unknown/generic readings: `Range`

The user can change the mode in Home Assistant.

## Threshold Helpers

Each reading has editable min/max helpers and a recovery deadband helper:

```text
input_number.labpulse_<service>_<reading>_minimum_threshold
input_number.labpulse_<service>_<reading>_maximum_threshold
input_number.labpulse_<service>_<reading>_recovery_deadband
```

These are the user-facing alarm thresholds.

They are created from generated defaults based on reading name and unit, but
after generation the user tunes them in Home Assistant.

The implementation should avoid moving alarm threshold values back into
`config.yaml`.

## Mute Helper

Each reading has a mute toggle:

```text
input_boolean.labpulse_<service>_<reading>_alarm_muted
```

Mute semantics:

- Mute suppresses notifications and SMS for that reading.
- Mute does not stop state calculation.
- Mute does not hide Danger or Sensor Fault on the dashboard.
- Mute does not reset the alarm state.
- If a reading becomes dangerous while muted, no alert is sent.
- If the reading is still dangerous when unmuted, no retroactive alert is sent.
- After unmuting, the next state transition can notify normally.

This is Option A from the design discussion: no retroactive alert when unmuting.

## Zone Sensors

For each reading, generate template binary sensors that classify the current
reading.

### Danger Zone

```text
binary_sensor.labpulse_<service>_<reading>_danger_zone
```

This is `on` when the current numeric reading is outside the allowed threshold
range according to the selected alarm mode.

Rules:

```text
Disabled:
  danger_zone = off

Low Only:
  danger_zone = reading < minimum_threshold

High Only:
  danger_zone = reading > maximum_threshold

Range:
  danger_zone = reading < minimum_threshold
             or reading > maximum_threshold
```

If the source sensor is unknown, unavailable, missing, or non-numeric, the
danger zone should be `off`; sensor fault logic handles that case separately.

### Recovery Zone

```text
binary_sensor.labpulse_<service>_<reading>_recovery_zone
```

This is `on` when the current numeric reading is safely inside the allowed
range according to the selected alarm mode.

Rules:

```text
Disabled:
  recovery_zone = on if source reading is valid

Low Only:
  recovery_zone = reading >= minimum_threshold + recovery_deadband

High Only:
  recovery_zone = reading <= maximum_threshold - recovery_deadband

Range:
  recovery_zone = minimum_threshold + recovery_deadband <= reading
              and reading <= maximum_threshold - recovery_deadband
```

The recovery deadband prevents a reading that hovers near the danger threshold
from immediately recovering and re-triggering. The deadband is an editable
per-reading Home Assistant helper with the same unit as the reading.

### Sensor Fault Zone

```text
binary_sensor.labpulse_<service>_<reading>_sensor_fault_zone
```

This is `on` when the reading is not trustworthy.

Sensor fault should include:

- source entity is `unknown`
- source entity is `unavailable`
- source entity is missing
- source value is non-numeric
- reading is stale
- service status indicates disconnected/reconnecting/error if that signal is available

Stale detection should be implemented with Home Assistant-native logic. A
practical v1 approach is to use the source sensor's `last_changed` or
`last_updated` in a template and compare it with a stale timeout helper.

## Timing And Filtering

Danger entry uses rolling history percentage filtering.

Recovery uses Home Assistant's `for:` behavior.

### Per-Service Timing Helpers

To avoid clutter, timing controls are generated per service rather than per
reading:

```text
input_number.labpulse_<service>_danger_ratio_percent
input_number.labpulse_<service>_danger_window_seconds
input_number.labpulse_<service>_recovery_seconds
input_number.labpulse_<service>_stale_timeout_seconds
```

Suggested defaults:

```text
danger_ratio_percent: 70
danger_window_seconds: 120
recovery_seconds: 120
stale_timeout_seconds: 300
```

These helpers can be placed on the Alarm Setup view, grouped by service.

### Danger History Sensor

For each reading, generate a `history_stats` sensor:

```text
sensor.labpulse_<service>_<reading>_danger_ratio
```

This tracks the percentage of the recent window where the danger zone was `on`.

Use `type: ratio`.

The official Home Assistant `history_stats` integration supports `ratio`, and
supports templated `start` and `end`. Its `duration` field is a time period, not
a template. Therefore the editable window should be implemented using templated
`start` and `end`, not templated `duration`.

Example shape:

```yaml
- platform: history_stats
  name: LabPulse Pressure Danger Ratio
  entity_id: binary_sensor.labpulse_pressure_monitor_pressure_danger_zone
  state: "on"
  type: ratio
  start: >
    {{ now() - timedelta(seconds=states('input_number.labpulse_pressure_monitor_danger_window_seconds')|int(120)) }}
  end: "{{ now() }}"
```

Notes:

- `history_stats` updates when the source entity changes, or once per minute if
  there is no source change.
- This is suitable for a two-minute Danger window.
- If future short windows are introduced, update frequency must be tested.

### Normal To Danger

Transition from `Normal` to `Danger` when:

```text
danger_ratio >= service danger_ratio_percent
```

and:

```text
alarm state is Normal
sensor fault zone is off
alarm mode is not Disabled
```

Notification:

```text
Warning
```

Only send if mute is off.

### Danger To Normal

Transition from `Danger` to `Normal` when:

```text
recovery_zone is continuously on for service recovery_seconds
```

Use a Home Assistant template/state trigger with a templated `for:` value.

Home Assistant supports templated `for:` values in template triggers. The
template is evaluated when the trigger first becomes true.

Notification:

```text
Recovery
```

Only send if mute is off.

Note: Home Assistant `for:` waits do not survive Home Assistant restart or
automation reload. This is acceptable for v1 and should be documented.

### Any To Sensor Fault

Transition from any state to `Sensor Fault` when:

```text
sensor_fault_zone is on
```

Notification:

```text
Sensor Fault
```

Only send if mute is off.

### Sensor Fault Clear

When sensor fault clears, do not blindly return to Normal.

Instead, recalculate based on current conditions:

```text
if danger_ratio >= service danger_ratio_percent:
  Sensor Fault -> Danger
else if recovery_zone is on:
  Sensor Fault -> Normal
else:
  remain Sensor Fault or wait for next clear/check event
```

Notifications:

- `Sensor Fault -> Danger`: no per-reading notification in v1.
- `Sensor Fault -> Normal`: no per-reading notification in v1.

Sensor fault clear is intentionally silent per reading. A hub unplug/replug can
clear many reading faults at the same time, and per-reading restored
notifications are too noisy. The dashboard state still updates visibly. A later
implementation can add one aggregated hub-level restored notification if needed.

## Notification Rules

Notifications fire on state transitions only.

V1 notification events:

```text
Normal -> Danger:
  Warning

Danger -> Normal:
  Recovery

Any -> Sensor Fault:
  Sensor Fault

Sensor Fault -> Danger:
  No per-reading notification in v1

Sensor Fault -> Normal:
  No per-reading notification in v1
```

Notifications should publish to the existing SMS MQTT topic:

```text
labpulse/sms/send
```

The payload should include at least:

```json
{
  "event": "warning",
  "service": "pressure_monitor",
  "service_label": "Air Pressure Sensor Hub",
  "reading": "pressure",
  "reading_label": "Pressure",
  "entity_id": "input_select.labpulse_pressure_monitor_pressure_alarm_state",
  "state": "Danger",
  "title": "LabPulse warning",
  "message": "Air Pressure Sensor Hub / Pressure is in Danger."
}
```

Existing SMS backend behavior can remain:

- `sms.backend: "log"` logs messages on test systems.
- `sms.backend: "mmcli"` sends real SMS on the modem Pi.

## Dashboard Design

Use native Home Assistant dashboard cards only.

V1 should generate or seed two views:

```text
LabPulse Monitor
LabPulse Alarm Setup
```

### LabPulse Monitor View

This is the day-to-day operator view.

Show:

- service sections
- current readings
- current alarm state
- service status
- mute indicator if practical

Avoid showing all advanced tuning controls here.

### LabPulse Alarm Setup View

This is the configuration/tuning view.

Group by service.

Each service section includes a native `Show controls` toggle. The service
timing card and each reading setup card are native conditional cards that appear
only while that toggle is on. This gives a collapsible working shape without
depending on custom Lovelace cards.

For each service, show service-level timing helpers:

```text
danger_ratio_percent
danger_window_seconds
recovery_seconds
stale_timeout_seconds
```

For each reading, show reading-level controls:

```text
alarm_state
alarm_mode
alarm_muted
minimum_threshold
maximum_threshold
recovery_deadband
danger_ratio sensor
danger_zone
recovery_zone
sensor_fault_zone
```

Because native Home Assistant cards may not provide true collapsible sections
without custom cards, v1 uses a native helper plus conditional cards. Users can
still manually rearrange or remove cards in Home Assistant.

Do not depend on custom cards for v1.

## Generated Entity Summary

Per service:

```text
input_boolean.labpulse_<service>_alarm_controls_expanded
input_number.labpulse_<service>_danger_ratio_percent
input_number.labpulse_<service>_danger_window_seconds
input_number.labpulse_<service>_recovery_seconds
input_number.labpulse_<service>_stale_timeout_seconds
```

Per reading:

```text
input_select.labpulse_<service>_<reading>_alarm_state
input_select.labpulse_<service>_<reading>_alarm_mode
input_boolean.labpulse_<service>_<reading>_alarm_muted
input_number.labpulse_<service>_<reading>_minimum_threshold
input_number.labpulse_<service>_<reading>_maximum_threshold
input_number.labpulse_<service>_<reading>_recovery_deadband
binary_sensor.labpulse_<service>_<reading>_danger_zone
binary_sensor.labpulse_<service>_<reading>_recovery_zone
binary_sensor.labpulse_<service>_<reading>_sensor_fault_zone
sensor.labpulse_<service>_<reading>_danger_ratio
```

The existing entity map should be expanded to include these entities.

## Implementation Notes

Replace the current generated alarm logic rather than trying to preserve both
systems.

Likely files to change:

```text
docker_refactor/labpulse_homeassistant/model.py
docker_refactor/labpulse_homeassistant/alarm.py
docker_refactor/labpulse_homeassistant/dashboard.py
docker_refactor/labpulse_homeassistant/render.py
docker_refactor/labpulse_homeassistant/templates/alarm_logic.yaml
docker_refactor/labpulse_homeassistant/templates/dashboard_seed.yaml
docker_refactor/labpulse_homeassistant/templates/package.yaml.j2
docker_refactor/labpulse_homeassistant/README.md
docker_refactor/docs/CONTAINER_SETUP.md
docker_refactor/docs/HAPPY_PATH_SETUP.md
docker_refactor/docs/CODE_READING_GUIDE.md
docker_refactor/testing/test_homeassistant_generator.py
docker_refactor/testing/test_homeassistant_entities.py
```

The exact file list may change during implementation.

## Testing Expectations

Add or update tests to verify:

- generated package includes `input_select` alarm states
- generated package includes `input_select` alarm modes
- generated package includes mute booleans
- generated package includes per-service timing helpers
- generated package includes danger/recovery/fault zone binary sensors
- generated package includes `history_stats` ratio sensors
- danger transition uses the generated ratio sensor and service threshold helper
- recovery transition uses Home Assistant `for:`
- notification actions check mute before publishing SMS MQTT
- entity map includes the new state/mode/mute/history entities
- dashboard seed includes a clean Monitor view and a separate Alarm Setup view
- no old simple alert-active boolean behavior remains unless still needed by
  the new design

Run at least:

```powershell
python .\docker_refactor\testing\test_homeassistant_generator.py
python .\docker_refactor\testing\test_homeassistant_entities.py
python .\docker_refactor\testing\test_sms_container.py
```

Depending on touched files, also run:

```powershell
python .\docker_refactor\testing\test_homeassistant_mqtt.py
```

Clean generated test output and `__pycache__` after tests.

## Future Extensions

Critical can be added later by extending the same pattern:

```text
Critical state
critical zone
critical ratio sensor
critical thresholds
critical transition automations
escalation notifications
```

Do not implement Critical in v1.

Potential future additions:

- recovery deadband
- reminder notifications
- per-reading timing overrides
- native Home Assistant labels/areas/categories
- custom collapsible Lovelace cards if the user explicitly wants custom UI
- persistent timers that survive Home Assistant restarts
