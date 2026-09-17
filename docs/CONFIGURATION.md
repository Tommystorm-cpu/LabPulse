# LabPulse Configuration Reference

This guide explains how to describe a LabPulse installation: its sensors,
measurements, experiments, dashboards, notifications, and outputs. It begins
with a small example you can adapt, followed by the available settings.

For installation and operating instructions, use the
[Installation guide](INSTALLATION.md) and [User Guide](USER_GUIDE.md). The
settings here match this version of the source. If you've installed a released
package, use the documentation for that release.

## Contents

- [Before editing](#before-editing)
- [A few YAML basics](#a-few-yaml-basics)
- [A small complete configuration](#a-small-complete-configuration)
- [How the configuration fits together](#how-the-configuration-fits-together)
- [Top-level settings](#top-level-settings)
- [Dashboards and setups](#dashboards-and-setups)
- [Services](#services)
- [Measurements](#measurements)
- [Calculated measurements](#calculated-measurements)
- [Controlled outputs](#controlled-outputs)
- [Built-in drivers](#built-in-drivers)
- [Fake-hardware mode](#fake-hardware-mode)
- [Validation and generated files](#validation-and-generated-files)
- [Settings stored in Home Assistant](#settings-stored-in-home-assistant)
- [Complete examples](#complete-examples)

## Before editing

On your Raspberry Pi, your settings live in:

```text
~/labpulse-live/config.yaml
~/labpulse-live/config.d/**/*.yaml   when measurement files are used
```

Edit it with:

```bash
labpulse config
```

With no filenames, the command lets you choose `config.yaml`, edit an existing
measurement file, or create a new one. You can also name the files directly:

```bash
labpulse config config.yaml
labpulse config config.yaml config.d/triton-01-measurements.yaml
```

LabPulse edits temporary copies, validates the complete configuration, builds
the generated files, and only then applies the result. If validation fails, it
shows the source file and field which need attention rather than installing the
invalid edit.

The `config.yaml` in the GitHub repository is only the starter copied into a
new installation. Editing that file does not change an existing Pi.

Do not edit these generated files:

```text
~/labpulse-live/config.resolved.yaml
~/labpulse-live/config.fake.yaml
~/labpulse-live/compose.yaml
~/labpulse-live/homeassistant/config/configuration.yaml
~/labpulse-live/homeassistant/config/packages/labpulse_generated.yaml
~/labpulse-live/homeassistant/config/labpulse-*.yaml
```

They are replaced whenever LabPulse regenerates the deployment.

## A few YAML basics

YAML is a text format for settings. You don't need to learn all of it to use
LabPulse, but spacing matters. Here's a small **fragment**, not a complete
configuration:

```yaml
setups:
  compressed_air:
    label: Compressed Air
```

`setups` is the section. `compressed_air` is the ID of one setup, and its
indented `label` is the name you'll see on the dashboard.

- Use spaces, not tabs. The examples use two spaces for each level.
- Keep entries at the same level aligned. A second setup would line up with
  `compressed_air`, not with `label`.
- Keep the colon and the space after it in settings such as `label: Compressed Air`.
- IDs such as `compressed_air` use lowercase letters, numbers, and underscores.
  Labels can have spaces and capitals. Change the label to rename a displayed
  item without giving it a new identity.
- `true` and `false` are switches; write them without quotes. Put phone numbers
  and text such as `"°C"` in quotes, as shown in the examples.
- A list such as `setups: [compressed_air]` means this reading belongs to that
  setup. Several IDs can be separated with commas inside the brackets.
- Text after `#` is a comment for you; LabPulse ignores it.

When adding a fragment to an existing file, put it inside the matching section.
For example, add a new service under the existing `services:` heading; don't
create a second `services:` heading. A **complete example** contains everything
needed for that example installation. Replacing a lab's existing file with one
would also remove the lab's other settings.

Open your settings with `labpulse config`. If the editor is nano, press
**Ctrl+O**, then **Enter** to save, and **Ctrl+X** to exit. Other editors use
their own save and exit controls. LabPulse then checks the files together. If
it rejects a change, read the file and field it names, correct the mistake,
and try again.

For a worked example, follow [Connect your first sensor](FIRST_SENSOR.md).

## A small complete configuration

Here's a complete example for one Arduino pressure monitor:

```yaml
timezone: Europe/London

mqtt:
  broker: mosquitto

sms:
  dry_run: true

setups:
  compressed_air:
    label: Compressed Air

services:
  pressure_monitor:
    label: Pressure Monitor
    driver:
      type: labpulse.serial_pipe
      options:
        port: /dev/serial/by-id/replace-with-the-real-device
    measurements:
      pressure:
        setups: [compressed_air]
        unit: bar
        device_class: pressure
```

The important relationships are:

- `pressure_monitor` is one physical service and one container;
- `labpulse.serial_pipe` tells it how to read the hardware;
- `pressure` must match the name produced by the Arduino;
- `compressed_air` controls where the measurement appears on the dashboard;
- `mosquitto` is the broker hostname used inside the generated containers;
- SMS remains harmless because `dry_run` is `true`.

This same file works in fake-hardware mode without the serial device. LabPulse
keeps the service and measurement but substitutes simulated values at runtime.

## How the configuration fits together

The main sections are:

```yaml
timezone: Europe/London
mqtt: {}
sms: {}
service_health: {}
dashboards: {}
setups: {}
services: {}
outputs: {}
custom_measurements: {}
```

| Section | Purpose | Required? |
|---|---|---|
| `timezone` | Display timezone for Home Assistant and containers | No; defaults to `Europe/London` |
| `mqtt` | Internal broker connection and optional external listener | Yes |
| `sms` | Dry-run or modem delivery and recipient lists | No; defaults to safe dry-run |
| `service_health` | Default whole-service failure timing | No |
| `dashboards` | Optional extra Home Assistant tabs | No |
| `setups` | Logical experiments or monitored systems | Yes |
| `services` | Physical or network measurement sources | Yes |
| `outputs` | Optional independently controlled outputs | No |
| `custom_measurements` | Optional Home Assistant calculations | No |

Mappings use stable IDs as their keys. IDs must contain lowercase letters,
numbers, and underscores, for example `pressure_monitor`. Labels are the
human-readable names displayed in Home Assistant, for example `Pressure
Monitor`.

Changing a label keeps the existing identity and history. Changing an ID
creates new container, MQTT, entity, helper, or history identities. Choose IDs
carefully and avoid renaming them after commissioning.

Unknown fields are rejected. YAML duplicate keys are also rejected instead of
silently allowing the later value to replace the earlier one.

## Top-level settings

### Timezone

```yaml
timezone: America/New_York
```

Use a valid IANA timezone such as `Europe/London`, `America/New_York`,
`Asia/Tokyo`, or `Australia/Sydney`. Find the available names on the Pi with:

```bash
timedatectl list-timezones
```

LabPulse passes this timezone to Home Assistant and its containers. The Pi host
should use the same timezone. NTP synchronises the underlying clock; the
timezone determines how timestamps are displayed.

### MQTT

The normal generated deployment uses:

```yaml
mqtt:
  broker: mosquitto
  port: 1883
```

| Field | Default | Meaning |
|---|---:|---|
| `broker` | required | Broker hostname used inside LabPulse containers |
| `port` | `1883` | Broker port, from 1 to 65535 |
| `external_listener` | disabled | Optional authenticated TLS listener for other computers |

Use `mosquitto`, not `localhost`, for the standard container deployment.
Home Assistant uses host networking and is configured separately during
onboarding with `127.0.0.1:1883`.

#### External MQTT listener

An off-Pi publisher, such as a Triton control PC, can connect through a
separate TLS listener:

```yaml
mqtt:
  broker: mosquitto
  port: 1883
  external_listener:
    enabled: true
    bind_addresses:
      - 10.50.1.1
      - 10.50.2.1
    port: 8883
```

| Field | Default | Constraint |
|---|---:|---|
| `enabled` | `false` | Strict boolean |
| `bind_addresses` | `[0.0.0.0]` | One or more unique IPv4 addresses |
| `port` | `8883` | Host-facing TLS port, from 1 to 65535 |

`0.0.0.0` exposes the listener on every interface and cannot be combined with
specific addresses. Enabling the listener requires a server certificate,
private key, password database, and ACL. It never enables anonymous external
access. Follow the [Triton publisher guide](TRITON_PUBLISHER.md) for the full
network and certificate procedure.

### SMS

Begin with dry-run delivery:

```yaml
sms:
  dry_run: true
  recipients:
    - "+447700900000"
  test_recipients:
    - "+447700900001"
```

| Field | Default | Meaning |
|---|---:|---|
| `dry_run` | `true` | Validate and log requests without using a modem |
| `recipients` | `[]` | Numbers used when Home Assistant Test mode is off |
| `test_recipients` | `[]` | Numbers used when Test mode is on |

Numbers must use international `+` format followed by 8 to 15 digits. Empty or
duplicate entries within a list are rejected. At least one normal recipient is
required when `dry_run` is `false`.

Recipient lists belong in the private live configuration, not in a public Git
commit. See [Testing SMS](USER_GUIDE.md#testing-sms) before enabling real
delivery.

### Whole-service health

These defaults prevent a brief disconnect from immediately becoming an
incident:

```yaml
service_health:
  offline_confirm_seconds: 10
  recovery_confirm_seconds: 15
```

Both values accept 1 to 3600 seconds. They apply to complete service outages,
not individual missing readings or numeric threshold alarms.

A service can override either value while inheriting the other:

```yaml
services:
  triton_01:
    # Other service fields omitted here.
    service_health:
      offline_confirm_seconds: 120
```

## Dashboards and setups

### Extra dashboard tabs

The built-in `main` dashboard contains the Monitor view. Add another tab only
when the installation has enough setups to benefit from one:

```yaml
dashboards:
  pump_systems:
    label: Pump Systems
    icon: mdi:water-pump
    order: 10
```

| Field | Default | Meaning |
|---|---:|---|
| `label` | readable form of ID | Tab title |
| `icon` | `mdi:view-dashboard-outline` | Material Design icon |
| `order` | `100` | Order from 0 to 10000 |

Dashboard IDs use lowercase letters, numbers, and underscores. `main` is
reserved and must not be declared. Custom tabs appear after Monitor and before
Alarm Setup.

### Logical setups

A setup represents an experiment, room, utility, or other useful operator
group. It does not need to match the physical sensor wiring:

```yaml
setups:
  compressed_air:
    label: Compressed Air
    icon: mdi:gauge
    order: 10
    dashboard: main

  turbo_pump_experiment:
    label: Turbo Pump Experiment
    icon: mdi:snowflake-thermometer
    order: 20
    dashboard: pump_systems
```

| Field | Default | Meaning |
|---|---:|---|
| `label` | readable form of ID | Display name |
| `icon` | `mdi:flask-outline` | Material Design icon |
| `order` | `100` | Position from 0 to 10000 |
| `dashboard` | `main` | Built-in Monitor or a declared custom dashboard ID |

Ordinary measurements must belong to at least one declared setup. One
measurement can appear in several setups without duplicating its MQTT entity,
history, or alarm state.

## Services

Each entry under `services` is one independent acquisition worker and normally
one container:

```yaml
services:
  pressure_monitor:
    enabled: true
    label: Compressed Air Sensor Hub
    notify_on_service_failure: true
    driver:
      type: labpulse.serial_pipe
      options:
        port: /dev/serial/by-id/usb-example
        baud_rate: 9600
    measurement_defaults:
      setups: [compressed_air]
    measurements:
      pressure:
        unit: bar
        device_class: pressure
    reconnect_interval_seconds: 5
    maximum_measurement_age_seconds: 300
```

| Field | Default | Meaning |
|---|---:|---|
| `enabled` | `true` | Whether the worker is included in the deployment |
| `label` | required | Operator-facing service and device name |
| `notify_on_service_failure` | `true` | Send service-offline and recovery notifications |
| `driver` | required | Registered driver type and its options |
| `measurement_defaults` | absent | Values inherited by every measurement in this service |
| `measurements` | required* | Inline measurement mapping |
| `measurements_file` | absent* | Measurement mapping stored beneath `config.d` |
| `reconnect_interval_seconds` | `5` | Delay before reconnecting; must be greater than zero |
| `read_interval_seconds` | driver default | Central sampling interval; must be greater than zero |
| `maximum_measurement_age_seconds` | `300` | Freshness and MQTT expiry limit, 2 to 86400 seconds |
| `service_health` | global defaults | Optional outage/recovery timing overrides |
| `power_detection` | absent | Composite power-outage behaviour for a power service |

Define exactly one of `measurements` and `measurements_file`. Deployment
generation requires at least one enabled service.

Set `notify_on_service_failure: false` for a deliberately disconnected or
known-unreliable service when its status should remain visible without sending
whole-service outage messages. This does not disable its reading or power
alarms.

`read_interval_seconds` normally does not need to be supplied. The built-in
driver chooses a sensible default. `reconnect_interval_seconds` controls how
soon a failed device is tried again; `maximum_measurement_age_seconds` controls
when its last reading becomes stale.

### Reusing measurement settings

Use `measurement_defaults` to avoid repeating common values:

```yaml
measurement_defaults:
  setups: [pump_room]
  alarmed: true
  required: true
  unit: "°C"
  device_class: temperature
measurements:
  supply_temperature:
    label: Supply Temperature
  return_temperature:
    label: Return Temperature
  pressure:
    label: Water Pressure
    unit: bar
    device_class: pressure
```

An explicitly supplied measurement field overrides the shared default.
`measurement_defaults` accepts the ordinary display, setup, alarm, freshness,
unit, precision, graph, class, icon, and state-class fields. Driver-specific
`source`, `gpio_line`, and `active_high` remain on individual measurements.

### Moving measurements into `config.d`

Large lists, especially exact Triton logfile headers, can live in a separate
file:

```yaml
services:
  triton_01:
    label: Triton 1
    driver:
      type: labpulse.mqtt_json
      options:
        topic: labpulse/triton/triton-01/measurements
    measurement_defaults:
      setups: [cryogenics_room]
    measurements_file: config.d/triton-01-measurements.yaml
```

The fragment contains the mapping itself, without a surrounding
`measurements:` key:

```yaml
mixing_chamber_temperature:
  source: "Mixing Chamber T(K)"
  unit: K
  device_class: temperature

cold_plate_temperature:
  source: "Cold Plate T(K)"
  unit: K
  device_class: temperature
```

The path must:

- be relative to `config.yaml`;
- remain beneath `config.d`;
- end in `.yaml` or `.yml`;
- name a regular, non-symlink file;
- contain a non-empty measurement mapping.

Absolute paths, `..`, symlinks, nested include directives, duplicate keys, and
files outside `config.d` are rejected. Fragments are only available for
physical service measurements; all other sections remain in `config.yaml`.

## Measurements

A measurement is one named numeric value produced by a service:

```yaml
measurements:
  pressure:
    label: Compressed Air Pressure
    short_label: Pressure
    setups: [compressed_air]
    alarmed: true
    required: true
    missing_confirm_seconds: 60
    recovery_confirm_seconds: 15
    unit: bar
    precision: 2
    show_graph: true
    device_class: pressure
    icon: mdi:gauge
    state_class: measurement
```

The mapping key, here `pressure`, is the stable measurement ID. Its order in
the YAML is preserved on generated dashboards.

| Field | Default | Meaning |
|---|---:|---|
| `source` | driver-specific | Exact external name required by `labpulse.mqtt_json` |
| `label` | readable form of ID | Full dashboard and notification label |
| `short_label` | `label` | Compact label used beneath a setup heading |
| `setups` | required for ordinary readings | Non-empty list of declared setup IDs |
| `alarmed` | `true` | Create threshold controls and notifications |
| `required` | `true` | Treat missing data as a condition needing attention |
| `missing_confirm_seconds` | `60` | Missing time before an incident, 1 to 86400 seconds |
| `recovery_confirm_seconds` | `15` | Usable-data time before recovery, 0 to 3600 seconds |
| `unit` | none | Exact unit published and displayed |
| `precision` | none | Display suggestion from 0 to 10 decimal places |
| `show_graph` | `false` | Show a 24-hour graph instead of the compact row |
| `device_class` | none | LabPulse semantic group and default-icon choice |
| `icon` | derived | Optional explicit `mdi:` icon |
| `state_class` | `measurement` | Home Assistant statistics metadata; may be `null` |
| `gpio_line` | driver-specific | GPIO input line, 0 to 53 |
| `active_high` | driver-specific | GPIO input polarity; defaults to `true` for that driver |

Measurement IDs use lowercase letters, numbers, and underscores. Labels and
units are display text; they do not change the numeric value.

`precision` affects Home Assistant display metadata for physical readings. It
does not round their MQTT value, stored history, alarm input, or detailed
history graph. Calculated measurement precision does round the calculated
result itself.

Set `alarmed: false` for informational telemetry which should stay visible and
recorded without threshold helpers or threshold messages. Whole-service health
and required-reading behaviour remain separate.

Set `required: false` when absence is acceptable. When missing, the reading is
shown as **No recent data — optional**, does not open a missing-reading
incident, and is excluded from the required-reading service-health check. It
does not suppress driver faults: the MQTT JSON driver, for example, reports
`missing_measurements` when any mapped field is missing or invalid, including
optional fields. That fault makes the service show **Needs attention** while
usable fields continue updating. This setting does not disable an ordinary
numeric threshold alarm while valid data is available.

### Units, classes, and icons

For physical readings, LabPulse publishes `unit` exactly as written. It does
not expose the configured `device_class` as Home Assistant's convertible device class, so
Home Assistant will not silently convert Celsius to Fahrenheit or bar to psi.

LabPulse uses `device_class` to group similar measurements in the alarm editor
and choose a default icon:

| Class | Default icon |
|---|---|
| `battery` | `mdi:battery` |
| `current` | `mdi:current-dc` |
| `energy` | `mdi:lightning-bolt-circle` |
| `humidity` | `mdi:water-percent` |
| `power` | `mdi:lightning-bolt` |
| `pressure` | `mdi:gauge` |
| `signal_strength` | `mdi:wifi` |
| `temperature` | `mdi:thermometer` |
| `voltage` | `mdi:flash` |
| `volume_flow_rate` | `mdi:pipe-valve` |

Unknown or omitted classes use `mdi:chart-line`. An explicit `mdi:` icon
overrides the default. Calculated measurements use a different Home Assistant
template-sensor path, described below.

## Calculated measurements

Home Assistant can calculate a new measurement from physical LabPulse
readings:

```yaml
custom_measurements:
  temperature_difference:
    label: Water Temperature Difference
    short_label: Temperature Difference
    setups: [pump_room]
    inputs:
      supply: pump_room_hub.supply_temperature
      return_temp: pump_room_hub.return_temperature
    constants:
      scale: 1.0
    formula: (return_temp - supply) * scale
    precision: 2
    show_graph: true
    alarmed: true
    required: true
    unit: "°C"
    icon: mdi:delta
```

Each input maps a short local name to an existing physical
`service.measurement`. Calculated measurements cannot depend on other
calculated measurements. Every declared input and constant must be used.

The formula language supports finite numbers, names, parentheses, unary `+`
and `-`, and the `+`, `-`, `*`, and `/` operators. Function calls, powers,
attribute access, indexing, and arbitrary Python or Jinja are rejected.

| Field | Default | Meaning |
|---|---:|---|
| `label` | readable form of ID | Full label |
| `short_label` | `label` | Compact dashboard label |
| `setups` | required | One or more declared setup IDs |
| `inputs` | required | Local names mapped to distinct physical readings |
| `constants` | `{}` | Named finite numbers used by the formula |
| `formula` | required | Restricted arithmetic expression |
| `precision` | `2` | Result rounding from 0 to 10 decimal places |
| `show_graph` | `false` | Show a 24-hour graph |
| `alarmed` | `true` | Create normal threshold controls |
| `required` | `true` | Treat an unavailable result as missing required data |
| `missing_confirm_seconds` | `60` | Missing confirmation, 1 to 86400 seconds |
| `recovery_confirm_seconds` | `15` | Recovery confirmation, 0 to 3600 seconds |
| `unit` | none | Unit declared on the generated Home Assistant result sensor |
| `device_class` | none | LabPulse semantic group and Home Assistant device class |
| `icon` | none | Explicit `mdi:` icon; otherwise Home Assistant chooses the entity icon |
| `state_class` | `measurement` | Home Assistant statistics metadata; may be `null` |

Unlike physical MQTT readings, calculated sensors expose `device_class` to
Home Assistant. Its unit conversion and class/unit compatibility rules can
therefore apply. LabPulse does not assign the physical-reading fallback icon
to these sensors. Omit `device_class` when the result should not be treated as
that Home Assistant quantity, and set `icon` explicitly when needed. For
example, a temperature difference is not an absolute temperature; omit
`device_class: temperature` if the result must stay in its declared unit.

Input and constant names use lowercase letters, numbers, and underscores and
cannot be Python keywords or the reserved names `true`, `false`, `none`,
`null`, `states`, or `is_number`. Inputs and constants cannot share a name.
Formulas are limited to 500 characters and 100 parsed elements.

The result becomes unavailable when an input is unavailable or non-numeric, or
when a divisor evaluates to zero. The service ID `custom` is reserved whenever
custom measurements exist, and physical service IDs cannot collide with the
generated `custom_<measurement-id>` alarm identities.

## Controlled outputs

Outputs are separate from read-only services. Each enabled output becomes one
worker container and one Home Assistant switch:

```yaml
outputs:
  cooling_valve_enable:
    label: Cooling Valve Enable
    icon: mdi:valve
    setups: [turbo_pump_experiment]
    driver:
      type: labpulse.gpio_output
      options:
        gpio_chip: /dev/gpiochip0
        gpio_line: 18
        active_high: true
        safe_state: false
    reconnect_interval_seconds: 5
    maximum_active_seconds: 300
```

| Field | Default | Meaning |
|---|---:|---|
| `enabled` | `true` | Include the output worker |
| `label` | required | Switch and device label |
| `icon` | `mdi:toggle-switch` | Home Assistant icon |
| `setups` | omitted | One or more setups whose Controls cards contain the switch |
| `driver` | required | Output-capable driver and options |
| `reconnect_interval_seconds` | `5` | Retry delay, greater than 0 and at most 3600 seconds |
| `maximum_active_seconds` | none | Optional automatic ON limit, up to 86400 seconds |

Unassigned outputs appear in the general Controlled Outputs section. Assigned
outputs appear in every selected setup. All enabled outputs appear on System
Status. Omit `setups` for an unassigned output; if you provide the field, it
must contain at least one setup ID.

Output IDs use lowercase letters, numbers, and underscores. An enabled output
cannot claim a GPIO line already used by another enabled LabPulse service or
output.

`maximum_active_seconds` requires `safe_state: false`. The timer begins with a
logical ON command and repeated ON commands do not extend it. See the
[controlled-output safety notes](USER_GUIDE.md#using-controlled-outputs) before
connecting equipment.

## Built-in drivers

Every service selects one driver under `driver.type`. Only options declared by
that driver are accepted.

### Standard serial pipe

```yaml
driver:
  type: labpulse.serial_pipe
  options:
    port: /dev/serial/by-id/usb-example
    baud_rate: 9600
```

| Option | Default | Constraint |
|---|---:|---|
| `port` | required | Non-blank serial path |
| `baud_rate` | `9600` | Positive integer |

Use stable `/dev/serial/by-id/...` paths for real boards. The Arduino sends one
newline-terminated record such as:

```text
pressure:1.02|temperature:21.4|humidity:48.2
```

Measurement IDs must match the lower-case names sent by the firmware. Units
belong in the LabPulse configuration, not in the serial record. The driver
blocks while reading and therefore uses a default runner interval of zero. See
the [firmware guide](../firmware/README.md) for the complete wire contract.

The serial driver can also feed LabPulse's installation-wide power monitor.
This is mainly useful for a serial UPS simulator or a board that emits the same
three readings as the X1200 integration:

```yaml
services:
  ups_monitor:
    label: UPS Monitor
    driver:
      type: labpulse.serial_pipe
      options:
        port: /dev/serial/by-id/usb-example-ups
    measurements:
      voltage:
        unit: V
        device_class: voltage
      battery_level:
        unit: "%"
        device_class: battery
      mains_present:
        state_class: null
    power_detection:
      outage_confirm_seconds: 3
      restore_confirm_seconds: 5
```

When `power_detection` is present, the service must provide measurements named
exactly `voltage`, `battery_level`, and `mains_present`. The power-monitor rules
described in the X1200 section below then apply in exactly the same way.

### Named JSON over MQTT

Use `labpulse.mqtt_json` when another computer publishes named values:

```yaml
services:
  triton_01:
    label: Triton 1
    driver:
      type: labpulse.mqtt_json
      options:
        broker: mosquitto
        port: 1883
        topic: labpulse/triton/triton-01/measurements
        heartbeat_topic: labpulse/triton/triton-01/heartbeat
        heartbeat_timeout_seconds: 60
        maximum_record_age_seconds: 30
    measurement_defaults:
      setups: [cryogenics_room]
    measurements:
      cold_plate_temperature:
        source: "Cold Plate T(K)"
        unit: K
        device_class: temperature
```

| Option | Default | Constraint |
|---|---:|---|
| `broker` | `mosquitto` | Non-blank hostname |
| `port` | `1883` | 1 to 65535 |
| `topic` | required | Exact non-wildcard measurement topic |
| `maximum_record_age_seconds` | `300` | Accepted source age, 2 to 86400 seconds |
| `heartbeat_topic` | absent | Optional exact topic ending in `/heartbeat` |
| `heartbeat_timeout_seconds` | `60` | 2 to 3600 seconds; requires a heartbeat topic |

Every measurement requires a non-blank, case-sensitive, unique `source`. Other
drivers reject this field because they already produce stable measurement IDs.

The publisher sends versioned JSON:

```json
{
  "protocol": "labpulse.measurements",
  "version": 1,
  "recorded_at": 1700000000,
  "measurements": {
    "Cold Plate T(K)": 0.0857
  }
}
```

`recorded_at` is the current Unix timestamp. Messages are limited to 1,000,000
bytes, must use protocol version 1, may be at most 60 seconds in the future,
and must contain at least one usable mapped finite number. Missing or invalid
individual fields create a partial fault while valid fields continue.

When a heartbeat is configured, LabPulse also derives the sibling
`/availability` topic. A new, non-retained `alive` heartbeat and retained
`online` availability establish publisher health. The driver polls for new
snapshots every 0.1 seconds and requests no host hardware access.

While waiting for that heartbeat, the raw service status is
`awaiting_heartbeat`. Heartbeat freshness and measurement freshness are
independent: an online publisher can have expired readings, and heartbeats do
not refresh those readings. With heartbeat monitoring enabled, missing samples
alone do not cause reconnects. Without it, the runner uses successful readings
to establish health and reconnects when they become too old.

### Generic GPIO input

One service can own several lines on the same chip:

```yaml
services:
  gpio_inputs:
    label: GPIO Inputs
    driver:
      type: labpulse.gpio_input
      options:
        gpio_chip: /dev/gpiochip0
    measurement_defaults:
      setups: [io_testing]
      state_class: null
    measurements:
      door_closed:
        gpio_line: 17
        active_high: true
      pump_running:
        gpio_line: 27
        active_high: false
```

The only driver option is `gpio_chip`, which defaults to `/dev/gpiochip0` and
must match `/dev/gpiochipN`. Each measurement requires a unique `gpio_line`
from 0 to 53. `active_high` defaults to `true`.

Inactive is published as `0.0` and active as `1.0`, so ordinary numeric alarm
thresholds can be used. The default interval is one second. This driver is for
stable digital states, not pulse counting or debouncing. GPIO line offsets are
not physical header-pin numbers.

### DHT11

```yaml
services:
  room_dht:
    label: Room DHT11
    driver:
      type: labpulse.dht11
      options:
        pin: D4
    measurement_defaults:
      setups: [room]
    measurements:
      temperature:
        unit: "°C"
        device_class: temperature
      humidity:
        unit: "%"
        device_class: humidity
```

`pin` is required and must be an uppercase Raspberry Pi/Blinka board name using
letters, numbers, and underscores. The driver publishes `temperature` and
`humidity` and defaults to a two-second interval. It needs privileged GPIO
device access.

### Sensirion SHT40

```yaml
driver:
  type: labpulse.sht40
  options:
    bus: 1
    address: 0x44
```

| Option | Default | Constraint |
|---|---:|---|
| `bus` | `1` | 0 to 255 |
| `address` | `0x44` | Fixed SHT40 address |

Declare measurements named `temperature` and `humidity`. The default interval
is two seconds, and the container receives only `/dev/i2c-<bus>`.

### Geekworm X1200 UPS

```yaml
services:
  ups_monitor:
    label: UPS Monitor
    driver:
      type: labpulse.x1200
      options:
        bus: 1
        address: 0x36
        gpio_chip: /dev/gpiochip0
        gpio_line: 6
        mains_present_active_high: true
    measurements:
      voltage:
        unit: V
        device_class: voltage
      battery_level:
        unit: "%"
        device_class: battery
      mains_present:
        state_class: null
    power_detection:
      outage_confirm_seconds: 3
      restore_confirm_seconds: 5
```

| Option | Default | Constraint |
|---|---:|---|
| `bus` | `1` | 0 to 255 |
| `address` | `0x36` | Fixed MAX17043 address |
| `gpio_chip` | `/dev/gpiochip0` | `/dev/gpiochipN` |
| `gpio_line` | `6` | 0 to 53 |
| `mains_present_active_high` | `true` | GPIO polarity |

An X1200 service requires measurements named exactly `voltage`,
`battery_level`, and `mains_present`, plus `power_detection`. Its read interval
must be omitted or set to `1`.

Dedicated power measurements omit `setups`; Home Assistant displays them as one
installation-wide power monitor. All three must use the same `alarmed` value.
Set all three to `alarmed: false` to retain the raw readings without the
composite power alarm. Outage and restoration confirmation values accept 1 to
3600 seconds.

### Generic GPIO output

This driver is valid only under the top-level `outputs` section:

```yaml
driver:
  type: labpulse.gpio_output
  options:
    gpio_chip: /dev/gpiochip0
    gpio_line: 18
    active_high: true
    safe_state: false
```

| Option | Default | Constraint |
|---|---:|---|
| `gpio_chip` | `/dev/gpiochip0` | `/dev/gpiochipN` |
| `gpio_line` | required | 0 to 53 |
| `active_high` | `true` | Electrical high means logical ON |
| `safe_state` | `false` | Logical state used without command authority |

The output container receives only the configured GPIO chip. Electrical
isolation, level conversion, load switching, flyback protection, and a physical
pull resistor remain installation responsibilities.

## Fake-hardware mode

Fake hardware uses the same `config.yaml` and optional `config.d` fragments as
real hardware. Do not create fake-only services, ports, or measurements.

When the installation is in fake-hardware mode, LabPulse:

- retains every enabled sensor and output container;
- publishes a sensible changing value for every configured measurement;
- keeps calculated measurements and dashboards unchanged;
- stores output state only in memory;
- forces SMS into dry-run mode;
- gives workers no configured hardware mounts or devices.

`labpulse config` detects the active mode and regenerates both
`config.resolved.yaml` and `config.fake.yaml` while preserving it. Never edit
`config.fake.yaml` directly.

## Validation and generated files

The supported application workflow is always:

```bash
labpulse config
```

LabPulse validates:

- YAML syntax and duplicate keys;
- top-level, service, measurement, output, and driver fields;
- stable IDs and cross-references;
- `config.d` paths and contents;
- driver-specific measurement requirements;
- GPIO line ownership across enabled workers;
- formula names and operations;
- generated Compose and Home Assistant output.

The complete resolved source is written to `config.resolved.yaml`. Containers
receive that one standalone document rather than the fragments. A fake runtime
is derived separately when needed.

Use `labpulse doctor` for read-only checks after configuration. Direct generator
commands are intended for development and do not replace the guarded editor's
staging, rollback, and deployment refresh.

## Settings stored in Home Assistant

These operator settings are deliberately not YAML fields:

- alarm mode;
- minimum and maximum thresholds;
- observation-window length;
- required danger percentage;
- recovery time and deadband;
- global, setup, reading, and power mutes;
- notification Test mode.

They are edited on the generated **Alarm Setup** dashboard and stored in Home
Assistant state. See [Configuring alarms](USER_GUIDE.md#configuring-alarms).

Changing a YAML label preserves those helper identities. Changing a service,
measurement, setup, output, or custom-measurement ID can create new helpers and
leave old Home Assistant entities behind. Back up the installation before an
intentional identity change.

## Complete examples

These repository examples are complete configurations validated by the test
suite:

| File | Demonstrates |
|---|---|
| [minimal-serial.yaml](examples/minimal-serial.yaml) | One standard serial pressure reading |
| [calculated-measurement.yaml](examples/calculated-measurement.yaml) | Two physical readings, a calculation, setup grouping, and a custom tab |
| [mqtt-input.yaml](examples/mqtt-input.yaml) | External MQTT field mapping and publisher health |

They use dry-run SMS and no active physical outputs. Treat them as examples,
not replacements for an existing live configuration. The full starter
configuration at the repository root demonstrates the complete Laird Group
layout.
