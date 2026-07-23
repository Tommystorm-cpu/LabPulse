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

setups: {}
services: {}
```

Configuration is validated with Pydantic before generation and service startup.
Unknown driver IDs, invalid driver options, missing setup references, duplicate
measurement names, and invalid timing values fail early.

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

## Logical setups

Setups group measurements by experiment or monitored system independently of
the physical sensor hub:

```yaml
setups:
  compressed_air:
    label: "Compressed Air"
    icon: "mdi:gauge"
    order: 10
```

Setup IDs are stable identifiers containing lowercase letters, numbers, and
underscores. Changing an ID changes generated helper and dashboard identities.

Fields:

| Field | Default | Meaning |
|---|---:|---|
| `label` | readable form of ID | Display text |
| `icon` | `mdi:flask-outline` | Material Design icon |
| `order` | `100` | Dashboard ordering from 0 to 10000 |

An ordinary measurement must select at least one declared setup. One
measurement may appear in several setups without creating duplicate MQTT
entities or alarm state.

## Services

Each key under `services` describes one independently running hardware service:

```yaml
services:
  pressure_monitor:
    enabled: true
    driver:
      type: labpulse.serial_pipe
      options:
        port: /dev/serial/by-id/usb-example
        baud_rate: 9600
    device_name: "Air Pressure Sensor Hub"
    measurements:
      - name: pressure
        label: "Pressure"
        setups: [compressed_air]
        unit: bar
        device_class: pressure
    reconnect_interval_seconds: 5
    maximum_measurement_age_seconds: 300
```

Service keys are stable IDs used in container names, MQTT topics, devices, and
entity IDs. Choose a lowercase underscore-separated name and do not rename it
after collecting history unless a new identity is intended.

| Field | Default | Meaning |
|---|---:|---|
| `enabled` | `true` | Whether generation creates the service |
| `driver` | required | Driver ID and driver-owned options |
| `device_name` | required | Home Assistant device label |
| `measurements` | required | Allowed published values |
| `reconnect_interval_seconds` | `5` | Delay before connection retry; greater than 0 |
| `read_interval_seconds` | driver default | Central polling interval; greater than 0 when set |
| `maximum_measurement_age_seconds` | `300` | MQTT expiry/freshness limit, 2 to 86400 |
| `power_detection` | absent | Dedicated power-outage confirmation |

Each enabled service becomes `labpulse-<service-slug>` in Compose.

## Measurements

```yaml
- name: temperature
  label: "Room Temperature"
  subcategory: "Environment"
  setups: [cryogenics_room]
  unit: "°C"
  device_class: temperature
  icon: "mdi:snowflake-thermometer"
  state_class: measurement
```

| Field | Default | Meaning |
|---|---|---|
| `name` | required | Stable driver, MQTT, and entity key |
| `label` | readable form of `name` | Display text |
| `subcategory` | none | Presentation grouping within a setup |
| `setups` | required for ordinary values | One or more logical setup IDs |
| `unit` | none | Exact published unit |
| `device_class` | none | LabPulse semantic category and default-icon source |
| `icon` | derived | Explicit `mdi:` override |
| `state_class` | `measurement` | Home Assistant statistics metadata; may be `null` |

Measurement names must be unique within a service. Hardware readings not listed
in `measurements` are ignored.

Changing a label or subcategory preserves identity. Changing `name` creates a
new MQTT topic, Home Assistant entity, alarm helpers, and history.

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
default read interval is 2 seconds.

Declare measurements named `temperature` and `humidity` to match the built-in
driver output.

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

Dedicated power measurements omit `setups`; power is displayed and alarmed
outside ordinary experimental setup grouping. Both confirmation values accept
1 to 3600 seconds.

## Fake configuration

`labpulse setup --fake-usb` derives `config.fake.yaml`. It replaces starter
serial placeholders, converts DHT11 to simulated serial, and converts the power
service to the UPS pseudo-serial endpoint. It does not alter `config.yaml`.

Do not edit `config.fake.yaml` manually. The current `labpulse config` workflow
regenerates real-hardware Compose and does not preserve fake mode. While using
fake mode, edit the source directly and rerun fake setup:

```bash
${EDITOR:-nano} ~/labpulse-live/config.yaml
labpulse setup --fake-usb
```

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
