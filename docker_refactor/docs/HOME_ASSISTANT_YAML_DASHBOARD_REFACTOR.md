# Home Assistant YAML Dashboard and Setup Grouping Refactor

Status: implemented and verified by the lightweight offline test suite.

This document is the implementation specification for replacing direct Home
Assistant `.storage` dashboard writes with a generated YAML dashboard and for
separating physical sensor hubs from logical experimental setups.

It replaces the earlier WebSocket-dashboard proposal. The dashboard is not
managed through Home Assistant's WebSocket API, and custom cards are not a
required part of this refactor.

## Goals

1. Generate a supported Home Assistant YAML-mode LabPulse dashboard.
2. Remove all direct reads and writes of Home Assistant `.storage` dashboard
   files.
3. Preserve the existing generated/expanding dashboard behavior using native
   Home Assistant cards.
4. Let users group measurements by logical experimental setup independently of
   the physical service or sensor hub that reads them.
5. Provide both setup-oriented operational views and hub-oriented diagnostic
   views.
6. Keep MQTT identity, history, alarm state, and physical acquisition
   independent of dashboard grouping.
7. Prefer long-term stability and reproducibility over custom frontend code or
   visual dashboard editing.

## Non-goals

- Do not introduce custom Lovelace cards, dashboard strategies, or panels as a
  required runtime dependency.
- Do not add a Home Assistant custom integration solely for dashboard
  generation.
- Do not use the Lovelace WebSocket save commands.
- Do not retain direct `.storage` mutation as a fallback mode.
- Do not create separate MQTT entities or alarms for each setup in which a
  measurement appears.
- Do not add compatibility layers for the current pre-release dashboard
  format. Update the starter and live configuration to the new design.
- Do not move alarm decisions out of Home Assistant.

## Core domain model

The current dashboard hierarchy conflates two independent relationships:

```text
Physical topology                 Logical topology
-----------------                 ----------------
service / sensor hub              experimental setup
  -> driver                         -> selected measurements
  -> serial/GPIO/I2C path           -> presentation groups
  -> parser                         -> operator context
  -> service health
  -> owned measurements
```

A measurement is physically owned by exactly one service. Every ordinary measurement
explicitly names one or more logical setups. Dedicated power telemetry is not
an experimental setup and omits membership.

The implementation must build one canonical measurement catalog and project it
in two ways:

```text
Validated configuration
        |
        v
Canonical measurement catalog
        |
        +-- by setup   -> Monitor and Alarm Setup
        |
        +-- by service -> Diagnostics
```

The projections must reference the same measurement model rather than copying
identity, threshold, or alarm data into separate setup-specific models.

## User configuration

The live source of truth remains:

```text
~/labpulse-ha/config.yaml
```

The repository `docker_refactor/config.yaml` remains only the fresh-install
starter.

### Setup definitions

Top-level `setups` define presentation metadata only. They do not repeat the
measurement catalog.

```yaml
setups:
  turbo_pump_experiment:
    label: "Turbo Pump Experiment"
    icon: "mdi:vacuum-outline"
    order: 10

  cryostat_experiment:
    label: "Cryostat Experiment"
    icon: "mdi:snowflake"
    order: 20

  magnet_testing:
    label: "Magnet Testing"
    icon: "mdi:magnet"
    order: 30
```

Setup IDs are stable machine identifiers. Labels, icons, and order are
presentation values and may change without changing entity identity.

The initial model should support:

```python
class SetupConfig(BaseModel):
    label: str | None = None
    icon: str = "mdi:flask-outline"
    order: int = 100
```

When `label` is omitted, derive a readable label from the setup ID.

### Measurement membership

Each measurement is declared once under its physical service. A required `setups`
field specifies its logical scope.

The accepted form is a non-empty list:

```yaml
setups:
  - turbo_pump_experiment
  - cryostat_experiment
```

Example:

```yaml
services:
  pump_room:
    enabled: true
    driver: serial
    parser: pump_room
    serial_port: "/dev/serial/by-id/..."
    baud_rate: 9600
    device_name: "Pump Room Sensor Hub"
    measurements:
      - name: "plant_room_temperature"
        label: "Plant Room Temperature"
        unit: "°C"
        setups:
          - building_environment
        subcategory: "Building Environment"

      - name: "turbo_flow"
        label: "Turbo Cooling Flow"
        unit: "L/min"
        setups:
          - turbo_pump_experiment
        subcategory: "Cooling Water"

      - name: "cooling_supply_pressure"
        label: "Cooling Supply Pressure"
        unit: "bar"
        setups:
          - turbo_pump_experiment
          - cryostat_experiment
        subcategory: "Cooling Water"

  room_environment:
    enabled: true
    driver: gpio
    gpio_sensor: dht11
    gpio_pin: "D4"
    device_name: "Room Environment Sensor"
    measurements:
      - name: "temperature"
        label: "Room Temperature"
        unit: "°C"
        setups:
          - room_conditions
        subcategory: "Room Conditions"
```

### Physical service presentation

Services do not have a separate `display` block. Logical setup metadata owns
Monitor presentation, while `device_name` is the physical hub label used by
Diagnostics. Physical services and their measurements retain their order from
`config.yaml`, and service headings use a standard icon by default.

Do not use presentation-only service sections to represent physical
locations. If location-aware Diagnostics becomes necessary, add an explicit
location model rather than reintroducing `display.section`.

The meanings are:

| Value | Meaning |
| --- | --- |
| List of IDs | Measurement applies to exactly those setups |

If a condition is conceptually general or applies across the lab, give it a
descriptive setup of its own, such as `room_conditions`. Require membership on
every ordinary measurement. Measurements in a service with `power_detection` instead
omit `setups`, because the dedicated power lifecycle is rendered separately.

### Measurement subcategories

An optional `subcategory` groups related measurements within their effective
setup section. It is presentation
only and does not alter setup membership, physical ownership, identity, or
alarms. Use it for operational context such as `Cooling Water` or `Room
Conditions`; `device_class` continues to describe the measurement type such
as temperature or pressure.

### Normalized membership model

Normalize and validate the YAML list at config load time. Rendering code
should receive one typed representation.

```python
class SetupScope:
    setup_ids: tuple[str, ...]
```

The exact Pydantic implementation may differ, but downstream code must receive
one normalized representation.

### Validation

Configuration validation must reject:

- duplicate setup IDs;
- blank setup IDs or labels;
- invalid setup icons or ordering values where applicable;
- a selected setup ID that is not declared under top-level `setups`;
- duplicate setup IDs in one measurement's selected list;
- missing or empty membership on an ordinary measurement;
- membership on dedicated power telemetry;
- duplicate measurement names within a service, as today.

Validation must allow:

- one hub serving measurements from several setups;
- one setup containing measurements from several hubs;
- one measurement appearing in several selected setups;
- explicit single-setup measurements;
- explicit shared measurements;
- setup-independent dedicated power measurements;
- a setup temporarily containing no enabled measurements;
- disabled services whose measurements are omitted from generated views.

## Identity and state rules

Setup membership is presentation and notification context. It must never
change the physical measurement identity.

For example:

```text
service: pump_room
measurement: flow1
entity:  sensor.labpulse_pump_room_flow1
```

Moving that measurement between setups must not:

- change its MQTT topic or unique ID;
- create another Home Assistant sensor;
- reset recorder history;
- create setup-specific threshold helpers;
- create duplicate alarm automations;
- emit duplicate SMS messages;
- alter the hardware container or driver configuration.

Labels and optional setup-specific presentation text must not be used as
stable identity inputs.

## Dashboard views

Generate one dedicated YAML dashboard with three views.

### 1. Monitor

The Monitor view is the main operator view and is grouped logically.

The Monitor view uses native masonry so independently sized columns pack
compactly across the available screen width. Render columns in this order:

1. Active Problems: a native entity-filter nested at the top of the first
   available column. It hides when empty and watches confirmed service faults,
   persistent ordinary-measurement alarm state, and persistent power state. Measurement
   rows require their individual and every owning setup mute to be off; the
   global mute does not affect this operational summary.
2. Dedicated Power: one independent column for a service with
   `power_detection`; it is never grouped into a setup.
3. One ordered column per configured setup.

Membership behavior:

| Scope | Monitor presentation |
| --- | --- |
| One selected setup | Full card in that setup |
| Several selected setups | Full card in each selected setup with a Shared indicator |

Repeating a selected shared measurement means repeating only its card/entity
reference. There remains one Home Assistant entity and one alarm state.

Where practical, a shared card should show the other affected setup labels.

Use native Home Assistant masonry, vertical stacks, headings, tiles, entity
rows, gauges, and card features. Do not require custom frontend resources.

`subcategory` controls entity-card boundaries only. Do not render its text as
a visible heading: the separate boxes already communicate the grouping.

### 2. Alarm Setup

Alarm controls remain Home Assistant helper entities and the existing
expanding/conditional behavior should be preserved using native cards.

Render controls by logical setup, with no physical sensor-hub grouping:

```text
Alarm Setup
  Masonry landing page
  Notification Controls card
  Bulk Timing card
    target: all measurements or one configured setup
  Configure Alarms card
    each setup: navigation | setup mute
    one tile per non-empty setup
    dedicated power tile when configured

Setup subview
  repeated setup notification mute
  left: two-column measurement launcher grid
  middle: conditional editable alarm settings
  right: conditional live alarm status
```

Shared measurements appear in each affected setup, but every appearance references
the same physical helper entities and alarm state. Observation window, required
danger percentage, and recovery duration are per-measurement controls. The bulk
editor copies all three values to all ordinary measurements or one selected setup
after explicit confirmation.

Each non-empty setup uses a native Home Assistant subview with a stable path and
an explicit back path to the Alarm Setup landing page. The internal expansion
helper state is hidden from the compact measurement tiles. The same helper reveals
two separate cards: editable alarm settings in the middle column and read-only
live alarm status in the right column. Live status contains current value,
alarm state, observed danger, and danger/recovery/fault zones. Physical
Diagnostics excludes these alarm-engine entities and remains hub-oriented.

Each non-empty setup has an independent notification mute. Ordinary measurement
delivery requires the global mute, every assigned setup mute, and the individual
measurement mute to be open; toggling one must never write to another. Because a
shared measurement has one physical notification, muting any owning setup suppresses
that notification everywhere. The dashboard warns and requires confirmation
before enabling a mute for a setup containing shared measurements, while allowing
unmute without confirmation. Logical setup mutes do not govern physical
service-health or dedicated power alarms.

Native tile-card features should be preferred over long generic entity lists:

- toggle feature for mute controls;
- select-options feature for alarm mode;
- numeric-input feature, using buttons where suitable, for thresholds and
  timing;
- bar-gauge feature for observed danger percentage;
- conditional expansion for advanced timing and diagnostics.

The frontend remains presentation only. Home Assistant templates,
automations, helpers, and scripts continue to own alarm decisions and state.

### 3. Diagnostics

Diagnostics ignores setup membership and uses native masonry with one compact
vertical card per physical service or sensor hub.

Each service section should show:

- a device/hub heading;
- one prominent connection tile;
- paired Service Health and Confirmed service fault tiles;
- one latest-measurements entity card containing every physically owned measurement;
- a power lifecycle card where applicable.

Service cards follow their order under `services` in `config.yaml` and use
`device_name` as the heading. Their different heights pack naturally without a
separate service display order.

Every measurement appears exactly once in Diagnostics, even if it appears in
several logical setup sections on Monitor.

## Setup status and notifications

A setup's displayed health may be derived from all measurements that effectively
apply to it:

- measurements explicitly assigned to the setup;
- selected measurements shared with that setup;

If setup-level summary entities are implemented, their initial precedence
should be:

```text
Sensor Fault > Danger > Unknown > Normal
```

This summary is presentation state only and must not create additional alarm
events.

One physical measurement produces one notification. Include setup context in the
message rather than sending one message per setup:

| Scope | Notification context |
| --- | --- |
| One selected setup | `Affected setup: ...` |
| Several selected setups | `Affected setups: ..., ...` |

The diagnostic hub label may also be included, but setup membership must not
alter duplicate protection or cooldown identity.

## YAML dashboard ownership

The generated Home Assistant dashboard should be a normal Lovelace YAML
document, not a storage wrapper.

Target generated path:

```text
~/labpulse-ha/homeassistant/config/labpulse-dashboard.yaml
```

Register it through generated `configuration.yaml`:

```yaml
lovelace:
  dashboards:
    labpulse-monitor:
      mode: yaml
      filename: labpulse-dashboard.yaml
      title: LabPulse
      icon: mdi:flask-outline
      show_in_sidebar: true
```

The dashboard document itself should contain ordinary Lovelace configuration:

```yaml
views:
  - title: Monitor
    path: monitor
    type: sections
    sections: []
  - title: Alarm Setup
    path: alarm-setup
    type: sections
    sections: []
  - title: Diagnostics
    path: diagnostics
    type: sections
    sections: []
```

Do not emit `.storage` fields such as `version`, `minor_version`, `key`, or
`data.config`.

### Editing boundaries

| Concern | Durable source |
| --- | --- |
| Services, measurements, labels, setup membership | `~/labpulse-ha/config.yaml` |
| Thresholds, modes, deadband, and mute state | Home Assistant state/UI |
| Dashboard layout/card rules | repository dashboard seed/templates |
| Expanded live dashboard | generated `labpulse-dashboard.yaml` |
| Ongoing helper values | Home Assistant state/UI |

The generated dashboard must begin with a warning similar to:

```yaml
# GENERATED BY LABPULSE.
# Changes to this file are overwritten by regeneration.
# Edit config.yaml for sensors/grouping or repository dashboard rules for layout.
```

Advanced users may experiment by editing the generated YAML, but durable
changes must be moved into `templates/dashboard/cards.yaml` or the matching
module under `labpulse_homeassistant/dashboard/` before regeneration.

## Generator simplification

Normal generation becomes:

```text
load config
  -> validate and normalize
  -> build canonical catalog
  -> build setup and service projections
  -> render packages/entity map
  -> render labpulse-dashboard.yaml
```

The completed cleanup removed private Lovelace path discovery and JSON writes,
dashboard-only backup/restore/reset/synchronization modes, their flag
validation, storage ownership handling, wrapper templates, and operational
instructions.

No old mutation path remains as a fallback.

Full Home Assistant backup and reconstruction remain separate operational
requirements. Protect accounts, integrations, helper state, credentials, and
recorder data through the deployment's complete backup policy.

## Python structure

The implementation should favor a small number of clear models:

```text
labpulse_common/config.py
  SetupConfig
  normalized measurement SetupScope
  cross-reference validation

labpulse_homeassistant/
  catalog/models
    canonical service and measurement identity
  projections
    measurements by effective setup
    measurements by service
    none/shared/all classifications
  dashboard
    pure native-card Lovelace rendering
  core_config.py
    core Home Assistant configuration output
  dashboard_writer.py
    dashboard composition and generated file output
```

Exact filenames may be chosen during implementation. Do not duplicate config
loading, slug generation, stable IDs, or entity-ID logic in the renderer.

The existing large render model should be simplified where setup projections
make derived fields unnecessary. Prefer calculated entity namespaces or
properties over storing long lists of mechanically derived IDs.

## Entity renaming decision

The YAML dashboard should reference stable LabPulse entity IDs. Renaming
generated LabPulse entities in the Home Assistant UI is not a required user
workflow.

The optional entity-registry resolver has been removed. MQTT discovery and all
generated YAML use the same deterministic identity functions. Operators change
friendly labels in `config.yaml` and must not rename generated LabPulse entity
IDs through Home Assistant. A numeric suffix indicates a stale registry
collision that should be cleaned up rather than normalized into generated
configuration.

## Related alarm-model issue

Service-wide danger percentage, observation window, and recovery duration are
currently shared because measurements are attached to the same physical hub. The
new setup model demonstrates that physical co-location does not necessarily
mean shared alarm policy.

This refactor must not accidentally add further service/setup coupling.
Moving timing to per-measurement helpers or named alarm profiles is a related
follow-up design decision, not an implicit part of the first dashboard
implementation. Record and test whichever policy is selected before changing
alarm semantics.

## Completed implementation sequence

1. Add setup configuration models and normalized membership validation.
2. Update the starter `config.yaml` with explicit membership for every
   measurement.
3. Build a canonical catalog and separate setup/service projections.
4. Add projection tests for `none`, one, selected-many, and `all`.
5. Change dashboard rendering to return a plain Lovelace configuration.
6. Generate and register `labpulse-dashboard.yaml` through
   `configuration.yaml`.
7. Implement Monitor, Alarm Setup, and Diagnostics using native cards.
8. Preserve and test expandable alarm controls.
9. Add setup context to notifications without duplicating events.
10. Verify the YAML dashboard on the fake-hardware installation and test Pi.
11. Remove all direct `.storage`, backup/load/reset/sync, and ownership code.
12. Update architecture, internals, setup/troubleshooting, and roadmap docs.

Only YAML dashboard generation is maintained.

## Test requirements

### Configuration tests

- valid setup metadata and inferred labels;
- required measurement membership;
- one and selected-many normalization;
- missing setup references;
- duplicate selected setup IDs;
- missing or empty ordinary membership;
- dedicated power membership rejection;
- disabled services and empty effective setups.

### Projection tests

- one hub contributes measurements to different setups;
- one setup receives measurements from different hubs;
- one measurement appears in several selected setups;
- dedicated power stays outside setup projections;
- every measurement appears once under its physical service in Diagnostics;
- projections reuse canonical measurement identity.

### Dashboard tests

- generated file is valid Lovelace YAML with no storage wrapper;
- generated `configuration.yaml` registers the dashboard in YAML mode;
- visible view order is Monitor, Alarm Setup, Diagnostics;
- non-empty setup and dedicated power editors are native hidden subviews;
- setup, subcategory, and measurement order is deterministic;
- shared measurements reference the same entity IDs in every appearance;
- alarm controls are grouped by setup and reuse shared physical identities;
- setup mutes are independent and shared-measurement impact requires confirmation;
- timing is per measurement and the bulk script has exact logical targets;
- native conditional expansion still works;
- collapsed measurement launchers are state-hidden and arranged two across;
- each expansion aligns editable settings with read-only live status;
- no custom card/resource is required;
- generated-file warning is present.

### Alarm and notification tests

- setup membership does not change alarm/entity identity;
- one measurement event produces one notification;
- context correctly distinguishes one and selected-many;
- every assigned setup independently gates shared-measurement delivery;
- no setup, measurement, global, or power mute writes another mute helper;
- service faults remain hub-level diagnostics;
- setup summary state, if implemented, does not emit duplicate alarms.

### Deployment tests

- clean setup generates the dashboard without Home Assistant running;
- no access token is required;
- no code accesses `.storage`;
- Home Assistant accepts the generated configuration;
- dashboard reload/restart instructions are accurate;
- regeneration deterministically replaces only generated files;
- real helper values survive dashboard regeneration.

## Acceptance criteria

The refactor is complete when:

- every ordinary measurement explicitly selects one or more setup IDs;
- dedicated power measurements remain setup-independent;
- Monitor and Alarm Setup are organized logically by setup;
- Diagnostics is organized physically by service/hub;
- shared measurements are contextually repeated without duplicating entities,
  alarms, history, or notifications;
- setup-grouped alarm controls share one physical state per measurement;
- per-measurement timing and confirmed bulk timing are generated;
- the dashboard is generated as supported YAML and registered normally;
- ordinary generation never reads or writes `.storage`;
- storage dashboard flags, backups, ownership handling, and documentation are
  removed;
- only native Home Assistant cards are required;
- fake-hardware tests and a real-Pi Home Assistant config check pass;
- maintained documentation describes exactly what users edit and regenerate.
