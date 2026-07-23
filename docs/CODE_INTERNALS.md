# LabPulse Code Internals

This guide explains how the implemented code works below the architecture
level. It names the important variables and data structures, shows which
functions call which, and identifies the places where behavior is intentionally
centralized.

Paths in this document are relative to the repository root.

## Recommended documentation order

Read the source in this order if you want to reconstruct the complete system:

1. `config.yaml`
2. `src/labpulse/common/config.py`, `identity.py`, and `mqtt_contracts.py`
3. `src/labpulse/hardware/cli.py`
4. `src/labpulse/hardware/drivers/`
5. `src/labpulse/hardware/serial_parser.py`
6. `src/labpulse/hardware/homeassistant_publisher.py`
7. `src/labpulse/homeassistant/cli.py`, `measurement_model.py`, and `render_model.py`
8. `src/labpulse/homeassistant/core_config.py`, `alarm_package.py`,
   `dashboard_writer.py`, and `dashboard/`
9. `src/labpulse/homeassistant/templates/`
10. `src/labpulse/sms/subscriber.py`, `sender.py`, and `subscriptions.py`
11. `simulate_serial.py` and `setup_usb_devices.py`
12. `generate_compose.sh` and `setup_container_fs.sh`
13. `testing/`

## Shared configuration models

`src/labpulse/common/config.py` is the only Python config reader. `load_config()`
loads YAML and validates it into these Pydantic objects:

```text
LabPulseConfig
  mqtt: MqttConfig
  sms: SmsConfig
  setups: dict[str, SetupConfig]
  services: dict[str, ServiceConfig]

ServiceConfig
  enabled: bool
  driver: DriverConfig
    type: stable registered driver ID
    options: driver-owned validated mapping
  device_name
  measurements: list[MeasurementConfig]
  reconnect_interval_seconds
  read_interval_seconds

MeasurementConfig
  name, label
  subcategory: str | None
  setups: SetupScope
  unit, device_class, icon, state_class
```

The `services` dictionary key is the stable service identity. A
`MeasurementConfig.name` is the stable measurement identity. `device_name`, `label`,
setup metadata, and `subcategory` are presentation. Services follow their
order in `config.yaml`; there is no separate service `display` block.

The MQTT publisher treats `unit` as an exact measurement contract. It retains
`device_class` inside LabPulse, derives or accepts an explicit `mdi:` `icon`,
and publishes that icon without publishing the convertible Home Assistant
device class. This prevents regional unit conversion while keeping readings
visually distinct.

Important computed properties are:

- `MeasurementConfig.display_label`: configured label or a title made from `name`.
- `SetupConfig.display_label(setup_id)`: configured label or a title made from
  the stable setup ID.

`SmsConfig.validate_recipients()` applies the same normalization and
international-number validation to `recipients` and `test_recipients`.
`require_real_recipients()` requires at least one normal number when `dry_run`
is false. Test requests with no configured test recipients fail closed instead
of falling through to the normal emergency list.

`load_config()` exits the process after logging readable YAML or validation
errors. Callers therefore receive a valid `LabPulseConfig`, not a partly valid
dictionary.

## Shared identity and MQTT contracts

`src/labpulse/common/identity.py` contains four small but critical functions:

- `slug(value)` converts arbitrary text to lowercase underscore form.
- `title(value)` converts a machine key to a display title.
- `stable_id(*parts)` prefixes normalized parts with `labpulse_`.
- `entity_id(domain, *parts)` combines a Home Assistant domain and stable ID.

Both the hardware publisher and Home Assistant generator import these
functions. This prevents the two sides from guessing different IDs.

`src/labpulse/common/mqtt_contracts.py` owns all cross-process topic strings:

```text
home/sensor/<service>/<measurement>/state
home/sensor/<service>/status
homeassistant/sensor/<service>_<measurement>/config
homeassistant/sensor/<service>_status/config
labpulse/sms/send
labpulse/sms/status
labpulse/sms/result/<request_id>
```

It also defines `SmsRequest`, the exact JSON contract accepted by the SMS
worker. Extra fields are forbidden. Supported events are `sensor_fault`,
`warning`, `recovery`, and `test`.

## Hardware service execution

`python -m labpulse.hardware` enters `src/labpulse/hardware/cli.py`.

`parse_args()` accepts:

- `--service`: required config service key
- `--config`: config path
- `--print`: log valid measurement dictionaries
- `--no-mqtt`: acquire without publishing
- `--once`: stop after one valid measurement

`main()` is intentionally orchestration-only:

```text
load config
get selected ServiceConfig
build_driver(service_name, service_cfg)
create HomeAssistantMqttPublisher unless --no-mqtt
build RunnerPolicy from service timing
create HardwareRunner
runner.run_forever(once=...)
```

`HardwareRunner` owns connection state, status transitions, reconnect
throttling, read scheduling, freshness, expected failure handling, and
idempotent driver/publisher cleanup. Its `step()` method performs one
connection or read action, which makes the complete lifecycle deterministic in
hardware-free tests. Blank serial reads sleep for 0.1 seconds so a quiet device
does not cause a busy loop.

### Driver lifecycle API and registry

`BaseSensorDriver` provides only stable identity and logging:

```python
self.name: str
self.logger: logging.Logger
```

Implementations provide `connect()`, `read()`, and `close()`. `read()` returns
`ReadingBatch` or `None`. A batch contains normalized numeric measurements and
optional `ComponentIssue` records for partial faults such as an unavailable
X1200 mains GPIO.

Expected failures cross the boundary through explicit exceptions:

- `DriverUnavailable`: connection could not be established;
- `ConnectionLost`: an established handle is no longer usable;
- `TransientReadError`: one sample failed but the connection remains usable.

Drivers do not retry, publish status, track freshness, or schedule reads.
`HardwareRunner` converts the contract outcomes into `online`, `reconnecting`,
`disconnected`, and `error`, suppresses duplicate status publications, and
continues the service process through recoverable failures.

Each hardware module contains its implementation, Pydantic options, builder,
container-resource resolver, default interval, and one exported
`DriverDefinition`. `hardware/registry.py` discovers those modules and exposes
`build_driver()` without device-specific selection branches. Compose uses the
same definition and validation model as the runtime.

The built-in IDs are `labpulse.serial_pipe`, `labpulse.dht11`, and
`labpulse.x1200`. All driver modules are inspected during discovery, so their
Pydantic models and standard-library code must be safe to import. Hardware
vendor libraries remain lazy imports inside `connect()` or a helper it calls.
In particular, serial and I2C workers do not import Blinka, `board`, or
`adafruit_dht`; eager imports can open `/dev/gpiochip0` in unrelated containers
and prevent the DHT worker from acquiring GPIO4.

To add another built-in driver:

1. Copy `src/labpulse/hardware/drivers/driver_template.py` to a new module.
2. Keep its strict options model, `Driver`, builder, structured resource
   resolver, and exported `DRIVER` definition together in that module.
3. Add registry and Compose-resource tests using fake dependencies; do not add
   device-specific fields to `ServiceConfig`, branches to `build_driver()`, or
   raw Compose YAML.
4. Add the service with only `driver.type` and `driver.options` in config.

The registry is deliberately internal for now. It provides one well-tested
extension seam for repository contributors without yet promising that arbitrary
third-party Python packages are safe to load.

The X1200 driver performs read-only MAX17043 VCELL and SOC transactions,
publishes voltage and gauge-calculated battery level, and reads the direct
mains GPIO. I2C faults raise `ConnectionLost` for runner-managed recovery. A
GPIO-only fault returns the valid battery values with a `gpio_fault` component
issue. It does not publish current or charging status because the installed
hardware does not measure them.

### Serial driver

`drivers/serial_pipe.py::Driver` holds:

```python
port, baud_rate
ser                         # pyserial handle or None
parser: SerialParser
```

`connect()` opens `serial.Serial(..., timeout=2)` and raises
`DriverUnavailable` when the path cannot be opened. `read()` decodes one line
and sends it to the standard parser; a disappearing device raises
`ConnectionLost`. `close()` releases the serial handle and is safe to repeat.

The container stays alive when a USB device disappears. This is why reconnect
logic belongs in `HardwareRunner` rather than every driver or Compose restart
behavior.

### DHT11 driver

`drivers/dht11.py::Driver` stores only the Blinka pin name and Adafruit
device object.

`connect()` resolves the named attribute from `board` and constructs
`adafruit_dht.DHT11` with `use_pulseio=True`. This is the mode verified against
the installed DHT11 and Raspberry Pi; GPIO4 must remain exclusive to the DHT
worker.

`read()` translates an ordinary DHT `RuntimeError` or incomplete sample into
`TransientReadError`. Unexpected GPIO/library failures become
`ConnectionLost`. `HardwareRunner` applies `read_interval_seconds`, limits
failure logging, changes status to `error` after
`maximum_measurement_age_seconds`, closes failed devices, and retries using
`reconnect_interval_seconds`. A valid sample is returned in `ReadingBatch` as:

```python
{"temperature": float, "humidity": float}
```

### Serial parser

`serial_parser.py::SerialParser` accepts the one supported Arduino contract:

```text
flow1: 2.45 | flow2: 3.10 | temp0: 20.11
```

Keys are lower-cased. Values must be unit-free finite numbers. Firmware emits
values in their final configured units; invalid channels are written as
`null` and omitted by the parser. Bare values, unit-bearing legacy text, JSON,
and non-finite numbers are rejected. There is no parser selector, device-specific
conversion, or compatibility branch. Valid lines produce a normalized
`dict[str, float]`, such as:

```python
{"flow1": 2.45, "temp0": 20.11}
```

## MQTT discovery and state publishing

`HomeAssistantMqttPublisher` is created once per hardware service. Its most
important state is:

```python
measurement_configs: dict[str, MeasurementConfig]
discovered_measurements: set[str]
status_discovery_published: bool
client: paho.mqtt.client.Client
```

`publish(measurements)` first calls `configured_measurements()`. Keys not declared in
the service’s `measurements` list are ignored and logged. This makes config the
allow-list for MQTT entities.

Discovery is published once per measurement when that measurement first appears.
Measurement discovery contains its label, state topic, stable `unique_id`,
`object_id`, `default_entity_id`, device grouping, and optional unit,
device-class, and state-class metadata. Discovery and service status are
retained; live numeric measurement values are not retained.

Service status has its own MQTT sensor and is published when the driver changes
between values such as `online`, `disconnected`, and `reconnecting`.

## Home Assistant generator

The public command is `generate_homeassistant_config.sh`. The shell wrapper
owns paths and generated-file permission checks. It then calls:

```bash
.venv/bin/python -m labpulse.homeassistant \
  CONFIG_PATH HA_CONFIG_DIR
```

`src/labpulse/homeassistant/cli.py::main()` performs the Python orchestration:

```text
load validated config
build canonical measurement catalog and RenderModel
render_core()
render_alarm()
render_yaml_dashboard()
```

### Render-model data structures

The Home Assistant-specific boundary is split by responsibility:

- `measurement_model.py` declares measurement render data and derives its
  threshold-editor bounds and deterministic IDs in `from_config()`.
- `render_model.py` declares aggregate render data and builds it directly from
  validated config and the canonical catalog with `RenderModel.from_config()`.
- `paths.py` derives generated output locations.

`RenderModel` contains an ordered `list[ServiceModel]`. Its `measurements` property
flattens that into `list[tuple[ServiceModel, MeasurementModel]]`, preserving access
to both parents during per-measurement expansion.

`ServiceModel` contains:

- stable identity and physical `device_name` label
- deterministic MQTT status unique and entity IDs
- entity IDs for four service-level timing helpers
- `list[MeasurementModel]`

`MeasurementModel` contains:

- measurement identity and label
- logical setup notification context derived from the canonical catalog
- deterministic MQTT measurement unique and entity IDs
- every generated alarm helper/entity ID
- a `ThresholdModel` with units, steps, and editable ranges

`MqttEntity` contains the complete generated MQTT identity:

```python
unique_id
entity_id
```

LabPulse treats these IDs as infrastructure. Friendly labels belong in
`config.yaml`; manually renaming generated entity IDs in Home Assistant is
unsupported because static dashboard and alarm YAML reference the stable IDs.

`GeneratorPaths` derives all output locations from `config_path` and
`ha_config_dir`; renderers do not manually reconstruct paths.

### Building the model

`RenderModel.from_config()` follows service order from `config.yaml`, skips
disabled services, and delegates to each model class's named `from_config()`
constructor. This keeps derived identities beside the data that owns them and
avoids a parallel builder module.

Editable threshold-helper ranges are inferred from the normalized measurement name:

| Name contains | Editor range concept |
| --- | --- |
| `flow`, `press`, `pressure` | non-negative process values |
| `temp`, `hum` | environmental values |
| anything else | generic numeric values |

The generated threshold helpers deliberately omit `initial` values. Operators
set Min, Max, and Deadband in the Alarm Setup view, and Home Assistant restores
those values thereafter. The option order makes fresh alarm-mode helpers begin
Disabled and fresh alarm-state helpers begin Normal.

One first-install marker enables the global notification mute exactly once.
Both that marker and the mute helper then use Home Assistant's restored state,
so an operator's later unmute survives restarts and regeneration. Service-level
observation and recovery timing retains its separate one-time initializer.

### Template expansion

There are two deliberately separate syntaxes:

- `[[ service.label ]]`, `[[ measurement... ]]`, and `[[ model... ]]` are expanded
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

`core_config.render_core()` writes `configuration.yaml`.
`ensure_ui_yaml_files()` creates empty `automations.yaml`, `scripts.yaml`, and
`scenes.yaml` only when absent.

### YAML dashboard rendering

For the visual end-to-end pipeline from `cli.py` through the in-memory config,
catalog, and render model to every generated Home Assistant file, see the
[Home Assistant generator flow](../src/labpulse/homeassistant/README.md#generation-flow).

Dashboard generation is deliberately split at view boundaries:

- `dashboard/monitor.py` owns logical setup projection and Active Problems;
- `dashboard/alarm_setup.py` owns the landing page and focused alarm subviews;
- `dashboard/diagnostics.py` owns the physical-service projection;
- `dashboard/primitives.py` contains shared native-card builders, template
  loading, and canonical-catalog-to-render-model lookups; and
- `dashboard_writer.py` fixes view order and serializes the assembled document
  to `homeassistant/config/labpulse-dashboard.yaml`.

This division keeps page-specific policy next to the page it affects while
retaining one canonical catalog and one set of physical entity identities.
`templates/core/configuration.yaml.j2` registers that file as the YAML-mode
`labpulse-monitor` dashboard. The generated file starts with a warning because
normal regeneration replaces it.

The Monitor view projects the same physical measurement entities into each
explicitly selected setup in deterministic order. Shared measurements may appear
under more than one setup, but every appearance references the same entity.
Dedicated power telemetry bypasses setup projection and uses its own column.
Measurements are ordered and grouped by `subcategory`, with a deterministic
fallback for measurements without one.

The first Monitor column begins with a native `entity-filter` card titled
**Active Problems**. Nesting it inside an existing masonry column prevents the
page from repacking when the card appears. It is built from the canonical
physical catalog, so shared measurements are not duplicated. It watches only
persistent lifecycle state: confirmed service-fault latches, ordinary measurement
`Danger`/`Sensor Fault` alarm states, and power `On Battery`/`Sensor Fault`.
Each ordinary-measurement row requires its individual alarm mute to be off. A
shared measurement remains visible while any owning setup is unmuted and is
hidden only when every owning setup is muted, matching its single-notification
semantics. The global mute deliberately does not conceal operational state.
Home Assistant removes the card when no eligible confirmed state matches.

Alarm Setup is a native Sections view with Configure Alarms first, followed by
Notification Controls and Group Alarm Settings. The group editor is collapsed by
default; when opened it presents target, settings and values, review, and Apply as
a numbered workflow. Each value input appears only while its matching Change
switch is on. It uses independent
apply flags for every common value and recovery-deadband compatibility family.
`BulkAlarmTarget` and `BulkDeadbandGroup` carry canonical measurement keys and
explicit helper IDs, so the dashboard never derives identity or compatibility
from labels. Target changes clear every apply flag. Apply snapshots the target,
flags, and values; writes only selected fields; reports success; and clears the
flags only after every write completes.

Every non-empty setup has a hidden three-column Sections subview. Native screen
conditions select an explicit desktop or mobile projection of the same entities.
Desktop measurement rows use six equal cells for current value, alarm state,
minimum, maximum, notification mute, and right-aligned Configure/Close. Mobile
rows place the current value and alarm state at full width, the two thresholds
and notification mute side by side, and Configure/Close at full width. Closed
rows have no section background.
Measurement tiles inherit the MQTT entity's device-class icon. The existing
expansion helper reveals a two-column desktop form or stacked mobile form plus
live alarm state. Dedicated power controls use their own subview. Shared
visual controls reuse the same physical helper IDs. A setup
containing shared measurements requires confirmation before its mute is enabled and
names those measurements in the warning; unmuting does not require confirmation.
Derived alarm zones and observed danger remain read-only inside the editor.
Diagnostics contains no ordinary alarm engine state. It uses native Sections
and the physical service projection in config order: one section per hub with
its `device_name`, a connection
tile, paired health tiles, physical measurements once, and power lifecycle
diagnostics where applicable. **Service Health** is the immediate derived
problem signal from the current connection status. **Confirmed service fault**
is the persistent latch set only after `fault_confirm_seconds` and cleared only
after `recovery_confirm_seconds`; alerts and Active Problems use this stable
state.

There is no storage-backed dashboard renderer, dashboard synchronization path,
or live registry-resolution path. Generation is fully offline and uses the
same stable entity-ID functions as MQTT discovery.

## Alarm state machine

`alarm_package.py` reshapes the rules in `templates/alarm/alarm_logic.yaml` into native
Home Assistant package sections. Service rules are expanded once per service;
measurement rules once per measurement.

### Generated helpers

Each service receives:

- required danger percentage
- observation-window seconds
- required recovery seconds

Each measurement receives:

- persistent alarm state: Normal, Danger, or Sensor Fault
- alarm mode: Disabled, Low Only, High Only, or Range
- mute and dashboard-expansion booleans
- minimum, maximum, and recovery-deadband numbers

### Calculated entities

`danger_zone` is on when a numeric measurement violates the active threshold mode.
Disabled or invalid measurements are not considered threshold danger.

`recovery_zone` applies the deadband inward. For example, a Low Only measurement
recovers only at or above `minimum + deadband`. Disabled mode is considered
recovered when the measurement is numeric.

`sensor_fault_zone` is on when the measurement is invalid/unavailable or service
health reports an explicit error/unknown condition. MQTT discovery sets
`expire_after` from `maximum_measurement_age_seconds`, so Home Assistant makes a
measurement unavailable only when its MQTT samples actually stop. Repeated samples
with an unchanged numeric value remain healthy. `disconnected` and
`reconnecting` do not immediately fault a previously valid measurement: MQTT
expiry acts as the reconnect grace period. After expiry, ordinary measurements use
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

Sensor-fault reconciliation is condition-driven rather than relying only on the
instantaneous `on` to `off` fault-zone edge. If fresh data returns in the danger
zone before the observation window contains enough evidence, the state remains
`Sensor Fault` temporarily and moves to `Danger` when the configured percentage
is reached. The same reconciliation repairs a persisted `Sensor Fault` after a
Home Assistant restart, and moves directly to `Normal` when the recovered value
is already inside the recovery zone.

Sensor fault takes priority. Danger entry excludes faulted and Disabled
measurements. State changes occur whether muted or not; only notifications and SMS
publishing are inside the combined global/setup/individual mute check. At least
one setup assigned to a shared measurement must be unmuted. No mute helper is
used as a state writer for another mute helper. Physical service-health and dedicated
power alarms are not gated by logical setup mutes. Test mode
adds `[TEST]` to titles and sets the validated request flag consumed by the SMS
recipient router. Its explicit `initial: true` setting makes every Home
Assistant start default to test delivery until an operator turns it off. When a confirmed fault clears, Home
Assistant creates a persistent sensor-restored notification after reconciling
the measurement to Normal or Danger and publishes a validated recovery SMS request.
Because the state does not enter Sensor Fault during an unconfirmed startup
transient, ordinary container restarts do not emit a recovery for every measurement.

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

While the whole-service problem is present or latched, new per-measurement fault,
Danger, and recovery transitions are gated. MQTT measurements may still expire for
honest dashboard presentation. A measurement that was already in a genuine Sensor
Fault remains latched and recovers only after the service returns and that
measurement becomes valid. Once the service recovery period ends, ordinary stale
measurement confirmation resumes, providing an additional telemetry grace period.

Danger notifications include the current measurement, active threshold, observed
danger percentage, observation window, approximate time in danger, and required
percentage. Sensor-fault notifications distinguish unavailable/non-numeric
measurements from unhealthy service status. The SMS contract calls the optional
value `current_measurement`, and rendered SMS labels it `Current Measurement`. Every
ordinary measurement notification also includes one canonical context line:
one affected setup or selected affected setups. This text is derived from the
catalog and does not create additional
automations, MQTT requests, or cooldown identities.

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
`src/labpulse/common/sms_templates.yaml`. The Home Assistant generator expands its
alert and notification title/message pairs into MQTT requests. Each alert body contains a
dedicated `{current_measurement}` line labelled for that alert; the SMS worker fills
that final value or removes the line when no usable measurement exists. The worker
also reads the same file for the test prefix, warning footer, and
subscribe/unsubscribe confirmations. `sms_templates.py` validates the catalogue
at startup so a missing, empty, or incomplete alert entry fails clearly.
The Home Assistant generator applies the conditional `[TEST]` prefix centrally
to every alert and notification title, so individual title templates contain only their normal
wording. The SMS worker retains a no-duplication prefix check as a safety net.

`src/labpulse/sms/cli.py` loads config, creates the persistent
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
- a 30-second cooldown per `service:measurement:event`
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
the current measurement. Subscription confirmations and non-warning events do not
receive that footer.

## Serial simulator internals

`simulate_serial.py` represents all fake devices as pseudo-terminals. A
`SerialEndpoint` owns the PTY and stable symlink; `MeasurementGenerator` produces
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

For ordinary sensor targets, `stale` suppresses only the selected measurement while
leaving the serial link and peer measurements active. Its MQTT entity becomes
unavailable after the configured expiry. A steady sensor that continues
publishing the same value does not expire.

## USB assignment helper internals

`setup_usb_devices.py` reads enabled serial services in config order. Real mode
snapshots `/dev/serial/by-id`; fake mode snapshots
`/tmp/labpulse-fake-serial`. Each unplug step must remove exactly one symlink,
and each replug step must restore the same public name. Ambiguous changes abort
the whole run before any config write.

After operator confirmation, `replace_serial_ports()` changes only the relevant
`driver.options.port` lines and validates the resulting YAML. `write_config()` keeps one
`.usb-setup-backup` and atomically replaces the config, avoiding partial writes
and repeated timestamped backups.

## Tests as executable documentation

The scripts under `testing/` are grouped by contract:

| Area | Tests |
| --- | --- |
| Config/shared IDs/topics | `test_common_contracts.py`, `test_hardware_factory.py` |
| Driver lifecycle | `test_hardware_runner.py` |
| Drivers and parsing | `test_serial_driver.py`, `test_serial_parser.py`, `test_dht11_driver.py`, `test_x1200_ups_driver.py` |
| Simulator and USB assignment | `test_simulate_serial.py`, `test_usb_setup.py` |
| MQTT discovery | `test_homeassistant_publisher.py` |
| HA model/generation/registry | `test_setup_grouping.py`, `test_homeassistant_entities.py`, `test_homeassistant_generator.py`, `test_yaml_dashboard.py`, `test_notification_context.py`, `test_power_monitor.py` |
| SMS | `test_sms_container.py` |
| Setup and Compose output | `test_deployment_generation.py` |

When changing a contract shared by packages, run every test that consumes that
contract rather than only the file nearest the edit.
