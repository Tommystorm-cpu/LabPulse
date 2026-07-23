# Alarm Setup Layout Implementation Specification

## Status

This document is the implementation specification for replacing the current
Alarm Setup landing page and setup editor layout. It supersedes the visual
layout described for Alarm Setup in
`HOME_ASSISTANT_YAML_DASHBOARD_REFACTOR.md`, but it does not change the alarm
state machine, notification rules, MQTT identity, or measurement ownership.

The design has two levels:

1. **Alarm Setup landing page**: global notification controls, selective group
   alarm settings, setup navigation, setup notification mutes, and dedicated
   power-monitoring navigation.
2. **Setup subview**: one compact summary row per measurement, with an inline
   editor opened by a clearly labelled **Configure** button.

The dashboard remains generated YAML. Thresholds and alarm settings remain
Home Assistant helper state rather than configuration-file values.

## Goals

- Keep only logical setups visible on the Alarm Setup landing page.
- Make the landing page compact enough to understand at a glance.
- Show minimum threshold, maximum threshold, and recovery deadband as
  display-only values in each measurement row.
- Open the complete editor for one measurement from a Configure button on that
  row.
- Retain every currently implemented alarm control and live-status field.
- Allow group updates to change any subset of supported settings.
- Prevent a deadband value from being applied across incompatible measurement
  types or units.
- Preserve one physical entity, alarm state, helper set, history, and
  notification identity for a shared measurement.
- Produce a responsive layout usable on desktop, tablet, and phone.

## Non-goals

- Do not change threshold evaluation, danger entry, recovery, sensor-fault, or
  notification semantics.
- Do not make minimum or maximum thresholds bulk-editable in the first version.
  They are safety-specific values and remain per-measurement controls.
- Do not move persistent alarm settings into `config.yaml`.
- Do not group ordinary alarm controls by physical service or sensor hub.
- Do not merge dedicated power monitoring into the ordinary threshold alarm
  model.
- Do not create setup-specific copies of measurement entities or helpers.
- Do not require custom cards, HACS frontend packages, repository-owned
  JavaScript, `card-mod`, custom themes, or browser-local state.

## Existing features that must be retained

| Existing feature | Required presentation after the redesign |
| --- | --- |
| Global notification mute | Switch in Notification Controls; alarm state remains visible |
| Test mode | Switch in Notification Controls; active recipient mode is stated clearly |
| Phone-book notification | Explicit action with confirmation and test/live recipient context |
| Bulk target | All ordinary measurements or one non-empty logical setup |
| Required danger percentage | Optional group update and editable per measurement |
| Observation window | Optional group update and editable per measurement |
| Required recovery duration | Optional group update and editable per measurement |
| Alarm mode | Editable per measurement |
| Individual measurement mute | Editable per measurement without hiding alarm state |
| Minimum and maximum thresholds | Read-only in the row; editable in the measurement editor |
| Recovery deadband | Read-only in the row; editable per measurement; optional typed group update |
| Current measurement | Compact row/status value and full live-status value |
| Persistent alarm state | Compact row/status value and full live-status value |
| Observed danger percentage | Read-only live-status value |
| Danger, recovery, and sensor-fault zones | Read-only live-status values |
| Setup notification mute | Available on landing and repeated in its setup subview |
| Shared-measurement mute warning | Confirmation only when enabling the affected setup mute |
| Direct unmute | No confirmation |
| Dedicated power monitoring | Separate landing row and dedicated lifecycle subview |
| Stable subview paths and back path | Retained |

## Information architecture

```text
Alarm Setup
  Notification Controls
    Mute all notifications
    Test mode
    Send phone-book notification

  Group Alarm Settings
    Target: all measurements or one setup
    Optional common updates
      Required danger percentage
      Observation window
      Required recovery duration
    Optional typed updates
      One recovery-deadband control per compatible measurement family
    Review and apply selected changes

  Configure Alarms
    One row per non-empty logical setup
      Setup name and measurement count
      Setup notification state/mute action
      Configure action
    Dedicated Power Monitoring row

Setup subview
  Setup heading and setup notification mute
  Measurement rows
    Name, current value, and alarm state
    Minimum threshold
    Maximum threshold
    Recovery deadband
    Configure action
  Inline editor for the selected measurement
    Alarm controls
    Thresholds and deadband
    Timing and danger requirement
    Live alarm status
```

## Alarm Setup landing page

### Page structure

The landing page should use a native Home Assistant Sections view rather than
unconstrained masonry. On a normal desktop width:

- Notification Controls occupies the left section.
- Group Alarm Settings occupies the wider right section.
- Configure Alarms occupies the full width below them.

At phone width all three sections stack in that order. The page must not depend
on horizontal scrolling.

Only non-empty logical setups are listed. Physical service/hub names remain in
Diagnostics, not Alarm Setup.

### Notification Controls

The panel contains:

1. **Mute all notifications** bound to
   `input_boolean.labpulse_global_notifications_muted`.
2. **Test mode** bound to
   `input_boolean.labpulse_notification_test_mode`.
3. **Send phone-book notification** bound to
   `script.labpulse_send_phone_book_notification`.

The phone-book action must preserve its current confirmation. The confirmation
must state whether test or live recipients are active and must explain that
nothing is delivered while the global mute is enabled.

Changing a mute changes delivery only. It must not conceal or write any alarm
state.

### Group Alarm Settings

The current Bulk Timing panel becomes **Group Alarm Settings**. It retains the
existing target scopes and adds selective-update behavior and typed recovery
deadbands.

#### Target selection

The target selector contains:

1. `All measurements`;
2. one option per non-empty logical setup, in configured setup order.

Dedicated power telemetry is never included. A shared measurement is included
once in `All measurements` and once in each setup target to which it belongs,
but any one apply operation writes its physical helper only once.

The selected target displays its number of unique ordinary measurements.

#### Patch semantics

Every bulk-editable setting has an independent **apply** checkbox. The checkbox
is the authority for whether that setting will be written.

- All checkboxes default to off when Home Assistant starts.
- An unchecked setting is labelled **Unchanged**.
- Its value input is disabled or hidden.
- Checking it enables the input and changes its label to **Will change**.
- Pressing Apply with no selected settings is disabled.
- A displayed value must never imply that it will be written when its checkbox
  is off.

The common settings are independently selectable:

- required danger percentage;
- observation-window seconds;
- required-recovery seconds.

For example, an operator may update only required danger percentage while both
timing values remain untouched.

#### Typed recovery deadbands

Recovery deadband is grouped by a compatibility key:

```text
(device_class, exact native unit)
```

Examples:

- `(temperature, °C)`;
- `(pressure, bar)`;
- `(volume_flow_rate, L/min)`;
- `(humidity, %)`.

Measurements with different device classes or different native units must not
share a bulk deadband input. No implicit unit conversion occurs in this
feature. A measurement without a usable device class is placed in a
measurement-specific fallback group, preventing it from being combined with an
unrelated measurement merely because the unit text happens to match.

Only deadband groups present in the selected target are shown. Each group has:

- its own apply checkbox;
- its type label and native unit;
- the number of target measurements in that group;
- its own numeric value.

This permits, for example, changing only the temperature deadband while leaving
humidity deadband and every common setting unchanged.

#### Review and confirmation

Before any helper is written, the panel presents an exact review such as:

```text
Required danger: 75% -> 6 measurements
Temperature deadband: 1.2 °C -> 4 measurements
Everything else: unchanged
```

The final action requires confirmation. The confirmation identifies:

- the selected target;
- each selected setting and value;
- the number of unique physical measurements affected by that setting.

The apply operation snapshots the target, selected flags, values, and resolved
entity IDs at invocation. A target change during execution must not redirect a
partially completed update.

After a successful apply:

- all apply checkboxes reset to off;
- entered bulk values may remain available for reuse;
- a short success result reports exactly what changed.

If any write fails, the script reports failure and retains the selection so the
operator can review it. The script must not claim atomicity because Home
Assistant service calls update multiple helpers, but it must fail visibly and
must never write an unchecked setting.

### Configure Alarms list

Each non-empty logical setup has one compact row containing:

- setup icon and display label;
- unique measurement count;
- setup notification state;
- **Mute** or **Unmute** action;
- **Configure** action on the right.

Configure navigates to the setup's existing stable subview path:

```text
/labpulse-monitor/alarm-setup-<setup_id>
```

The setup mute remains independent from the global mute, every other setup
mute, and every measurement mute.

If the setup contains a shared measurement, enabling its mute names the shared
measurements and warns that they remain unmuted while another owning setup is
unmuted. Unmuting remains a direct action without confirmation.

The dedicated power row appears after logical setups. It has no logical setup
mute and navigates to:

```text
/labpulse-monitor/alarm-power-<service_id>
```

## Setup subview

### View configuration

Every non-empty setup remains a hidden native subview with:

- stable `path`;
- `subview: true`;
- `back_path: /labpulse-monitor/alarm-setup`;
- setup title and configured icon;
- repeated setup notification mute.

The current three-column Measurements / Alarm Settings / Live Alarm Status
layout is removed.

### Measurement list

The subview renders one row per ordinary measurement in canonical setup order.
Shared measurements appear in each owning setup but reference the same physical
entities and helper IDs.

Desktop columns are:

| Column | Content |
| --- | --- |
| Measurement | Friendly label, current value with unit, and persistent alarm state |
| Minimum | Display-only current minimum threshold |
| Maximum | Display-only current maximum threshold |
| Deadband | Display-only current recovery deadband |
| Action | Labelled Configure button |

The row must distinguish `unknown` and `unavailable` from numeric values. Alarm
state is always expressed in text; colour or icon may reinforce it but must not
be the only signal.

Minimum and maximum remain visible even when the alarm mode does not currently
use both. The inactive threshold may be visually secondary, but its value must
not be edited from the row.

On a narrow phone layout:

- measurement label, current value, and alarm state occupy the first line;
- minimum, maximum, and notification mute wrap into a compact grid below;
- Configure remains clearly labelled and reachable without horizontal scroll.

### Per-measurement editor

Configure toggles the existing
`input_boolean.*_alarm_controls_expanded` helper for that physical
measurement. The matching editor opens immediately below that row. Closing the
editor turns the same helper off.

The first implementation may allow more than one measurement editor to remain
open. If exclusive expansion is later desired, it must be implemented only as
presentation state and must not couple alarm helpers or alarm decisions.

The editor contains two logical areas.

#### Editable alarm settings

- alarm mode;
- individual measurement mute;
- minimum threshold;
- maximum threshold;
- recovery deadband;
- required danger percentage;
- observation-window seconds;
- required-recovery seconds.

These controls bind directly to the existing per-measurement helpers. There is
no separate Save button: Home Assistant helper changes retain their current
immediate-write behavior. The UI must not imply transactional editing.

#### Read-only live alarm status

- current measurement;
- persistent alarm state;
- observed danger percentage;
- danger-zone state;
- recovery-zone state;
- sensor-fault-zone state.

The live-status values stay visible inside the open editor so the redesign does
not remove the diagnostic context provided by the current right-hand column.

### Shared-measurement behavior

A shared measurement row may appear in several setup subviews. Every occurrence
must reference the same:

- MQTT sensor entity;
- alarm-mode helper;
- mute helper;
- threshold helpers;
- deadband helper;
- timing helpers;
- alarm-state and derived-zone entities;
- expansion helper.

Editing any occurrence therefore updates the other occurrence naturally. No
setup-specific alarm state or duplicate notification path may be introduced.

## Dedicated power subview

The power subview retains its current lifecycle controls and read-only status:

- sensor-hub fault active;
- power lifecycle state;
- power alert mute;
- confirmed external-power input;
- raw GPIO mains value;
- external-power sensor fault;
- confirmed outage active.

It adopts the same visual heading and compact row language where practical but
does not receive thresholds, deadbands, danger percentages, or ordinary group
settings.

## Native Home Assistant card requirement

The dashboard must use only card types, features, actions, conditions, and
layouts shipped with Home Assistant. This is a deliberate long-term
maintenance boundary.

The generated dashboard must not contain any `custom:*` card type and must not
register or load frontend resources. In particular, implementation must not
introduce Mushroom, Button Card, multiple-entity-row, layout-card, `card-mod`,
HACS, or a LabPulse-owned JavaScript card.

The supported vocabulary for this design is:

- Sections views and grid sections;
- section backgrounds for visual grouping;
- heading, tile, button, entities, markdown, conditional, and vertical-stack
  cards;
- built-in tile-card features such as toggle, select options, and numeric
  input;
- normal Home Assistant tap/hold/double-tap actions;
- Home Assistant template entities and Markdown-card templates;
- generated Home Assistant helpers, scripts, and automations.

Alarm state and durable configuration remain in Home Assistant entities. No
required presentation state may exist only in a browser.

### Native measurement-row composition

Home Assistant does not provide a native multi-entity table row with an
independent labelled action. The generator therefore emits desktop and mobile
projections of each measurement, selected by native screen conditions. Both
projections reference the same entities and helpers.

Use a full-width three-section desktop grid with one compact line:

```text
measurement (6) | alarm state (6) | minimum (6) | maximum (6) |
notification mute (6) | Configure (6)
```

The mobile projection gives measurement and alarm state full rows, places
minimum, maximum, and notification mute in three four-column cells, and gives
Configure/Close a full row. Closed measurement sections have no background.

Cards within the section are:

1. a read-only tile for the MQTT measurement entity;
2. a read-only tile for the persistent alarm-state entity;
3. a read-only tile for minimum threshold;
4. a read-only tile for maximum threshold;
5. a state-aware notification-mute tile;
6. a state-hidden tile bound to the existing expansion helper, named
   **Configure** while closed and **Close** while open;
7. the existing conditional editor, spanning the full section width.

All display-only tiles set tap, hold, double-tap, and icon-tap actions to
`none`. This prevents the more-info dialog from becoming an unintended edit
path. Only notification mute and Configure/Close are interactive in the compact
row.

The renderer emits two conditional Configure/Close tiles if a dynamic name is
not supported reliably by the selected native card:

- when the expansion helper is off, show Configure with a turn-on/toggle
  action;
- when it is on, show Close with a turn-off/toggle action.

The full-width conditional editor uses side-by-side Alarm behaviour and
Confirmation timing entities cards on desktop, stacked cards on mobile, and a
separate Live status card with a Close action.

### Native group-settings composition

Group Alarm Settings is assembled from native generated cards and helpers:

1. a compact entities card containing the target select and unique target count;
2. one apply-flag entity row per common setting;
3. one conditional input-number row beneath each selected common apply flag;
4. target-conditional typed-deadband groups;
5. one apply-flag row and conditional input-number row per visible deadband
   group;
6. a templated Markdown review;
7. conditional Apply controls for empty and non-empty selections.

The entire group editor is collapsed behind a native Configure/Close tile by
default so setup navigation remains visible at the top of Alarm Setup.

Every common-setting block follows this native pattern:

```yaml
type: vertical-stack
cards:
  - type: tile
    entity: input_boolean.labpulse_bulk_apply_required_danger_percent
    name: Change required danger
    features:
      - type: toggle
  - type: conditional
    conditions:
      - entity: input_boolean.labpulse_bulk_apply_required_danger_percent
        state: "on"
    card:
      type: tile
      entity: input_number.labpulse_bulk_required_danger_percent
      name: Required danger
      features:
        - type: numeric-input
```

Typed deadband blocks use the same pattern and are additionally conditional on
the selected target option. The renderer generates the exact target/group
combinations; the dashboard does not infer compatibility from labels.

Changing the target invokes or triggers a generated reset action that turns
off every bulk apply flag before the new target's controls are used. This
prevents a hidden selection from the previous target being applied
unexpectedly.

The native Markdown review reads the target, apply flags, bulk values, and
generated target counts. It lists only settings whose apply flag is on. It
must show **Nothing will be changed** when the selection is empty.

Use a generated template binary sensor such as
`binary_sensor.labpulse_bulk_alarm_changes_selected` to drive two native
conditional cards:

- when off, show a disabled/non-actionable Apply tile explaining that no
  settings are selected;
- when on, show the actionable Apply tile with confirmation.

The confirmation text may refer to the immediately adjacent exact Markdown
review rather than duplicating a dynamically templated message in an action
field that Home Assistant may not template.

### Native setup navigation composition

Each logical setup landing row is a full-width native grid/stack containing:

- a setup tile that navigates to the stable subview;
- a setup mute tile with built-in toggle feature when no shared warning is
  required;
- the existing pair of conditional confirmed-mute/direct-unmute tiles when the
  setup contains shared measurements.

The dedicated power row is one native navigation tile without a logical setup
mute.

### Accessibility and responsiveness

The generated native layout must:

- use visible text labels for Configure, Close, Mute, Unmute, and Apply;
- retain Home Assistant's built-in keyboard and focus behaviour;
- state Normal, Danger, Sensor Fault, Unknown, and Unavailable in text;
- avoid colour-only state or selection indicators;
- use section and card grid options rather than CSS positioning;
- support widths down to 320 px without page-level horizontal scrolling;
- use only built-in theme behaviour, without custom CSS or themes required for
  correctness.

## Render-model additions

Introduce explicit bulk-setting projections rather than reconstructing groups
inside the dashboard renderer.

Suggested immutable models:

```python
@dataclass(frozen=True)
class DeadbandGroupKey:
    device_class: str
    unit: str


@dataclass(frozen=True)
class BulkDeadbandGroup:
    key: DeadbandGroupKey
    label: str
    helper_slug: str
    unit: str
    measurement_keys: tuple[MeasurementKey, ...]
    value_entity: str
    apply_entity: str


@dataclass(frozen=True)
class BulkAlarmTarget:
    target_id: str
    option: str
    measurement_keys: tuple[MeasurementKey, ...]
    deadband_groups: tuple[BulkDeadbandGroup, ...]
```

The canonical catalog owns membership and deduplication. The render model adds
only entity IDs and display metadata.

The existing `BulkTimingTarget` should be replaced or expanded rather than
maintained as a competing target model.

## Generated helper changes

Retain the existing bulk target and common value helpers. Add apply flags:

```text
input_boolean.labpulse_bulk_apply_required_danger_percent
input_boolean.labpulse_bulk_apply_observation_window_seconds
input_boolean.labpulse_bulk_apply_required_recovery_seconds
```

For every distinct deadband compatibility group in enabled ordinary
measurements, generate:

```text
input_boolean.labpulse_bulk_apply_deadband_<helper_slug>
input_number.labpulse_bulk_deadband_<helper_slug>
```

Examples:

```text
input_boolean.labpulse_bulk_apply_deadband_temperature_c
input_number.labpulse_bulk_deadband_temperature_c
input_boolean.labpulse_bulk_apply_deadband_pressure_bar
input_number.labpulse_bulk_deadband_pressure_bar
```

Apply flags must start off and must be turned off after a successful apply.
Bulk value helpers may restore their previous values.

Generate these presentation-support entities as normal Home Assistant package
state:

```text
binary_sensor.labpulse_bulk_alarm_changes_selected
script.labpulse_clear_bulk_alarm_selection
```

The template binary sensor is on when any common or typed-deadband apply flag
is on. The clear-selection script turns every apply flag off. An automation
triggered by a change to `input_select.labpulse_bulk_alarm_timing_target`
invokes the clear-selection script, ensuring a selection cannot remain hidden
after the target changes.

These entities coordinate native cards only. They do not participate in alarm
calculation or notification delivery.

Helper numeric limits and steps must be derived conservatively from the target
measurement helpers in that compatibility group. If group members do not share
compatible limits or step size, use the strictest intersection and the least
precise compatible step. Reject an empty intersection during generation.

## Group apply script

Rename or replace `script.labpulse_apply_bulk_alarm_timing` with:

```text
script.labpulse_apply_bulk_alarm_settings
```

The script must:

1. snapshot the selected target;
2. resolve its canonical unique measurement list;
3. snapshot every apply flag and selected value;
4. reject invocation when no apply flag is on;
5. copy required danger only when its flag is on;
6. copy observation window only when its flag is on;
7. copy required recovery only when its flag is on;
8. for each selected deadband group, update only target measurements belonging
   to that exact compatibility group;
9. never update minimum threshold, maximum threshold, alarm mode, or mute;
10. clear apply flags only after all selected action sequences complete;
11. expose a clear success/failure result for the dashboard.

Every target-to-entity mapping is generated from the canonical catalog. Do not
construct entity IDs inside Home Assistant templates.

## Python and template changes

Expected implementation locations:

| File | Change |
| --- | --- |
| `src/labpulse/homeassistant/dashboard/alarm_setup.py` | Replace landing stacks and three-column subview assembly with native Sections panels, setup rows, per-measurement grid sections, and inline conditional editors |
| `src/labpulse/homeassistant/templates/dashboard/cards.yaml` | Replace launcher/settings/status fragments with native tile, conditional, entities, Markdown-review, inline-editor, and power fragments |
| `src/labpulse/homeassistant/render_model.py` | Add bulk target/deadband projections and explicit native-card entity metadata |
| `src/labpulse/homeassistant/alarm_package.py` | Generate selective apply flags, typed deadband helpers, and selective apply script |
| `src/labpulse/homeassistant/templates/alarm/package.yaml.j2` | Include new helpers/script sections if owned at the package-template layer |
| `src/labpulse/homeassistant/dashboard_writer.py` | Keep visible view order and hidden subview order; no state logic |
| setup/deployment generation | No frontend-resource installation; continue generating only supported Home Assistant configuration and dashboard files |

Remove obsolete card fragments and renderer helpers rather than leaving the
three-column path as a fallback.

## Dashboard generation rules

- Generated YAML remains deterministic.
- Setup and measurement order follows the canonical configured order.
- Every native card receives explicit entity IDs from the render model; no
  identity is derived from labels or presentation text.
- Empty setups produce no landing row and no subview.
- Power services produce the dedicated row/subview only.
- Shared measurements reuse physical IDs in every generated occurrence.
- The dashboard contains no `custom:*` card types, custom resources, custom
  CSS, or JavaScript modules.
- The generated-file warning remains at the top of
  `labpulse-dashboard.yaml`.
- Normal generation does not read or write Home Assistant `.storage`.

## Test plan

### Render-model tests

- derive compatibility groups from `(device_class, exact unit)`;
- separate the same device class when units differ;
- isolate missing/ambiguous device classes safely;
- deduplicate shared measurements in the all-measurements target;
- retain one physical helper set for shared measurements;
- exclude dedicated power telemetry from every ordinary bulk target;
- calculate deterministic target and group order.

### Alarm-package tests

- all new apply flags start off;
- changing the target clears common and typed-deadband apply flags;
- the changes-selected binary sensor follows every apply flag;
- selecting only required danger writes no timing or deadband helpers;
- selecting only one typed deadband writes only compatible target helpers;
- selecting several fields writes exactly those fields;
- unchecked displayed values are never written;
- shared measurements are written once per invocation;
- empty selection is rejected;
- successful apply clears flags;
- failure does not report success or silently clear the pending selection;
- minimum, maximum, alarm mode, and mutes are never bulk-written.

### Dashboard tests

- visible view order remains Monitor, Alarm Setup, Diagnostics;
- landing page contains Notification Controls, Group Alarm Settings, and
  Configure Alarms in order;
- every non-empty setup produces exactly one landing row and one hidden subview;
- each setup row contains notification state, mute action, and Configure action;
- shared setup mute warns only while enabling mute;
- direct unmute requires no confirmation;
- power navigation remains present and has no logical setup mute;
- each measurement subview row references current value, alarm state, minimum,
  maximum, deadband, and expansion helper;
- threshold/deadband row values are display-only;
- display-only tiles have every interaction action set to `none`;
- each measurement is one native grid section with a conditional full-width
  editor;
- the inline editor contains every retained editable and read-only entity;
- obsolete three-column headings and launcher grids are absent;
- selective common and deadband inputs appear only when their apply flag is on;
- changing bulk target clears every apply flag;
- the native Markdown review lists only selected changes;
- empty and non-empty selections produce the correct conditional Apply tile;
- no generated card type starts with `custom:`;
- no Lovelace resource registration is added;
- no card references a missing generated entity.

### End-to-end generation and Home Assistant checks

- clean generation emits valid YAML without downloading, copying, or
  registering a frontend module;
- `ha core check` or the deployment's equivalent accepts the generated config;
- the dashboard loads using only card types included with Home Assistant;
- helper values survive dashboard regeneration;
- applying a selective update on fake hardware changes exactly the intended
  helper states;
- alarm behaviour remains correct after each changed helper value;
- real-Pi smoke testing covers desktop and phone-sized clients;
- the browser console contains no missing-card or missing-resource errors.

## Documentation updates required with implementation

Update these maintained documents in the same change:

- `HOME_ASSISTANT_YAML_DASHBOARD_REFACTOR.md`;
- `CODE_INTERNALS.md`;
- `SETUP_AND_TROUBLESHOOTING.md`;
- `src/labpulse/homeassistant/README.md`;
- `SOFTWARE_TODO.md` to record native-only dashboard presentation as a durable
  maintenance boundary.

Document how to reload the generated YAML dashboard and how to diagnose an
unsupported or renamed native card/feature after a future Home Assistant
upgrade. No HACS or frontend-resource installation instructions are required.

## Implementation sequence

1. Add compatibility-group and expanded bulk-target models with unit tests.
2. Extend alarm-package generation with apply flags, typed deadband helpers,
   and the selective apply script.
3. Add native target-reset and changes-selected template entities/automation.
4. Replace the landing page renderer with native Sections, tile, conditional,
   Markdown, and stack cards.
5. Replace three-column setup subviews with native per-measurement grid
   sections and inline conditional editors.
6. Retain and restyle the dedicated power subview using native cards.
7. Update dashboard and package tests to assert exact entity ownership and
   selective-write behaviour.
8. Add assertions that reject custom card types and resource registration.
9. Generate a fake-hardware installation and perform Home Assistant config
   validation.
10. Perform browser checks at desktop, tablet, and phone widths.
11. Update maintained documentation and remove stale layout descriptions.

## Acceptance criteria

The redesign is complete when:

- the landing page shows only notification tools, group settings, logical
  setups, and dedicated power navigation;
- each measurement appears as a compact row with display-only minimum and
  maximum values plus its notification-mute control;
- Configure opens the complete editor for that physical measurement;
- every editable setting and live-status field from the old layout remains
  available;
- an operator can apply only required danger, only one typed deadband, or any
  other supported subset without writing unchecked values;
- incompatible measurement types or units never share a deadband control;
- all bulk actions require an exact review and confirmation;
- shared measurements retain one identity, helper set, alarm, history, and
  notification event;
- setup, global, individual, and power mutes remain independent;
- the dedicated power lifecycle remains outside ordinary threshold controls;
- the generated dashboard contains only native Home Assistant cards and needs
  no HACS package, custom resource, JavaScript, CSS, or custom theme;
- automated generation, alarm-package, dashboard, and end-to-end tests pass;
- Home Assistant accepts the generated configuration and the fake-hardware UI
  has been checked at desktop and phone widths.
