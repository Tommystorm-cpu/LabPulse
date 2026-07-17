# LabPulse Code Internals

This guide explains how the implemented code works below the architecture
level. It names the important variables and data structures, shows which
functions call which, and identifies the places where behavior is intentionally
centralized.

Paths in this document are relative to `docker_refactor/`.

## Recommended reading order

Read the source in this order if you want to reconstruct the complete system:

1. `config.yaml`
2. `labpulse_common/config.py`, `identity.py`, and `mqtt_contracts.py`
3. `labpulse_hardware/cli.py`
4. `labpulse_hardware/drivers/`
5. `labpulse_hardware/legacy_parsing/serial_parser.py`
6. `labpulse_hardware/homeassistant_publisher.py`
7. `labpulse_homeassistant/cli.py` and `data_models.py`
8. `labpulse_homeassistant/write_yaml.py`, `alarm.py`, and `dashboard.py`
9. `labpulse_homeassistant/templates/`
10. `labpulse_sms/subscriber.py`, `sender.py`, and `subscriptions.py`
11. `simulate_serial.py` and `setup_usb_devices.py`
12. `generate_compose.sh` and `setup_container_fs.sh`
13. `testing/`

## Shared configuration models

`labpulse_common/config.py` is the only Python config reader. `load_config()`
loads YAML and validates it into these Pydantic objects:

```text
LabPulseConfig
  mqtt: MqttConfig
  sms: SmsConfig
  services: dict[str, ServiceConfig]

ServiceConfig
  enabled: bool
  driver: "serial" | "gpio" | "i2c"
  parser, serial_port, baud_rate
  gpio_sensor, gpio_pin
  device_name
  display: DisplayConfig
  readings: list[ReadingConfig]
  reconnect_interval_seconds
  read_interval_seconds
```

The `services` dictionary key is the stable service identity. A
`ReadingConfig.name` is the stable reading identity. `device_name`, `label`,
`display.section`, and `display.icon` are presentation.

Important computed properties are:

- `ReadingConfig.display_label`: configured label or a title made from `name`.
- `ServiceConfig.display_label`: the device name.
- `ServiceConfig.dashboard_section`: configured section or device name.
- `ServiceConfig.dashboard_icon`: configured icon or `mdi:chip`.

`SmsConfig.validate_recipients()` applies the same normalization and
international-number validation to `recipients` and `test_recipients`.
`require_real_recipients()` requires at least one normal number when `dry_run`
is false. Test requests with no configured test recipients fail closed instead
of falling through to the normal emergency list.

`load_config()` exits the process after logging readable YAML or validation
errors. Callers therefore receive a valid `LabPulseConfig`, not a partly valid
dictionary.

## Shared identity and MQTT contracts

`labpulse_common/identity.py` contains four small but critical functions:

- `slug(value)` converts arbitrary text to lowercase underscore form.
- `title(value)` converts a machine key to a display title.
- `stable_id(*parts)` prefixes normalized parts with `labpulse_`.
- `entity_id(domain, *parts)` combines a Home Assistant domain and stable ID.

Both the hardware publisher and Home Assistant generator import these
functions. This prevents the two sides from guessing different IDs.

`labpulse_common/mqtt_contracts.py` owns all cross-process topic strings:

```text
home/sensor/<service>/<reading>/state
home/sensor/<service>/status
homeassistant/sensor/<service>_<reading>/config
homeassistant/sensor/<service>_status/config
labpulse/sms/send
labpulse/sms/status
labpulse/sms/result/<request_id>
```

It also defines `SmsRequest`, the exact JSON contract accepted by the SMS
worker. Extra fields are forbidden. Supported events are `sensor_fault`,
`warning`, `recovery`, and `test`.

## Hardware service execution

`python -m labpulse_hardware` enters `labpulse_hardware/cli.py`.

`parse_args()` accepts:

- `--service`: required config service key
- `--config`: config path
- `--print`: log valid reading dictionaries
- `--no-mqtt`: acquire without publishing
- `--once`: stop after one valid reading

`main()` is intentionally orchestration-only:

```text
load config
get selected ServiceConfig
build_driver(service_name, service_cfg)
create HomeAssistantMqttPublisher unless --no-mqtt
driver.setup()
publish initial driver status
loop:
  readings = driver.read()
  publish changed driver status
  skip empty/invalid samples
  publish readings
  stop after one sample when --once
finally disconnect driver and MQTT
```

`last_status` avoids publishing the same health transition on every loop.
Blank serial reads sleep for 0.1 seconds so a disconnected or quiet device does
not cause a busy loop.

### Driver interface and factory

`BaseSensorDriver` defines the shared state:

```python
self.name: str
self.connected: bool
self.status: str
self.logger: logging.Logger
```

Implementations must provide `setup()`, `read()`, and `disconnect()`.
`read()` returns either `dict[str, float]` or `None`.

`drivers/factory.py::build_driver()` maps validated config to implementations:

- `driver: serial` requires `serial_port` and `parser`, then constructs
  `SerialDriver`.
- `driver: gpio` plus `gpio_sensor: dht11` requires `gpio_pin`, then constructs
  the DHT11 driver.
- `driver: i2c` plus `i2c_sensor: max17043_ups` requires an explicit bus and
  the verified address `0x36`, then constructs the MAX17043 UPS driver.

Driver modules are imported only inside their selected branch. In particular,
serial and I2C workers do not import Blinka, `board`, or `adafruit_dht`; eager
imports can open `/dev/gpiochip0` in unrelated containers and prevent the DHT
worker from acquiring GPIO4.

The MAX17043 driver performs read-only VCELL and SOC transactions, publishes
voltage and gauge-calculated battery level at one-second intervals, and
reconnects after explicit I2C faults. It does not publish current or charging
status because the installed hardware does not measure them.

### Serial driver

`drivers/serial_driver.py::Driver` holds:

```python
port, baud_rate
ser                         # pyserial handle or None
parser_type
parser: SerialParser
reconnect_interval_seconds
last_reconnect_attempt      # monotonic time
```

`setup()` opens `serial.Serial(..., timeout=2)` and changes status to `online`.
On failure it closes/clears state and returns false.

`read()` has two paths:

1. If disconnected, `_try_reconnect()` is rate-limited by
   `reconnect_interval_seconds` and returns no reading.
2. If connected, one line is read, decoded as UTF-8, stripped, and sent to the
   parser. Serial/OSError failures mark the driver disconnected.

The container stays alive when a USB device disappears. This is why reconnect
logic belongs in the driver rather than Compose restart behavior.

### DHT11 driver

`drivers/dht11_driver.py::Driver` stores a Blinka pin name, read/reconnect and
maximum-age timings, the Adafruit device object, monotonic freshness state, and
the most recent reconnect attempt.

`setup()` resolves the named attribute from `board` and constructs
`adafruit_dht.DHT11` with `use_pulseio=True`. This is the mode verified against
the installed DHT11 and Raspberry Pi; GPIO4 must remain exclusive to the DHT
worker.

`read()` throttles requests with monotonic time. A normal DHT `RuntimeError`
means one sample was missed and does not immediately mark the service offline.
If valid samples remain absent for `maximum_reading_age_seconds`, status becomes
`error`; warnings are rate-limited to one per minute. A valid sample restores
`online`.

Unexpected errors release the GPIO device and enter a rate-limited reconnect
loop using `reconnect_interval_seconds`. This also lets a service whose initial
GPIO setup failed recover without restarting its container. A valid sample
returns exactly:

```python
{"temperature": float, "humidity": float}
```

### Unified and legacy serial parser

`legacy_parsing/serial_parser.py::SerialParser` first detects the standardized
schema-1 JSON envelope emitted by `docker_refactor/firmware`. It requires the
record's `device` to match the configured service name and returns only finite
numeric members of its `readings` object. Startup records, JSON `null`, booleans,
metadata, and `diagnostics` are not returned as telemetry.

If the line is not JSON, `parser_type` selects the temporary compatibility
path for boards that have not yet been reflashed:

- `pressure`: parse one MPa number and multiply by 10 to publish bar.
- `pump_room` or `water`: locate recognized labels anywhere in a line.
- anything else: generic pipe-delimited `Label: value | Label: value` parsing.

The labelled parser uses a compiled pattern for `FlowRate`, `TotalLitres`,
`RoomTemp`, `RoomHum`, numbered `Flow`, `Temp`, and `Press` labels. Values run
from one recognized label to the next, allowing it to recover the malformed
`L/minTemp0` boundary printed by the full-water sketch.

`_clean_float()` extracts the first signed decimal and rejects non-finite
values. `_key()` lowercases labels. Both paths produce the same normalized
`dict[str, float]`, such as:

```python
{"flow1": 2.45, "temp0": 20.11}
```

## MQTT discovery and state publishing

`HomeAssistantMqttPublisher` is created once per hardware service. Its most
important state is:

```python
reading_configs: dict[str, ReadingConfig]
discovered_readings: set[str]
status_discovery_published: bool
client: paho.mqtt.client.Client
```

`publish(readings)` first calls `configured_readings()`. Keys not declared in
the service’s `readings` list are ignored and logged. This makes config the
allow-list for MQTT entities.

Discovery is published once per reading when that reading first appears.
Reading discovery contains its label, state topic, stable `unique_id`,
`object_id`, `default_entity_id`, device grouping, and optional unit,
device-class, and state-class metadata. Discovery and service status are
retained; live numeric reading values are not retained.

Service status has its own MQTT sensor and is published when the driver changes
between values such as `online`, `disconnected`, and `reconnecting`.

## Home Assistant generator

The public command is `generate_homeassistant_config.sh`. The shell wrapper
owns paths, permissions, dashboard backup/restore, flag validation, and the
optional access-token environment. It then calls:

```bash
python3 -m labpulse_homeassistant \
  CONFIG_PATH HA_CONFIG_DIR RESET RESOLVE SYNC HA_URL
```

`labpulse_homeassistant/cli.py::main()` performs the Python orchestration:

```text
load validated config
load and validate alarm_defaults.json beside that config
build RenderModel
optionally fetch and resolve the live entity registry
render_core()
render_alarm()
render_dashboard()
```

### Render-model data structures

`data_models.py` is the boundary between general LabPulse config and Home
Assistant-specific rendering.

`RenderModel` contains an ordered `list[ServiceModel]`. Its `readings` property
flattens that into `list[tuple[ServiceModel, ReadingModel]]`, preserving access
to both parents during per-reading expansion.

`ServiceModel` contains:

- stable identity, label, section, icon, and display order
- an `EntityReference` for the MQTT status sensor
- entity IDs for four service-level timing helpers
- `list[ReadingModel]`

`ReadingModel` contains:

- reading identity and label
- an `EntityReference` for the MQTT reading
- every generated alarm helper/entity ID
- default alarm mode
- a `ThresholdModel` with initial values and editable ranges

`EntityReference` separates identity from the current registry name:

```python
platform
unique_id
default_entity_id
resolved_entity_id | None
resolution_status
```

Its `entity_id` property uses the resolved ID when available, otherwise the
deterministic default. This lets every renderer consume one effective value.

`GeneratorPaths` derives all output locations from `config_path` and
`ha_config_dir`; renderers do not manually reconstruct paths.

### Building the model

`build_render_model()` sorts services by `display.order`, skips disabled
services, constructs service IDs/helpers, and calls `build_reading_model()` for
each configured reading.

The default alarm mode and editable helper ranges are inferred from the
normalized reading name:

| Name contains | Default mode | Initial range concept |
| --- | --- | --- |
| `flow`, `press`, `pressure` | Low Only | low threshold is meaningful |
| `temp`, `hum` | Range | both boundaries are meaningful |
| anything else | Range | generic numeric defaults |

The initial Min, Max, and Deadband values come from the user-owned
`alarm_defaults.json` beside the selected `config.yaml`. The loader requires an
entry for every enabled ordinary reading, rejects unknown services/readings,
and excludes the dedicated power service.

Each reading's three JSON values are hashed into the suffix of its persistent
initialization helper. An unchanged suffix leaves operator-tuned Home Assistant
values alone. Editing that reading's JSON entry and regenerating produces a new
off marker, so its initialization automation applies the new values exactly
once. The editable dashboard remains the ongoing owner after that seed.

### Template expansion

There are two deliberately separate syntaxes:

- `[[ service.label ]]`, `[[ reading... ]]`, and `[[ model... ]]` are expanded
  by LabPulse Python during generation.
- `{{ ... }}` and `{% ... %}` are Home Assistant Jinja and are preserved for
  Home Assistant to evaluate at runtime.

`template_utils.expand_template()` recursively walks dictionaries, lists,
dictionary keys, and strings from the YAML seeds. A string that consists only
of one LabPulse placeholder returns the underlying Python value, preserving
numbers and booleans. A placeholder embedded in a larger string is converted
to text.

`render_template_file()` handles the small outer `.j2` files. Despite their
extension, it intentionally performs exact `[[ key ]]` replacement rather than
using the Jinja2 Python package. This keeps Home Assistant’s Jinja untouched and
avoids a second delimiter configuration.

### Core YAML output

`write_yaml.render_core()` writes `configuration.yaml` and
`labpulse_entity_map.yaml`. `ensure_ui_yaml_files()` creates empty
`automations.yaml`, `scripts.yaml`, and `scenes.yaml` only when absent.

`entity_map()` is a diagnostic projection of the model. For every MQTT entity
it records default, resolved, and effective IDs plus all alarm-related entity
IDs. It is the first file to consult when a dashboard reference is uncertain.

### Dashboard rendering and preservation

`dashboard.py` loads `templates/dashboard/dashboard_seed.yaml` and expands it
into Home Assistant’s active Overview JSON store. The generator resolves a
named `.storage/lovelace.<id>` through `lovelace_dashboards`, with legacy
`.storage/lovelace` as the fallback.

The generated Monitor view contains one section per distinct
`display.section`. Services with the same section label share that location
section and receive separate service subheadings and status tiles. A duplicate
top-level System Health section is intentionally omitted because each service's
health remains visible beside its readings.
The first ordered service supplies the shared section icon. Each reading is
represented by one compact entities list containing only current readings.
When readings define `group`, the dashboard renders one ordered entities card
per group. Cards remain untitled; the surrounding section and service
subheading name the room and owning hub. Reading rows use the short config label
but do not specify an icon, allowing Home Assistant's entity icon to render.
Room-environment readings use `Room Temperature` and `Room Humidity` labels.
Group metadata does not affect acquisition, identity, or alarm ownership.
Alarm State and Muted are omitted from Monitor to keep scanning concise; both
remain available inside each reading's expanded controls in Alarm Setup. The
device name is always rendered between the location and service status, even
when the location contains only one service, so dashboard columns share the
same visual hierarchy. Alarm Setup starts with one global notification-control
section, followed by one section per service containing service timing helpers
and per-reading show-controls/conditional settings cards.

`render_dashboard()` has three mutually exclusive behaviors:

- reset: generate and replace the resolved Overview storage file
- sync: recursively replace exact stale entity-ID strings in the existing
  dashboard
- normal: print that the editable dashboard was preserved

`replace_entity_references()` only replaces complete dictionary keys or string
values. It does not search/replace text embedded in titles or user content.

### Entity-registry resolution

`entity_registry.fetch_entity_registry()` authenticates to Home Assistant’s
WebSocket API and retrieves registry entries. `resolve_model_entities()` groups
entries by `(platform, unique_id)` and gives every `EntityReference` one of:

```text
matched, renamed, missing, disabled, ambiguous
```

Strict mode rejects missing, disabled, or ambiguous entities. A renamed entity
is safe because its unique ID still proves identity. `ResolutionReport` creates
old-to-current replacements from deterministic defaults and the previous
entity map, enabling surgical dashboard synchronization.

Fresh startup deliberately does not use this path: entities do not exist until
hardware services publish MQTT discovery.

## Alarm state machine

`alarm.py` reshapes the rules in `templates/alarm/alarm_logic.yaml` into native
Home Assistant package sections. Service rules are expanded once per service;
reading rules once per reading.

### Generated helpers

Each service receives:

- required danger percentage
- observation-window seconds
- required recovery seconds

Each reading receives:

- persistent alarm state: Normal, Danger, or Sensor Fault
- alarm mode: Disabled, Low Only, High Only, or Range
- mute and dashboard-expansion booleans
- minimum, maximum, and recovery-deadband numbers

### Calculated entities

`danger_zone` is on when a numeric reading violates the active threshold mode.
Disabled or invalid readings are not considered threshold danger.

`recovery_zone` applies the deadband inward. For example, a Low Only reading
recovers only at or above `minimum + deadband`. Disabled mode is considered
recovered when the reading is numeric.

`sensor_fault_zone` is on when the reading is invalid/unavailable or service
health reports an explicit error/unknown condition. MQTT discovery sets
`expire_after` from `maximum_reading_age_seconds`, so Home Assistant makes a
reading unavailable only when its MQTT samples actually stop. Repeated samples
with an unchanged numeric value remain healthy. `disconnected` and
`reconnecting` do not immediately fault a previously valid reading: MQTT
expiry acts as the reconnect grace period. After expiry, ordinary readings use
a second confirmation window of up to 15 seconds before changing the alarm
state. This filters the brief `unavailable` phase produced when Home Assistant,
the broker, and every publisher are restarted together.

The `history_stats` observed-danger sensor reports the percentage of the
sliding observation window for which `danger_zone` was on. It updates on source
changes and otherwise on Home Assistant’s periodic history-stat refresh.

### State transitions

```text
Normal
  -- observed danger >= required percentage --> Danger

Danger
  -- recovery zone continuously on for recovery time --> Normal

Normal or Danger
  -- sensor fault remains on through confirmation --> Sensor Fault

Sensor Fault
  -- fault clears and observed danger is high --> Danger
  -- fault clears and recovery zone is on      --> Normal
  -- neither condition is true                 --> remains Sensor Fault
```

Sensor fault takes priority. Danger entry excludes faulted and Disabled
readings. State changes occur whether muted or not; only notifications and SMS
publishing are inside the combined individual/global mute check. The global
helper is never used as a state writer for individual mute helpers. Test mode
adds `[TEST]` to titles and sets the validated request flag consumed by the SMS
recipient router. Its explicit `initial: true` setting makes every Home
Assistant start default to test delivery until an operator turns it off. When a confirmed fault clears, Home
Assistant creates a persistent sensor-restored notification after reconciling
the reading to Normal or Danger and publishes a validated recovery SMS request.
Because the state does not enter Sensor Fault during an unconfirmed startup
transient, ordinary container restarts do not emit a recovery for every reading.

### Service-health lifecycle

Every hardware MQTT client installs a retained QoS-1 `offline` Last Will before
connecting and explicitly flushes the same state during clean shutdown. Normal
driver states remain retained on the shared service-status topic. Home Assistant
derives one service-wide problem sensor from `disconnected`, `reconnecting`,
`error`, `offline`, `unknown`, and `unavailable`. `online` is fully healthy;
component-specific `gpio_fault` means the service is reachable but its X1200
GPIO input is degraded.

After `service_health.fault_confirm_seconds`, a persistent service-fault latch
and start timestamp are set and one hub warning is sent. Changes between
unhealthy status strings cannot duplicate it. When the whole-service problem
sensor remains off for `recovery_confirm_seconds`, Home Assistant sends one
recovery with downtime and clears the latch. Startup triggers repeat the same
confirmed checks because native `for` timers do not survive restart.

While the whole-service problem is present or latched, new per-reading fault,
Danger, and recovery transitions are gated. MQTT readings may still expire for
honest dashboard presentation. A reading that was already in a genuine Sensor
Fault remains latched and recovers only after the service returns and that
reading becomes valid. Once the service recovery period ends, ordinary stale
reading confirmation resumes, providing an additional telemetry grace period.

Danger notifications include the current reading, active threshold, observed
danger percentage, observation window, approximate time in danger, and required
percentage. Sensor-fault notifications distinguish unavailable/non-numeric
readings from unhealthy service status. The SMS contract calls the optional
value `current_reading`, and rendered SMS labels it `Current Reading`.

### Dedicated UPS power lifecycle

A service with `power_detection` is excluded from every generic threshold,
history-stat, and percentage loop above. `PowerModel` instead supplies the IDs
and configured timings expanded from `templates/alarm/power_logic.yaml`.

The live X1200 driver combines its read-only MAX17043 fuel-gauge sample with a
libgpiod read of GPIO6. It publishes `mains_present=1` for external power and
`mains_present=0` for battery operation. The Compose generator maps only the
configured I2C bus and gpiochip device into the UPS container. GPIO4 remains
owned by the independent DHT11 service.

Home Assistant converts the numeric MQTT value into a `power` binary sensor.
An off state held for `outage_confirm_seconds` (default three) records the GPIO
edge time, turns on the persistent outage latch, selects `On Battery`, and
sends one warning. An on state held for `restore_confirm_seconds` (default
five) can recover only an active outage; it records duration, clears the latch,
selects `Normal`, and sends one recovery. Native state-trigger `for` periods
cancel automatically when a brief flicker reverses.

Home Assistant `for` timers do not survive restart, so explicit startup and
automation-reload reconciliation covers both missed directions. Persistent
`outage_active` and `outage_started` helpers prevent duplicate warnings and
allow a restored signal observed after restart to complete the existing event.
When a new outage begins while Home Assistant is down, its exact remote edge
time is unknowable; reconciliation records the beginning of the confirmed
observation window. Normal live transitions retain their actual GPIO edge time.

If GPIO sampling fails, the composite driver publishes `gpio_fault` and omits
only `mains_present`; voltage and percentage continue. MQTT expiry also makes a
stale mains value unavailable. Either condition creates `Sensor Fault` and is
never interpreted as an outage. A confirmed-fault helper prevents routine
startup restoration from fabricating incidents.

Power has one dedicated mute. It suppresses only power notifications and
validated SMS requests; telemetry, lifecycle transitions, and history continue.
The dashboard reads outage history through template-sensor mirrors, keeping the
persistent timestamp and duration helpers off the editable Monitor surface. A
built-in gauge visualizes UPS battery percentage without custom cards. Alarm
Setup exposes the normalized and raw mains values, fault state, and active
outage latch. Battery voltage and percentage never determine outage state.

## SMS service internals

All user-facing SMS text is defined once in
`labpulse_common/sms_templates.yaml`. The Home Assistant generator expands its
alert title/message pairs into MQTT requests. Each alert body contains a
dedicated `{current_reading}` line labelled for that alert; the SMS worker fills
that final value or removes the line when no usable reading exists. The worker
also reads the same file for the test prefix, warning footer, and
subscribe/unsubscribe confirmations. `sms_templates.py` validates the catalogue
at startup so a missing, empty, or incomplete alert entry fails clearly.
The Home Assistant generator applies the conditional `[TEST]` prefix centrally
to every alert title, so individual title templates contain only their normal
wording. The SMS worker retains a no-duplication prefix check as a safety net.

`labpulse_sms/cli.py` loads config, creates the persistent
`SubscriptionRegistry` and `RecentRequestCache` under the log directory,
creates `SmsSender`, and starts `SMSSubscriber`. In real modem mode it also
starts `SmsCommandMonitor`. SIGTERM/SIGINT becomes a controlled shutdown so
the command monitor stops before the sender drains.

### Subscriber and request cache

`SMSSubscriber` uses fixed client ID `LabPulse-SMS` with `clean_session=False`,
subscribes at QoS 1, advertises a retained Home Assistant status sensor, and
sets an offline last will.

`RecentRequestCache` stores an ordered mapping of request IDs to timestamps and
an in-memory mapping of event keys to their latest time. It provides:

- 24-hour duplicate-ID protection
- a 30-second cooldown per `service:reading:event`
- a 2,000-entry bound
- atomic best-effort persistence to `sms_processed_requests.json`

Only successfully enqueued requests are remembered.

### Sender queue and modem delivery

`SmsSender` owns a bounded `queue.Queue` and one non-daemon worker thread. A
request is expanded to one queued item per configured, currently subscribed
recipient only if the whole active fan-out fits. Suppressed recipients receive
an `unsubscribed` delivery result. Results are reported back through a
callback. One re-entrant lock serializes inbound polling and outbound modem
operations.

In dry-run mode, the worker logs a masked number and reports `logged`. In real
mode `_send_with_mmcli()`:

1. finds the first modem with `mmcli -L`
2. creates an SMS object
3. sends it
4. retries failures up to three times
5. deletes the ModemManager SMS object in `finally`
6. reports `sent` or `failed`

Each per-recipient outcome is published to
`labpulse/sms/result/<request_id>`.

### Subscription commands

`SubscriptionRegistry` builds an exact allow-list from the union of normal and
test recipients and atomically persists an `unsubscribed` set. The same set is
checked after normal/test routing, so a choice applies in both modes. Direct
command confirmations intentionally bypass suppression.

`SmsCommandMonitor` polls ModemManager every five seconds. `SmsSender` lists
SMS objects, reads each through `mmcli --output-keyvalue`, and returns only
complete `received` text messages. The monitor accepts case-insensitive exact
`SUBSCRIBE` and `UNSUBSCRIBE` commands after trimming whitespace. It never
replies to a number outside the current config allow-list and deletes every
inspected received object from modem storage. Paths already handled during the
current process are not answered twice if deletion initially fails.

Warning formatting appends the required unsubscribe/resubscribe footer after
the current reading. Subscription confirmations and non-warning events do not
receive that footer.

## Serial simulator internals

`simulate_serial.py` represents all fake devices as pseudo-terminals. A
`SerialEndpoint` owns the PTY and stable symlink; `ReadingGenerator` produces
Arduino-shaped payloads; `SimulatorService` writes them at the configured
interval.

`disconnect DEVICE` closes one endpoint and removes its stable symlink without
stopping the daemon. `connect DEVICE` creates a replacement PTY behind the same
public path. These commands exercise real serial disconnect/reconnect handling
and the interactive USB assignment workflow while other fake devices continue
running.

The background service listens on
`/tmp/labpulse-fake-serial/control.sock`. Control commands send newline-delimited
JSON over that Unix socket, so changing a scenario does not recreate serial
devices or disconnect containers.

Scenario state is `dict[target, state]`. Normal sensor targets use `normal`,
`recover`, `danger-low`, `danger-high`, and `stale`. The UPS target
`ups_monitor.power` uses `mains`, `battery`, and `stale`.
UPS `stale` emits no payload at all so the real 15-second MQTT expiry is
exercised.

For ordinary sensor targets, `stale` suppresses only the selected reading while
leaving the serial link and peer readings active. Its MQTT entity becomes
unavailable after the configured expiry. A steady sensor that continues
publishing the same value does not expire.

## USB assignment helper internals

`setup_usb_devices.py` reads enabled serial services in config order. Real mode
snapshots `/dev/serial/by-id`; fake mode snapshots
`/tmp/labpulse-fake-serial`. Each unplug step must remove exactly one symlink,
and each replug step must restore the same public name. Ambiguous changes abort
the whole run before any config write.

After operator confirmation, `replace_serial_ports()` changes only the relevant
`serial_port` lines and validates the resulting YAML. `write_config()` keeps one
`.usb-setup-backup` and atomically replaces the config, avoiding partial writes
and repeated timestamped backups.

## Tests as executable documentation

The scripts under `testing/` are grouped by contract:

| Area | Tests |
| --- | --- |
| Config/shared IDs/topics | `test_common_contracts.py`, `test_hardware_factory.py` |
| Drivers and parsing | `test_serial_driver.py`, `test_dht11_driver.py`, `test_max17043_driver.py`, `test_legacy_serial_parser.py` |
| Simulator and USB assignment | `test_simulate_serial.py`, `test_usb_setup.py` |
| MQTT discovery | `test_homeassistant_publisher.py` |
| HA model/generation/registry | `test_homeassistant_entities.py`, `test_homeassistant_generator.py`, `test_power_monitor.py` |
| SMS | `test_sms_container.py` |
| Setup and Compose output | `test_deployment_generation.py` |

When changing a contract shared by packages, run every test that consumes that
contract rather than only the file nearest the edit.
