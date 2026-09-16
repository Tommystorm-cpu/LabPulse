# Configuration reference

The installed source entry point is:

```text
~/labpulse-live/config.yaml
```

It may reference operator-owned physical-measurement mappings beneath
`~/labpulse-live/config.d/`. The repository sources are copied only when setup
creates a new installation. Never edit them expecting an existing Pi to change.

For a real-hardware installation, use the guarded editor:

```bash
labpulse config
```

## Source and runtime configuration

There is one operator-owned source bundle and one complete generated runtime:

| Path | Ownership | Purpose |
|---|---|---|
| `~/labpulse-live/config.yaml` | Operator | Master service, setup, dashboard, MQTT, SMS, and inline-measurement configuration |
| `~/labpulse-live/config.d/**/*.yaml` | Operator | Optional physical-measurement mappings selected by `measurements_file` |
| `~/labpulse-live/config.resolved.yaml` | Generated | Complete validated real-hardware runtime with every measurement inline |
| `~/labpulse-live/config.fake.yaml` | Generated | Complete fake-USB runtime derived from the resolved configuration |
| repository `config.yaml` | Package | Starter copied only when a live source does not exist |

Real Compose mounts `config.resolved.yaml` into Python containers as
`/app/config.yaml`. Fake Compose mounts `config.fake.yaml` at that same path.
Source fragments are never mounted into containers. Do not edit either generated
runtime file; `labpulse config`, setup, and direct generators replace them.

Home Assistant generation uses the active runtime document. Fake derivation
preserves service and measurement names, so both modes produce the same public
entity and alarm identities.

## Top-level structure

```yaml
mqtt:
  broker: mosquitto
  port: 1883
  external_listener:
    enabled: false
    bind_addresses:
      - 10.50.1.1
      - 10.50.2.1
    port: 8883

sms:
  dry_run: true
  recipients: []
  test_recipients: []

service_health:
  offline_confirm_seconds: 10
  recovery_confirm_seconds: 15

dashboards: {}
setups: {}
services: {}
outputs: {}
custom_measurements: {}
```

The top-level example is a schema skeleton, not a runnable deployment: Compose
requires at least one enabled sensor service. Other YAML blocks in this guide
are **fragments** to place under the shown key, not complete files. Use the
[complete examples](#complete-examples) for standalone validation.

`mqtt`, `setups`, and `services` are required mappings. `sms` defaults to dry-run
with empty recipient lists; `service_health` defaults to 10/15-second confirmation;
`dashboards`, `outputs`, and `custom_measurements` default to empty mappings.
`mqtt.broker` has no default; `mqtt.port` defaults to 1883. The external MQTT
listener defaults to disabled.

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
| Compose generator | enabled services and outputs, runtime image inputs, driver resources, SMS mode |
| Hardware CLI | one selected service, its typed driver options, MQTT settings |
| Home Assistant generator | enabled services and outputs, dashboards, setups, measurements, health and power timing |
| SMS CLI | MQTT settings, delivery mode, normal and test recipients |
| Output CLI | one selected output, its typed driver options, MQTT settings, and safety timing |
| Doctor | source/runtime agreement, enabled workers, declared host resources |

## MQTT

```yaml
mqtt:
  broker: mosquitto
  port: 1883
  external_listener:
    enabled: false
    bind_addresses:
      - 10.50.1.1
      - 10.50.2.1
    port: 8883
```

`broker` is the address used by LabPulse Python containers. In the generated
Compose deployment it must be `mosquitto`, not `localhost`.

`port` must be between 1 and 65535. The standard generated deployment uses
1883.

Home Assistant is different because it uses host networking. Its MQTT
integration connects to `127.0.0.1:1883`.

`external_listener` is for off-Pi data publishers such as a Triton control PC:

- `enabled` defaults to `false`; the generated broker remains loopback-only.
- `bind_addresses` is a non-empty list of Pi IPv4 interfaces on which to
  publish. LabPulse creates one host-port mapping per address. The configured
  addresses must be unique. `0.0.0.0` publishes on every interface and cannot
  be combined with specific addresses.
- `port` is the host-facing TLS port and defaults to 8883.

When enabled, generation requires
`mosquitto/config/certs/server.crt`,
`mosquitto/config/certs/server.key`,
`mosquitto/config/external-passwords`, and
`mosquitto/config/external-acl` under `~/labpulse-live`. The listener always
requires TLS, password authentication and an ACL; there is no configuration
switch for anonymous external access. Follow the
[Triton publisher setup](TRITON_PUBLISHER.md) for certificates, per-computer
topics, firewalling and Windows installation.

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
- Every incident that requested an opening SMS also requests a recovery SMS
  when the condition resolves, unless notification delivery is muted at recovery.
  Test mode at recovery sends the message to the current test recipients.
- Remove any old `send_recovery_sms` line from `~/labpulse-live/config.yaml`
  before updating LabPulse; it is no longer a valid SMS setting.
- `recipients` receive normal live alerts.
- `test_recipients` receive requests created while Home Assistant Test mode is
  enabled.
- Numbers use international `+` format with 8 to 15 digits.
- Empty and duplicate numbers are rejected within each list.
- At least one normal recipient is required when `dry_run` is `false`.

Use example numbers in committed configuration. See
[SMS behavior](USER_GUIDE.md#sms-behaviour).

## Whole-service health

```yaml
service_health:
  offline_confirm_seconds: 10
  recovery_confirm_seconds: 15
```

These values confirm a complete hardware-service outage and recovery before
Home Assistant opens or closes a service-level incident.

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

## Controlled outputs

Physical outputs are separate from read-only `services`:

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

Each enabled output becomes one `labpulse-output-...` container and one MQTT
switch such as `switch.labpulse_output_cooling_valve_enable`. An output with
`setups` is shown under **Controls** inside each selected setup and remains on
System Status. An output without `setups` is shown under **Controlled Outputs**
on Monitor and on System Status.

| Field | Default | Meaning |
|---|---:|---|
| `enabled` | `true` | Whether to generate and run this output worker |
| `label` | required | Home Assistant switch and device label |
| `icon` | `mdi:toggle-switch` | Material Design switch icon |
| `setups` | none | Optional non-empty list of declared setups where this control is displayed |
| `driver` | required | Output-capable driver and its options |
| `reconnect_interval_seconds` | `5` | Seconds; greater than 0 and at most 3600 |
| `maximum_active_seconds` | none | Seconds; greater than 0 and at most 86400 when supplied |

Output IDs use lowercase letters, numbers, and underscores. LabPulse rejects
an output that selects an input-only driver or a GPIO line already claimed by
another enabled LabPulse service or output.

The output worker subscribes to its Home Assistant command topic at QoS 1.
Only exact, live `ON` and `OFF` messages are accepted. Home Assistant is told
not to retain commands, and the worker rejects any retained command it does
receive. State and availability are retained so the UI can recover accurately
after reconnecting.

The current local broker does not authenticate publishers inside the Compose
network. The worker therefore cannot prove that a valid command came from Home
Assistant rather than another process with broker access. Keep Mosquitto bound
to localhost as generated and do not expose this experimental control path to
an untrusted network.

On startup, orderly shutdown, or loss of MQTT command authority, the worker
applies `safe_state`. It also retries unavailable GPIO hardware while keeping
the Home Assistant switch unavailable. If `maximum_active_seconds` is set,
logical `ON` returns automatically to `safe_state: false` when that timer
expires. Repeated `ON` commands do not extend the original timer. A maximum
active time cannot be combined with `safe_state: true`.

`labpulse setup --fake-usb` does not run physical output containers. Returning
to real-hardware mode starts each output in its safe state.

### Generic GPIO output

The `labpulse.gpio_output` driver has these options:

| Option | Default | Constraint |
|---|---:|---|
| `gpio_chip` | `/dev/gpiochip0` | `/dev/gpiochipN` |
| `gpio_line` | none | Required Linux GPIO line offset, 0 to 53 |
| `active_high` | `true` | Electrical high represents logical `ON` |
| `safe_state` | `false` | Logical state used without command authority |

The worker requests and holds the line using the libgpiod 2.x Python binding;
it does not release and reacquire GPIO for each command. After every write, it
reads back the GPIO latch before publishing the switch state. This confirms
only the Pi output, not that the connected relay, valve, or equipment moved.

The generated container receives only the configured `/dev/gpiochipN` device.
The custom interface must accept 3.3 V logic and provide any buffering,
isolation, level shifting, load switching, separate load supply, and inductive
flyback protection required by the equipment. Never power a relay or solenoid
directly from GPIO. A physical pull resistor must hold the same safe state
while the Pi is booting, unpowered, or after LabPulse releases the line.

## Services

Each key under `services` describes one independently running hardware service:

```yaml
services:
  pressure_monitor:
    label: Compressed Air and Environment Sensor Hub
    notify_on_service_failure: true
    driver:
      type: labpulse.serial_pipe
      options:
        port: /dev/serial/by-id/usb-example
        baud_rate: 9600
    measurements:
      pressure:
        setups: [compressed_air]
        unit: bar
        device_class: pressure
      temperature:
        label: Main Lab Temperature
        short_label: Temperature
        setups: [compressed_air]
        unit: "°C"
        device_class: temperature
      humidity:
        label: Main Lab Humidity
        short_label: Humidity
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
| `notify_on_service_failure` | `true` | Strict boolean controlling service-offline and service-recovery Home Assistant/SMS delivery. `false` leaves status and confirmed outages visible; reading and power alarms stay independent |
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
measurement_defaults:
  setups: [cryogenics_room]
  alarmed: false
measurements:
  temperature:
    label: Cryogenics Room Temperature
    short_label: Room Temperature
    unit: "°C"
    precision: 1
    show_graph: true
    device_class: temperature
    icon: mdi:snowflake-thermometer
    missing_confirm_seconds: 60
    recovery_confirm_seconds: 15
```

A service may instead move this mapping into one file:

```yaml
measurement_defaults:
  setups: [triton_1]
measurements_file: config.d/triton-01-measurements.yaml
```

`config.d/triton-01-measurements.yaml` contains the measurement mapping itself,
without a surrounding `measurements:` key:

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

Define exactly one of `measurements` and `measurements_file` for each service.
External files are supported only for physical service measurements. Driver
settings, `measurement_defaults`, calculated measurements, outputs, setups,
dashboards, MQTT, and SMS remain in `config.yaml`.

The path must be relative to `config.yaml`, name a regular `.yaml` or `.yml`
file beneath `config.d`, and must not use a symlink or `..`. Empty files, lists,
duplicate keys, missing files, and malformed mappings are rejected with the
fragment filename. Includes within fragments and general-purpose YAML includes
are not supported.

| Field | Default | Meaning |
|---|---|---|
| mapping key | required | Stable driver, MQTT, and entity ID; lowercase letters, numbers, and underscores |
| `source` | driver-specific | Exact external field name; required by `labpulse.mqtt_json` and rejected by drivers that already produce stable IDs |
| `label` | readable form of ID | Full label used for MQTT discovery, System Status, active problems, helpers, and notifications |
| `short_label` | `label` | Shorter label used where the dashboard's setup heading supplies context |
| `setups` | required for ordinary values | One or more logical setup IDs |
| `alarmed` | `true` | Whether to generate measurement alarm state, controls, and notifications |
| `required` | `true` | Whether missing data needs attention, can notify, and affects service status; strict boolean |
| `missing_confirm_seconds` | `60` | Continuous missing data required before a required-reading incident opens; 1 to 86400 seconds |
| `recovery_confirm_seconds` | `15` | Continuous usable data required before its missing-reading incident closes; 0 to 3600 seconds |
| `unit` | none | Exact published unit |
| `precision` | none | Optional Home Assistant display decimal places, strict integer from 0 to 10; MQTT state and graph history retain the full reading |
| `show_graph` | `false` | Strict boolean; replace the measurement's compact row with a native 24-hour line graph at the same position |
| `device_class` | none | LabPulse semantic category and default-icon source |
| `icon` | derived | Explicit `mdi:` override |
| `state_class` | `measurement` | Home Assistant statistics metadata; may be `null` |

Measurement IDs are mapping keys and preserve their YAML order. Duplicate keys
are rejected rather than allowing a later value to replace an earlier one.
Hardware readings not listed in the resolved `measurements` mapping are ignored.
Each setup preserves measurement order within its compact rows and graph cards. The former
`group` field is unsupported; remove it from measurements, measurement defaults,
and custom measurements when upgrading an existing configuration.

`measurement_defaults` is optional and accepts the same presentation,
availability, alarm, timing, unit, precision, graph, device-class, icon, and state-class fields as
an individual measurement. It cannot set `source`, because external source
names identify individual readings. Explicit fields on a measurement override
the service defaults; all other fields retain the ordinary measurement
defaults. LabPulse resolves this inheritance once while loading the file, so
runtime services receive complete validated measurement settings.

For ordinary service readings, `precision: 0` shows a whole number and
`precision: 2` suggests two decimal places. Omitting it publishes no display
precision suggestion from LabPulse. Home Assistant may apply its own display
defaults or an operator's entity-level override. The sensor state, recorded
history, alarm thresholds, and detailed history graph retain the unrounded
numeric value. The separate `custom_measurements.precision` field currently
rounds a calculated result itself, including its history.

Changing `label` or `short_label` preserves identity. Changing a
measurement mapping key creates a new MQTT topic, Home Assistant entity, alarm helpers, and
history.

Use `label` to keep a measurement unambiguous when it appears without its
logical setup heading. Add `short_label` only when that heading makes a
shorter name clearer. For example, `Triton 1 Temperature In` can appear as
`Temperature In` within the `Triton 1` setup. Set `show_graph: true` to replace
that measurement's compact row with a native Home Assistant sensor card at the
same position, containing its current value and a 24-hour line graph. Other
measurements retain the compact entities layout. Available graph history
follows Home Assistant Recorder retention.

Set `alarmed: false` for informational telemetry that should remain published
and visible on operator dashboards and System Status without measurement alarm
helpers, threshold controls, active-problem rows, or notifications. Whole-
service health monitoring remains separate. Dedicated power readings form one
composite outage alarm, so every measurement in a `power_detection` service
must use the same `alarmed` value.

Every configured measurement is required by default. Set `required: false`
only when a value should be shown when present but its absence is acceptable.
It then shows **No recent data — optional**, produces no incident, Home
Assistant notification, or SMS, does not change its service from **Working**,
and does not block `labpulse update`. `required` accepts only YAML booleans;
invalid values are rejected with the configuration filename and field location.

## Custom measurements

Custom measurements are calculated by Home Assistant from one or more physical
LabPulse measurements. They do not run in hardware containers and do not
publish another MQTT topic.

```yaml
custom_measurements:
  pump_room_temperature_difference:
    label: Pump Room Temperature Difference
    short_label: Temperature Difference
    setups: [pump_room_system]
    inputs:
      supply: pump_room.temp0
      return_temp: pump_room.temp1
    constants:
      scale: 1.0
    formula: (return_temp - supply) * scale
    show_graph: true
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
| `setups` | required | One or more logical setup IDs |
| `inputs` | required | One or more alias-to-physical-measurement references |
| `constants` | `{}` | Named finite numbers available to the formula |
| `formula` | required | Restricted arithmetic expression |
| `precision` | `2` | Result rounding from 0 to 10 decimal places |
| `alarmed` | `true` | Whether to create the normal threshold alarm controls |
| `required` | `true` | Whether a missing calculated result needs attention and can open an incident |
| `missing_confirm_seconds` | `60` | Required continuous missing calculated data before an incident opens |
| `recovery_confirm_seconds` | `15` | Required continuous usable calculated data before its incident closes |
| `unit` | none | Result unit shown by Home Assistant |
| `device_class` | none | Result semantic category and bulk-deadband grouping |
| `icon` | none | Optional explicit `mdi:` icon |
| `state_class` | `measurement` | Home Assistant statistics metadata; may be `null` |

The resulting entity is `sensor.labpulse_custom_<custom-id>`. It is unavailable
when any physical input is unavailable or non-numeric, or when a divisor
evaluates to zero. Its own `required` setting applies to that result. A
required calculated reading waits while a source service is offline so the
service-level incident remains the single root problem. Once inputs recover,
normal observation-window alarm evaluation resumes.

The service ID `custom` is reserved whenever custom measurements are present;
physical service IDs `custom_<custom-id>` also cannot collide with the synthetic
alarm service. Input aliases/constants must be usable lowercase arithmetic
names, not Python keywords or `true`, `false`, `none`, `null`, `states`, or
`is_number`. Inputs must reference distinct physical measurements, and aliases
cannot overlap constants. Formulas are limited to 500 characters and 100 syntax
tree nodes. Referenced physical services should be enabled; the current
cross-reference validator checks existence, not whether the input worker runs.

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

See the [Arduino serial behavior](USER_GUIDE.md#sensor-services-and-drivers) and
[firmware guide](../firmware/README.md).

### Named JSON over MQTT

Use `labpulse.mqtt_json` when another computer publishes a changing set of
named measurements as one JSON snapshot. The publisher sends every available
field. Each selected LabPulse measurement declares its exact external `source`
beside its display and alarm settings:

```yaml
driver:
  type: labpulse.mqtt_json
  options:
    topic: labpulse/triton/triton-01/measurements
    heartbeat_topic: labpulse/triton/triton-01/heartbeat
    heartbeat_timeout_seconds: 60
    maximum_record_age_seconds: 30
measurement_defaults:
  setups: [cryogenics_room]
  alarmed: false
measurements:
  condense_pressure:
    source: "P2 Condense (Bar)"
    unit: bar
    device_class: pressure
  cold_plate_temperature:
    source: "Cold Plate T(K)"
    unit: K
    device_class: temperature
  turbo_speed:
    source: "turbo speed(Hz)"
    unit: Hz
```

| Option | Default | Meaning |
|---|---:|---|
| `broker` | `mosquitto` | Broker hostname visible inside the service container |
| `port` | `1883` | Internal broker TCP port |
| `topic` | required | Exact MQTT topic; wildcards are rejected |
| `heartbeat_topic` | absent | Optional exact publisher heartbeat topic ending in `/heartbeat`; its sibling `/availability` topic is derived automatically |
| `heartbeat_timeout_seconds` | `60` | Seconds, 2–3600; requires `heartbeat_topic`. The Pi requires a new non-retained heartbeat within this interval and retained publisher availability `online` |
| `maximum_record_age_seconds` | `300` | Seconds, 2–86400; reject older source timestamps |

Without `heartbeat_topic`, an MQTT JSON service still derives health from
measurement freshness. With it, the service waits for a new heartbeat after
each connection and uses the heartbeat plus retained availability for publisher
health. Old numeric readings continue to expire according to
`maximum_measurement_age_seconds` and can open their separate required-reading
incidents. A quiet logfile therefore does not by itself open a publisher outage.

Every measurement in an MQTT JSON service requires a nonblank `source`.
Source names are exact, case-sensitive, and unique within that service. Extra
fields in a message are ignored. If one configured field is absent or null,
available fields continue updating and the service reports a partial hardware
fault. Drivers such as `labpulse.serial_pipe` already return stable measurement
IDs and therefore reject `source`.

Messages use this versioned contract:

```json
{
  "protocol": "labpulse.measurements",
  "version": 1,
  "recorded_at": 1700000000,
  "measurements": {
    "Cold Plate T(K)": 0.0857,
    "unused changing header": null
  }
}
```

`measurements` must be non-empty; mapping keys use lowercase alphanumeric words
separated by single underscores, and source names must be non-blank.
Messages are limited to 1,000,000 bytes, must use protocol version 1, and need
a finite Unix timestamp no more than 60 seconds ahead of receipt. Boolean,
non-numeric, null, absent, and non-finite fields are unavailable. A message
with no usable mapped readings is rejected. The timestamp shown above is an
illustration and must be replaced by the current record time for a live test.
The default polling interval is 0.1 seconds. This input driver has no TLS or
username/password options; an external secured listener may feed the internal
broker separately, as discussed in the [publisher guide](../firmware/README.md).

The driver consumes each snapshot once. If publishing stops, the ordinary
service `maximum_measurement_age_seconds` setting makes the service stale and
reconnects it. MQTT is ordinary network access, so this driver requests no
host devices or privileged container permissions.

### Generic GPIO input

Use one service for all digital inputs on a GPIO chip:

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
      pin_17:
        label: GPIO Pin 17
        gpio_line: 17
        active_high: true
      pin_27:
        label: GPIO Pin 27
        gpio_line: 27
        active_high: false
    read_interval_seconds: 1
```

| Option | Default | Constraint |
|---|---:|---|
| `gpio_chip` | `/dev/gpiochip0` | `/dev/gpiochipN` |
Each measurement requires a unique `gpio_line` from 0 to 53. Its strict boolean
`active_high` defaults to `true`; set it to `false` for an active-low signal.
These two fields are valid only on measurements belonging to this driver.

LabPulse requests all configured lines together and publishes each value under
its measurement ID. Logically inactive is `0.0` and active is `1.0`.
Normal numeric alarm thresholds therefore apply; for example, a minimum of
`0.7` treats the inactive state as low. A dedicated Home Assistant binary
sensor is not generated yet.

The default read interval is 1 second. This is intended for stable equipment
states, switches, and relay contacts, not for counting short pulses. The
generated container receives only the selected GPIO chip device and uses the
packaged Python `gpiod` library. `gpio_line` is the Linux GPIO line offset, not the
physical header-pin number.

Raspberry Pi GPIO uses 3.3 V logic. The official
[GPIO documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio-and-the-40-pin-header)
describes inputs as 3.3 V tolerant and warns against direct motor loads. The
custom hardware must provide a defined high or low level and any required
isolation, level conversion, and pull resistor; never connect a higher-voltage
signal directly to the Pi. `active_high: false` inverts an active-low interface
in software.

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
  voltage:
    label: UPS Battery Voltage
    unit: V
    device_class: voltage
  battery_level:
    label: UPS Battery Level
    unit: "%"
    device_class: battery
  mains_present:
    label: External Power Present
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

`labpulse setup --fake-usb` first resolves `config.yaml` and `config.d` into
`config.resolved.yaml`, then derives `config.fake.yaml` without altering the
operator-owned source bundle. Substitution is deliberately narrow:

- named `FAKE_PRESSURE_PORT`, `FAKE_PUMP_ROOM_PORT`, `FAKE_TURBO_PUMP_PORT`,
  and `FAKE_UPS_PORT` placeholders map to fixed pseudo-terminal paths;
- the service named `room_environment` is converted only when it uses DHT11 or SHT40;
- one enabled `power_detection` service is converted to the UPS endpoint;
- when no power service is configured, a default simulated UPS service is added;
- configured but disabled power services are not silently enabled, and more
  than one enabled power service is rejected by fake derivation;
- arbitrary serial paths, renamed environment services, GPIO inputs, and MQTT
  sources are not automatically simulated;
- Compose omits physical output workers in fake mode.

Inspect the derived config before expecting a custom installation to run
without hardware. The simulator's fixed channel names must match the configured
measurement names. See
[simulation controls](USER_GUIDE.md#choose-real-hardware-or-simulation).

Do not edit `config.resolved.yaml` or `config.fake.yaml` manually. The current `labpulse config` workflow
detects whether generated Compose is using fake USB, regenerates
`config.fake.yaml` from the edited source, and preserves that runtime mode:

```bash
labpulse config
```

The guarded workflow validates the complete staged source bundle, renders and
independently validates the standalone resolved runtime, and then builds
Compose and Home Assistant output from that same runtime document.

## Validation and application

The supported workflow is:

```bash
labpulse config
labpulse config config.d/triton-01-measurements.yaml
labpulse config config.yaml config.d/triton-01-measurements.yaml
```

With no path, the command lists `config.yaml` and every YAML file beneath
`config.d`, then asks which one to edit. The menu can also create a new
measurement file; it opens the new file with `config.yaml` so the master can
reference it in the same guarded edit. Passing paths directly opens staged
copies of the selected sources without showing the menu.
The command compares and backs up the complete source bundle, so changing only
a fragment still regenerates and refreshes the deployment. A master reference
and a new fragment can be created in one invocation by passing both paths.

For diagnostics without mutation:

```bash
labpulse doctor
```

Direct generator wrappers exist under `~/labpulse-live`, but using them alone
does not provide the editor's complete validation, rollback, Home Assistant
check, and service refresh workflow.

## Settings owned by Home Assistant

Threshold values, alarm mode, observation/recovery settings, deadband, mutes,
and Test mode are edited in Home Assistant and stored with its state. They are
not fields to add to the LabPulse YAML. See the complete
[alarm behavior](USER_GUIDE.md#measurement-alarm-behaviour).
Changing YAML labels preserves IDs; changing keys can create new helpers and
leave old entities behind. Back up Home Assistant state before identity changes.

## Complete examples

The following files are complete source configurations validated by
`testing/test_documentation.py`. Each uses dry-run SMS with no recipients and
no active physical outputs. They are examples for isolated development, not
instructions to overwrite an existing live installation.

| File | Demonstrates |
|---|---|
| [minimal-serial.yaml](examples/minimal-serial.yaml) | One pressure sample on a known simulator endpoint |
| [calculated-measurement.yaml](examples/calculated-measurement.yaml) | Two physical temperatures, a calculated difference, grouping and a custom tab |
| [mqtt-input.yaml](examples/mqtt-input.yaml) | Exact external header mapping into a configured measurement |

From a development checkout with dependencies installed, generate into a
scratch directory without starting services:

```bash
python -m labpulse.deployment --config docs/examples/minimal-serial.yaml --compose-output testing/tmp/doc-example/compose.yaml --project-dir testing/tmp/doc-example --ha-config-dir testing/tmp/doc-example/homeassistant/config
```

This checks the schema and renders files; it does not start a broker, simulator,
Home Assistant, or hardware. The serial example already uses a fake path, so
the serial driver's fake-path handling supplies its mounts without changing
the configuration through the setup workflow.
