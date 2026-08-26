# Configuration reference

The installed source of truth is:

```text
~/labpulse-live/config.yaml
```

The repository `config.yaml` is copied only when setup creates a new
installation. Never edit it expecting an existing Pi to change.

For a real-hardware installation, use the guarded editor:

```bash
labpulse config
```

## Source and runtime configuration

There is one operator-owned source and, in fake mode, one derived runtime
projection:

| Path | Ownership | Purpose |
|---|---|---|
| `~/labpulse-live/config.yaml` | Operator | Permanent service, measurement, setup, dashboard, MQTT, and SMS configuration |
| `~/labpulse-live/config.fake.yaml` | Generated | Fake-USB transport substitutions used by simulated containers |
| repository `config.yaml` | Package | Starter copied only when a live source does not exist |

Real Compose mounts `config.yaml` into Python containers as
`/app/config.yaml`. Fake Compose mounts `config.fake.yaml` at that same
container path. Hardware and SMS processes therefore use one stable internal
path regardless of runtime mode.

Home Assistant generation uses the active runtime document. Fake derivation
preserves service and measurement names, so both modes produce the same public
entity and alarm identities.

## Top-level structure

```yaml
mqtt:
  broker: mosquitto
  port: 1883

sms:
  dry_run: true
  recipients: []
  test_recipients: []

service_health:
  fault_confirm_seconds: 10
  recovery_confirm_seconds: 15

dashboards: {}
setups: {}
services: {}
custom_measurements: {}
```

Configuration is validated with Pydantic before generation and service startup.
Unknown driver IDs, invalid driver options, missing setup references, unstable
measurement IDs, unknown fields, and invalid timing values fail early. File,
YAML, schema, driver, and option failures are reported through one error format
that includes the source path and field location.

Each command or service validates its selected configuration once at startup.
Driver options are typed as part of that load; Compose, Home Assistant,
hardware, SMS, and diagnostics do not validate or reinterpret them again.

The same validated document is consumed differently:

| Consumer | Reads from the document |
|---|---|
| Compose generator | enabled services, runtime image inputs, driver resources, SMS mode |
| Hardware CLI | one selected service, its typed driver options, MQTT settings |
| Home Assistant generator | enabled services, dashboards, setups, physical and custom measurements, health and power timing |
| SMS CLI | MQTT settings, delivery mode, normal and test recipients |
| Doctor | source/runtime agreement, enabled services, declared host resources |

## MQTT

```yaml
mqtt:
  broker: mosquitto
  port: 1883
```

`broker` is the address used by LabPulse Python containers. In the generated
Compose deployment it must be `mosquitto`, not `localhost`.

`port` must be between 1 and 65535. The standard generated deployment uses
1883.

Home Assistant is different because it uses host networking. Its MQTT
integration connects to `127.0.0.1:1883`.

## SMS

```yaml
sms:
  dry_run: true
  recipients:
    - "+447700900000"
  test_recipients:
    - "+447700900001"
```

- `dry_run` defaults to `true`. Requests are validated and logged without using
  a modem.
- `recipients` receive normal live alerts.
- `test_recipients` receive requests created while Home Assistant Test mode is
  enabled.
- Numbers use international `+` format with 8 to 15 digits.
- Empty and duplicate numbers are rejected within each list.
- At least one normal recipient is required when `dry_run` is `false`.

Use example numbers in committed configuration. See [SMS](SMS.md).

## Whole-service health

```yaml
service_health:
  fault_confirm_seconds: 10
  recovery_confirm_seconds: 15
```

These values confirm a complete hardware-service fault and recovery before
Home Assistant changes its hub-level state.

Both values accept 1 to 3600 seconds. They are separate from:

- driver reconnect timing;
- per-measurement MQTT expiry;
- ordinary measurement alarm observation and recovery settings.

## Dashboard tabs

The built-in `main` dashboard is the Monitor tab. Declare additional operator
tabs only when setups need to be split across separate views:

```yaml
dashboards:
  pump_systems:
    label: Pump Systems
    icon: mdi:water-pump
    order: 10
```

Dashboard IDs use lowercase letters, numbers, and underscores. The ID `main`
is reserved and does not need to be declared. Custom dashboards are ordered by
`order`, then ID, and always appear after Monitor and before Alarm Setup. Their
tabs show both the configured icon and label.

| Field | Default | Meaning |
|---|---:|---|
| `label` | readable form of ID | Dashboard tab title |
| `icon` | `mdi:view-dashboard-outline` | Material Design tab icon |
| `order` | `100` | Ordering among custom dashboards from 0 to 10000 |

## Logical setups

Setups group measurements by experiment or monitored system independently of
the physical sensor hub:

```yaml
setups:
  compressed_air:
    label: Compressed Air
    icon: mdi:gauge
    order: 10
    dashboard: main
```

Setup IDs are stable identifiers containing lowercase letters, numbers, and
underscores. Changing an ID changes generated helper and dashboard identities.

Fields:

| Field | Default | Meaning |
|---|---:|---|
| `label` | readable form of ID | Display text |
| `icon` | `mdi:flask-outline` | Material Design icon |
| `order` | `100` | Dashboard ordering from 0 to 10000 |
| `dashboard` | `main` | Built-in main tab or a declared custom dashboard ID |

An ordinary measurement must select at least one declared setup. One
measurement may appear in several setups without creating duplicate MQTT
entities or alarm state.

## Services

Each key under `services` describes one independently running hardware service:

```yaml
services:
  pressure_monitor:
    label: Compressed Air and Environment Sensor Hub
    driver:
      type: labpulse.serial_pipe
      options:
        port: /dev/serial/by-id/usb-example
        baud_rate: 9600
    measurements:
      pressure:
        label: Pressure
        setups: [compressed_air]
        unit: bar
        device_class: pressure
      temperature:
        label: Main Lab Temperature
        short_label: Temperature
        group: Environment
        setups: [compressed_air]
        unit: "°C"
        device_class: temperature
      humidity:
        label: Main Lab Humidity
        short_label: Humidity
        group: Environment
        setups: [compressed_air]
        unit: "%"
        device_class: humidity
```

Service keys are stable IDs used in container names, MQTT topics, devices, and
entity IDs. Choose a lowercase underscore-separated name and do not rename it
after collecting history unless a new identity is intended.

| Field | Default | Meaning |
|---|---:|---|
| `enabled` | `true` | Whether generation creates the service |
| `label` | required | Home Assistant device and operator-facing service label |
| `driver` | required | Driver ID and driver-owned options |
| `measurements` | required | Ordered mapping of stable measurement IDs to their settings |
| `reconnect_interval_seconds` | `5` | Delay before connection retry; greater than 0 |
| `read_interval_seconds` | driver default | Central polling interval; greater than 0 when set |
| `maximum_measurement_age_seconds` | `300` | MQTT expiry/freshness limit, 2 to 86400 |
| `power_detection` | absent | Dedicated power-outage confirmation |

Each enabled service becomes `labpulse-<service-slug>` in Compose.
Deployment generation requires at least one enabled hardware service.
Service keys that normalize to the same Compose slug are rejected.

The starter `pressure_monitor` represents one Arduino reading the compressed-
air pressure transducer and an SHT40. Its firmware emits `pressure`,
`temperature`, and `humidity` together through the standard serial pipe. The
separate `room_environment` starter service represents the other SHT40 wired
directly to the Raspberry Pi over I2C.

## Measurements

```yaml
measurements:
  temperature:
    label: Cryogenics Room Temperature
    short_label: Room Temperature
    group: Environment
    setups: [cryogenics_room]
    unit: "°C"
    device_class: temperature
    icon: mdi:snowflake-thermometer
```

| Field | Default | Meaning |
|---|---|---|
| mapping key | required | Stable driver, MQTT, and entity ID; lowercase letters, numbers, and underscores |
| `label` | readable form of ID | Full label used for MQTT discovery, Diagnostics, active problems, helpers, and notifications |
| `short_label` | `label` | Shorter label used where the dashboard's setup heading supplies context |
| `group` | none | Presentation grouping within a setup |
| `setups` | required for ordinary values | One or more logical setup IDs |
| `alarmed` | `true` | Whether to generate measurement alarm state, controls, and notifications |
| `unit` | none | Exact published unit |
| `device_class` | none | LabPulse semantic category and default-icon source |
| `icon` | derived | Explicit `mdi:` override |
| `state_class` | `measurement` | Home Assistant statistics metadata; may be `null` |

Measurement IDs are mapping keys, so they are inherently unique and preserve
their YAML order. Hardware readings not listed in `measurements` are ignored.

Changing `label`, `short_label`, or `group` preserves identity. Changing a
measurement mapping key creates a new MQTT topic, Home Assistant entity, alarm helpers, and
history.

Use `label` to keep a measurement unambiguous when it appears without its
logical setup heading. Add `short_label` only when that heading makes a
shorter name clearer. For example, `Triton 1 Temperature In` can appear as
`Temperature In` within the `Triton 1` dashboard group.

Set `alarmed: false` for informational telemetry that should remain published
and visible on operator dashboards and Diagnostics without measurement alarm
helpers, threshold controls, active-problem rows, or notifications. Whole-
service health monitoring remains separate. Dedicated power readings form one
composite outage alarm, so every measurement in a `power_detection` service
must use the same `alarmed` value.

## Custom measurements

Custom measurements are calculated by Home Assistant from one or more physical
LabPulse measurements. They do not run in hardware containers and do not
publish another MQTT topic.

```yaml
custom_measurements:
  pump_room_temperature_difference:
    label: Pump Room Temperature Difference
    short_label: Temperature Difference
    group: Calculated
    setups: [pump_room_system]
    inputs:
      supply: pump_room.temp0
      return_temp: pump_room.temp1
    constants:
      scale: 1.0
    formula: (return_temp - supply) * scale
    unit: "°C"
    device_class: temperature
    icon: mdi:delta
```

Each key below `inputs` is a short formula name. Its value must be an existing
physical `service.measurement` reference. At least one input is required,
every declared input must appear in the formula, and a custom
measurement cannot use another custom measurement as an input. This keeps the
calculation graph flat and makes faults traceable to hardware.

The formula language deliberately supports only numeric literals, input and
constant names, parentheses, unary `+`/`-`, and the `+`, `-`, `*`, and `/`
operators. Function calls, attributes, powers, and arbitrary Python or Jinja
are rejected during configuration validation. Constants are optional finite
numbers and must be used when declared.

| Field | Default | Meaning |
|---|---:|---|
| `label` | readable form of custom ID | Full display and notification label |
| `short_label` | `label` | Compact setup-dashboard label |
| `group` | none | Presentation grouping within a setup |
| `setups` | required | One or more logical setup IDs |
| `inputs` | required | One or more alias-to-physical-measurement references |
| `constants` | `{}` | Named finite numbers available to the formula |
| `formula` | required | Restricted arithmetic expression |
| `precision` | `2` | Result rounding from 0 to 10 decimal places |
| `alarmed` | `true` | Whether to create the normal threshold alarm controls |
| `unit` | none | Result unit shown by Home Assistant |
| `device_class` | none | Result semantic category and threshold-editor hint |
| `icon` | none | Optional explicit `mdi:` icon |
| `state_class` | `measurement` | Home Assistant statistics metadata; may be `null` |

The resulting entity is `sensor.labpulse_custom_<custom-id>`. It is unavailable
when any physical input is unavailable or non-numeric, or when a divisor
evaluates to zero. Physical readings retain ownership of sensor-fault alerts;
an unavailable dependency pauses and clears the custom threshold state without
sending a duplicate custom sensor-fault notification. Once inputs recover,
normal observation-window alarm evaluation resumes.

The service ID `custom` is reserved whenever custom measurements are present.

### Units and icons

LabPulse publishes the configured `unit` exactly and deliberately omits Home
Assistant's convertible sensor `device_class` from MQTT discovery. Home
Assistant therefore does not convert Celsius to Fahrenheit or bar to psi.

The configured `device_class` remains internal LabPulse metadata and selects a
default icon:

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

Unknown or omitted classes use `mdi:chart-line`. An explicit `icon` overrides
the default without changing units.

## Built-in drivers

### Standard serial pipe

```yaml
driver:
  type: labpulse.serial_pipe
  options:
    port: /dev/serial/by-id/usb-example
    baud_rate: 9600
```

- `port` is required and non-blank.
- `baud_rate` defaults to 9600 and must be positive.
- Real deployments expose `/dev` to this container.
- Fake paths under `/tmp/labpulse-fake-serial` receive pseudo-terminal mounts.
- The default runner interval is zero because the serial read blocks with its
  own timeout.

See [Serial protocol](SERIAL_PROTOCOL.md).

### DHT11

```yaml
driver:
  type: labpulse.dht11
  options:
    pin: D4
```

`pin` is a required Blinka board-pin name using uppercase letters, numbers, or
underscores. The generated container receives privileged `/dev` access. The
default read interval is 2 seconds. Its Python libraries belong to the shared
`gpio` dependency extra.

Declare measurements named `temperature` and `humidity` to match the built-in
driver output.

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

The container receives only the configured `/dev/i2c-<bus>` device. The driver
uses high-precision measurement mode and has a default read interval of 2
seconds. Declare measurements named `temperature` and `humidity` to match its
output. Fake-USB mode substitutes the standard room-environment SHT40 service
with the existing simulated serial temperature/humidity endpoint. Its Python
transport library belongs to the shared `i2c` dependency extra used by the
X1200 driver.

### Geekworm X1200

```yaml
driver:
  type: labpulse.x1200
  options:
    bus: 1
    address: 0x36
    gpio_chip: /dev/gpiochip0
    gpio_line: 6
    mains_present_active_high: true
```

| Option | Default | Constraint |
|---|---:|---|
| `bus` | `1` | 0 to 255 |
| `address` | `0x36` | Fixed MAX17043 address |
| `gpio_chip` | `/dev/gpiochip0` | `/dev/gpiochipN` |
| `gpio_line` | `6` | 0 to 53 |
| `mains_present_active_high` | `true` | GPIO polarity |

The container receives only the configured `/dev/i2c-<bus>` and GPIO chip
devices. The default read interval is 1 second.

An X1200 service requires:

```yaml
measurements:
  - name: voltage
    label: "UPS Battery Voltage"
    unit: V
    device_class: voltage
  - name: battery_level
    label: "UPS Battery Level"
    unit: "%"
    device_class: battery
  - name: mains_present
    label: "External Power Present"
    state_class: null
power_detection:
  outage_confirm_seconds: 3
  restore_confirm_seconds: 5
```

Dedicated power measurements omit `setups`; power is displayed outside
ordinary experimental setup grouping. It is alarmed by default. To keep only
the raw readings, set `alarmed: false` on all three measurements. Both
confirmation values accept 1 to 3600 seconds.

## Fake configuration

`labpulse setup --fake-usb` derives `config.fake.yaml`. It replaces starter
serial placeholders, converts DHT11 to simulated serial, and converts the power
service to the UPS pseudo-serial endpoint. It does not alter `config.yaml`.

Do not edit `config.fake.yaml` manually. The current `labpulse config` workflow
detects whether generated Compose is using fake USB, regenerates
`config.fake.yaml` from the edited source, and preserves that runtime mode:

```bash
labpulse config
```

The guarded workflow validates both the edited source and derived fake runtime
configuration through the central loader. It then builds Compose and Home
Assistant output from one loaded runtime document before replacing managed
live files.

## Validation and application

The supported workflow is:

```bash
labpulse config
```

For diagnostics without mutation:

```bash
labpulse doctor
```

Direct generator wrappers exist under `~/labpulse-live`, but using them alone
does not provide the editor's complete validation, rollback, Home Assistant
check, and service refresh workflow.
