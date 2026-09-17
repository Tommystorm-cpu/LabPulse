# LabPulse User Guide

This guide explains every user-visible LabPulse feature and how the system
behaves during normal operation and failure. Use the
[Installation guide](INSTALLATION.md) to create or repair an installation and
the [Configuration reference](CONFIGURATION.md) for individual YAML fields.

## Purpose and limits

LabPulse monitors laboratory infrastructure from a Raspberry Pi. It reads
Arduino sensor hubs and supported Pi/network inputs, publishes readings through
MQTT, builds a Home Assistant interface, evaluates alarms, and can send SMS
notifications. An explicitly configured GPIO output can also expose a manual
on/off switch.

LabPulse is a monitoring aid. It is not a safety-rated alarm, emergency
shutdown system, protective interlock or guaranteed notification channel. A
missing alert does not prove that conditions are safe. Equipment with a risk
of injury, damage or loss still needs independent local protection.

The supported reference is the documented Raspberry Pi 5 deployment. Other
platforms can work but require their own acceptance. Real modem delivery,
external Triton/fridge input and generic GPIO control are implemented but still
experimental until accepted with the intended installation.

## The main concepts

A **service** is one independently running acquisition worker, normally one
sensor board or device. A **measurement** is one numeric channel from that
service. A **driver** knows how to communicate with one kind of device or
transport. A **setup** groups measurements by experiment or lab system even
when their wires terminate at different services.

**MQTT** is a lightweight message protocol. Processes publish messages on
named topics through the Mosquitto broker; other processes subscribe to the
topics they need. **Home Assistant** turns these messages into entities,
records history, displays dashboards and evaluates alarm rules. **Docker
Compose** starts each part in an isolated container and defines its files and
hardware access.

The stable mapping is:

```text
physical or simulated source
  -> one LabPulse service container
  -> Mosquitto MQTT broker
  -> Home Assistant entity, history and alarm state
  -> optional SMS request

Home Assistant output switch
  -> one LabPulse output container
  -> configured GPIO line
```

## Installation layout and source of truth

The public operator interface is the `labpulse` command. Its default working
installation is `~/labpulse-live`. The operator-owned source bundle is:

```text
~/labpulse-live/config.yaml
~/labpulse-live/config.d/**/*.yaml   # only when referenced by measurements_file
```

The repository-level files are only starters copied into a new installation.
`config.resolved.yaml` is the complete generated runtime file. `compose.yaml`,
`config.fake.yaml` and LabPulse-managed Home Assistant YAML are also generated.
Editing generated files creates changes that the next setup or configuration
operation will replace.

`labpulse setup` prepares the live directory but does not start the stack.
`labpulse up` starts it; `labpulse down` removes containers without deleting
bind-mounted state; `labpulse restart` restarts all or selected services.
`labpulse update` installs the latest published release, refreshes generated
files, and recreates the complete stack only when the version has changed.
Confirmed incidents during an update follow their usual timing and mute rules.
The SMS worker's persistent MQTT session queues requests while it is unavailable;
failure and recovery requests can arrive together when it reconnects. A failed
update reports the installation or Compose error and does not leave a hidden mute.
After every LabPulse command finishes, a short version check prints a
`labpulse update` reminder only when PyPI has a newer release. The check is
silent on network failure and does not change the command's result.

## Choose real hardware or simulation

Choose the deployment mode before configuring or starting LabPulse. A physical
installation begins with `labpulse setup`; a hardware-free installation begins
with `labpulse setup --fake-hardware`. The installation guide gives the complete
prerequisites and setup procedure for both modes.

Fake mode preserves the complete resolved configuration and therefore produces
the same dashboard and the same enabled service/output containers as real
mode. Sensor workers bypass their configured physical drivers and generate one
sensible changing number for every configured measurement. This applies to
serial, I²C, GPIO, UPS, MQTT JSON and future registered driver types.

Always edit `config.yaml` and its referenced `config.d` fragments, even in fake
mode, and complete `labpulse config` before starting the stack. The guarded
configuration command regenerates the resolved runtime and fake projection.

Output workers keep the configured Home Assistant switches and safety timers,
but hold state only in memory. SMS is forced to dry-run and receives no modem
mount. Fake mode exercises configuration, container lifecycle, MQTT discovery,
dashboards and normal value publication. It deliberately does not prove real
driver behaviour, wiring, calibration, external data delivery or modem delivery.

## Configuring LabPulse

Configuration is part of initial commissioning. Run it after `labpulse setup`
and before the first `labpulse up`:

```bash
labpulse config
```

The guarded editor changes a temporary copy of the complete source bundle.
With no file arguments it asks whether to edit `config.yaml`, an existing
measurement file, or create a new measurement file. Creating one opens it with
the master config so you can add its `measurements_file` reference immediately.
Specific source files can still be opened directly:

```bash
labpulse config config.yaml config.d/triton-01-measurements.yaml
```

Define the MQTT connection, SMS routing, services, drivers, measurements, setups, dashboard tabs, calculated
measurements and any controlled outputs needed by this installation. The
complete field-by-field reference and examples are in
[Configuration](CONFIGURATION.md).

The command validates all referenced files, preserves fake mode where active, renders
Compose and Home Assistant output, checks both output families, installs the
source bundle and generated files, and displays status. It writes the standalone
`config.resolved.yaml` used by real containers. It keeps rolling backups and
attempts to restore the earlier source bundle and output if a downstream check
fails. The rolling copies are kept together in `~/labpulse-live/backups/`.

For real serial services, assign stable `/dev/serial/by-id/...` paths with the
installed USB helper after the devices are connected, then run
`labpulse config` again. Do not start a permanent installation using
`/dev/ttyUSB0` or `/dev/ttyACM0` identities.

There is no automatic hot reload. Use `labpulse config` again whenever the
live configuration changes. A group of filesystem replacements or external
Docker actions cannot be fully transactional; if recreation fails, inspect
logs and regenerate rather than editing `compose.yaml` by hand.

## Starting and verifying LabPulse

Start LabPulse only after `labpulse config` completes successfully:

```bash
labpulse up
labpulse ps
labpulse doctor
```

Open Home Assistant with `labpulse open`, or browse to
`http://<pi-address>:8123` from another
computer. Confirm that every expected service is running, MQTT is connected,
the System Status view reports the expected services, and measurements continue
to update before relying on alarms or notifications.

Generated Compose contains Home Assistant, Mosquitto, one SMS worker, one
container per enabled sensor service and one container per enabled output.
Each process loads and validates its own configuration at
startup.

Docker uses `restart: unless-stopped`. Sensor workers retry unavailable
hardware at their configured interval. Opening a device does not make a worker
healthy: it remains reconnecting until it publishes a valid reading. An
orderly shutdown closes the driver. If a container disappears unexpectedly,
MQTT Last Will and Home Assistant expiry provide separate failure indications.

## Routine operation

```text
labpulse setup       create or refresh the installation
labpulse update      install the latest release and recreate the stack
labpulse up          start all or selected services
labpulse down        stop/remove containers without deleting state
labpulse restart     restart all or selected services
labpulse ps          show container status
labpulse logs        show container logs
labpulse config      edit, validate, regenerate and apply configuration
labpulse doctor      run read-only diagnostics
labpulse backup      create a checksummed state archive
labpulse restore     reconstruct from an archive
labpulse uninstall   remove the live deployment and Docker resources
labpulse open        open local Home Assistant
labpulse firmware    show firmware source/download information
labpulse version     show the installed version
labpulse help        show command help
```

Use `labpulse help COMMAND` for exact options. `--live-dir DIR` precedes the
subcommand. Service names can be supplied to `up`, `down`, `restart` and
`logs`. `labpulse open` opens localhost on the machine running it; an SSH user
normally browses to `http://<pi-address>:8123` instead.

Python workers log to container stdout and `~/labpulse-live/logs/`. Persistent
logs rotate at local midnight and retain the previous seven daily files per
worker, in addition to the current file. `labpulse ps --all`,
`labpulse logs --tail 100` and `labpulse doctor` are the normal first checks.

## Setups and dashboards

A measurement may belong to several logical setups without being duplicated
on MQTT. Setups control dashboard grouping and notification context. The
built-in `main` dashboard contains the Monitor view; configured dashboard tabs
can place groups of setups on additional views.

The generated dashboard provides:

- **Monitor** for setup-grouped measurements, status banners and controlled
  outputs;
- configured custom tabs for selected setups;
- **Alarm Setup** for thresholds, timing, mutes, Test mode and bulk editing;
- **System Status** for a plain-language summary of services, readings and outputs;
- setup and power subviews with detailed controls.

It uses native Home Assistant YAML cards and requires no HACS frontend
extensions. LabPulse manages the dashboard YAML, not Home Assistant `.storage`.

## Measurements, units and identity

Service and measurement mapping keys form stable MQTT topics, Home Assistant
entity IDs, helper IDs and history identity. Changing a label changes display
text; changing a key creates a new identity and can leave old Home Assistant
state behind.

LabPulse publishes the configured unit exactly and does not ask Home Assistant
to convert it. `device_class` is LabPulse metadata used for default icons and
alarm-control grouping. An explicit Material Design `mdi:` icon overrides the
default. `alarmed: false` keeps a value visible without measurement threshold
helpers or notifications; whole-service health remains separate.

Measurements normally expire in Home Assistant when no state arrives within
the configured maximum age. Values are MQTT QoS 0 and not retained; service
status is QoS 1 and retained. QoS 1 can deliver a duplicate and is not an
exactly-once guarantee.

LabPulse excludes its internal alarm helpers, availability classifiers,
automations, and scripts from Home Assistant Recorder. They remain active but
do not consume new history storage. Home Assistant's History target picker
lists registered entities independently, so Recorder exclusions do not remove
them from its **Add target** menu. Physical and calculated measurements remain
recorded. Danger-zone binary sensors also remain recorded because
observation-window calculations depend on their history.

Set `show_graph: true` on a physical or calculated measurement to replace its
compact row with a native card containing the current value and a 24-hour line
graph at the same position in the setup. Measurements without this option
retain the compact list layout.

## Calculated measurements

Home Assistant can calculate a measurement from physical LabPulse entities.
Configuration gives each formula local input names, optional constants,
arithmetic and rounding precision. Only names, finite numbers, parentheses,
unary signs, addition, subtraction, multiplication and division are allowed.
Function calls, powers, attribute access and chains of calculated measurements
are rejected.

The calculated entity becomes unavailable when an input is unavailable or not
numeric, or when a divisor is zero. Its threshold alarm pauses while the value
cannot be evaluated. Calculated measurements run in Home Assistant; they do
not create another container or MQTT measurement.

## Service status and missing readings

The hardware runner schedules reads with a monotonic clock. A valid sample is
published before the online status so recovery does not act on an old value.
Transient errors are rate-limited in logs. A lost connection is closed and
scheduled for retry.

Empty or missing samples do not reset the last-success time. When their age
reaches the configured maximum, the runner closes and reconnects the driver.
Individual entities also expire in Home Assistant. A service may therefore be
running as a container while its device or one measurement is unhealthy.

System Status combines the technical signals into one operator-facing service
state. **Working** means the service and every required reading are current.
**Needs attention** means the service is communicating but has reported a
component problem or lacks required data. **Offline** means LabPulse cannot
currently communicate with the service. Threshold alarm state remains a
separate Normal or Danger decision and is evaluated only when data is present.

A confirmed service outage is one root incident. While it is pending or active,
LabPulse suppresses subordinate unavailable-reading incidents. If the service
remains healthy but one required reading disappears, that reading gets its own
incident after its configured confirmation delay. Measurements with
`required: false` remain visible and show **No recent data — optional**, but
their absence is informational and leaves the service **Working**.

## Measurement alarm behaviour

Each alarmed ordinary or calculated measurement has a threshold state:

```text
Normal -> Danger -> Normal
```

Minimum and maximum thresholds define dangerous values. A measurement enters
Danger only when the required proportion of recent observations is dangerous
within the observation window. This filters a brief spike but deliberately
delays the alarm by the configured evidence requirement.

Recovery requires continuous safe data for the recovery period. The value
must also move beyond the deadband: a high alarm recovers below
`maximum - deadband`, while a low alarm recovers above `minimum + deadband`.
Deadband prevents repeated transitions near a boundary.

Missing or non-numeric telemetry is represented separately from a dangerous
value. Threshold evaluation pauses until valid data returns, then
reconciles against the current thresholds. Alarm state and notification
delivery are separate: muting a
notification never makes a dangerous state Normal. Alarm state is read-only
on the dashboard and changes only when these measurement rules run.

When an active Danger or missing-reading alert needs to be delivered again, open
that measurement's alarm controls and press **Resend active alert**. The action
keeps the alarm state unchanged and repeats the matching warning using the
current Test mode, measurement mute, setup mute, and global mute settings. For
example, after an alarm was first sent to test recipients, disable Test mode
and use this button to send the still-active alert to the normal recipients.

Thresholds, observation window, dangerous proportion, recovery time and
deadband are adjusted in Home Assistant. They are not YAML fields. Home
Assistant restores most helpers from its state; installation automations
initialize missing values safely.

The alarm summary uses color as a quick explanation of the current settings:
an unused minimum or maximum is grey, a threshold currently crossed by the
live reading is red, and the alarm-state tile is red while its state is
**Danger**. A crossed threshold can appear red before the alarm state changes
because the observation-window requirement has not yet been satisfied.

## Power alarm behaviour

Power monitoring uses `mains_present` plus battery telemetry as one composite
alarm. Loss and restoration have separate confirmation times. A confirmed
outage and confirmed restoration are separate events; restoration reports the
duration rather than delaying the initial warning until power returns.

Missing voltage, charge, or mains readings and complete service loss remain
distinguishable from an actual **Running on battery** condition. LabPulse avoids
duplicate alerts after Home Assistant restarts. Raw power readings can
remain visible without power notifications by setting all three measurements
to `alarmed: false`.

## Mutes and Test mode

Global mute blocks all generated notifications. Per-reading and setup mutes block messages for
measurements assigned to that setup. Mutes are manual controls and do not
expire; the dashboard continues to show that delivery is muted.

Test mode starts enabled after every Home Assistant startup. Messages created
in Test mode are prefixed `[TEST]` and route only to `sms.test_recipients`.
Normal recipients are used only after an operator deliberately disables Test
mode. Test mode changes routing, not the underlying alarm calculations.
Muting suppresses delivery and removes that measurement or power condition
from **Current Problems**, without changing its underlying state. System Status
still shows the underlying service and reading condition. A Home Assistant
recovery notification requires an opening Home Assistant notification. A
recovery SMS requires an opening SMS request and obeys the mutes and Test mode
in effect at recovery.

## SMS behaviour

Dry-run is the default. It validates requests, applies routing/deduplication
and logs intended messages without using a modem. Real delivery requires
ModemManager, a provisioned modem and at least one normal recipient.

The SMS worker validates every MQTT request, suppresses reused request IDs and
recent duplicate event keys, then filters unsubscribed numbers. Accepted work
is queued and sent sequentially. Modem discovery, message creation and sending
use `mmcli`; failed attempts are retried and temporary modem messages are
deleted where possible. Delivery is best effort: the in-memory queue does not
survive abrupt process loss and modem acceptance is not proof that a person
read the message.

Configured numbers can reply `UNSUBSCRIBE` or `SUBSCRIBE`. Inbound commands
from numbers outside the configured normal/test lists are ignored. Subscription
and recent-request state are persisted in the live logs directory and included
in backups.

## Controlled GPIO outputs

An output can be placed with the experiment it controls by adding one or more
setup IDs to its live configuration:

```yaml
outputs:
  cooling_valve_enable:
    label: Cooling Valve Enable
    setups: [turbo_pump_experiment]
    driver:
      type: labpulse.gpio_output
      options:
        gpio_line: 18
```

Assigned outputs appear in a **Controls** card inside each selected setup.
Unassigned outputs remain in the Monitor page's general **Controlled Outputs**
section. All enabled outputs remain visible on System Status.

Each enabled output becomes a Home Assistant switch and an independent worker.
The worker accepts exact live `ON` and `OFF` commands only; retained or malformed
commands are rejected. After a write it reads the GPIO latch before publishing
state. Availability is online only when MQTT and output hardware are ready.

On startup, orderly shutdown, MQTT disconnection, hardware failure and retry,
the worker applies its configured logical safe state. An optional
`maximum_active_seconds` returns an output from ON to safe-state OFF; repeated
ON commands do not extend the existing timer. A maximum time cannot be combined
with a safe state of ON. Fake mode omits physical output containers.

The output proves only the Raspberry Pi latch. It does not prove that a relay,
valve or machine moved. Pi GPIO uses 0 V/3.3 V logic; a custom interface must
provide whatever switching, isolation and protection the selected equipment
requires. The local broker has no application-level command authentication, so
do not expose this path to an untrusted network. Automatic alarm-driven
actuation and safety functions are not supported.

## Sensor services and drivers

Every enabled service names a registered driver and the measurements LabPulse
is allowed to publish. Values returned by a driver but absent from the service
configuration are ignored. One faulty service cannot directly stop another
because they run in different containers.

### Arduino serial services

The standard serial driver reads complete newline-terminated records such as:

```text
pressure:1.02|temperature:21.4|humidity:48.2
```

Names and numeric values are separated by a colon, fields by a pipe. The wire
format contains no units; configuration assigns units. Firmware writes `null`
for a channel it could not measure. The parser publishes usable fields from a
partial sample and reports a partial fault; a line with no usable fields is
rejected.

Real installations should identify boards using `/dev/serial/by-id/...`
rather than changeable `/dev/ttyUSB0` or `/dev/ttyACM0` names. The USB helper
guides the operator through unplugging and reconnecting each board, updates
only its configured port and keeps one rolling backup in
`~/labpulse-live/backups/`.

The maintained firmware examples provide pressure/environment, pump-room and
turbo-pump hubs. Firmware owns sampling and calibration; Python owns parsing,
freshness and publication. See the [firmware README](../firmware/README.md).

### SHT40

The SHT40 driver reads temperature and humidity directly over I2C, a shared
two-wire bus addressed by device number. It requests the high-precision
conversion, waits for the device, verifies both checksums, scales the values
and rounds to two decimals. Invalid transfers are not presented as readings.
The default bus is 1 and address is `0x44`.

### DHT11

The DHT11 driver uses an explicit Raspberry Pi/Blinka pin name and publishes
temperature and humidity. Timing failures are treated as transient; loss of
device access causes reconnection. If only one channel is valid, it can be
published with a partial fault. The default read interval is two seconds.

### X1200 UPS

The X1200 driver reads battery voltage and charge level over I2C and external
power presence from a GPIO input. A GPIO-only failure preserves valid battery
telemetry while reporting a component fault. A power service must define
`voltage`, `battery_level` and `mains_present`; these readings are presented as
one dedicated power monitor rather than grouped into experimental setups.

### Generic GPIO input

The GPIO input driver uses one service to read multiple lines on one Linux GPIO
chip. Each configured measurement publishes its logical state as `0.0` or `1.0`.
It is intended for stable digital equipment states, not short-pulse counting or
debouncing. `active_high: false` reverses the electrical interpretation.

Raspberry Pi GPIO uses 0 V and 3.3 V logic. The physical header-pin number and
Linux GPIO line offset are different. Equipment-specific isolation, conversion
and connectors are custom to the eventual hardware.

### Named JSON over MQTT

The MQTT JSON driver accepts a versioned snapshot published by another
computer. Configuration maps exact external field names to stable LabPulse
measurement IDs. Messages include a source timestamp and measurements object.
The driver rejects unsupported versions, wildcard topics, oversized messages,
invalid/future/stale timestamps and samples with no usable mapped values.

It keeps the newest snapshot rather than a history queue. Missing or invalid
individual fields create partial faults while valid fields continue. This is
the implemented path for the optional Triton/fridge logfile publisher, but the
real instrument format, network and units still need installation-specific
acceptance.

## Firmware responsibilities

Arduino firmware owns pin allocation, device sampling, calibration and the
complete serial record. LabPulse Python owns transport parsing and system
health. Change firmware and the serial parser/tests together when names or the
wire contract change. There is no automatic firmware flashing command;
`labpulse firmware` points to the repository source.

## System Status and command-line diagnostics

The Home Assistant **System Status** view shows each service as Working, Needs
attention, or Offline. It lists the latest readings and gives a plain-language
explanation when action may be needed. A reading's time shows when its latest
sample was received, even if the numeric value stayed the same. A status time
shows when that status last changed.

`labpulse doctor` does not change the installation. It checks the live and
runtime configuration, mode, clock/NTP, watchdog, generated files, declared
hardware paths, Docker access and versions, Compose syntax and services, plus
local MQTT and Home Assistant TCP reachability. A warning does not make the
command fail; any FAIL result does.

Passing diagnostics proves that those boundaries are reachable, not that a
sensor is calibrated, an MQTT integration is correct, an SMS arrived or
equipment moved.

## Backup and restoration

`labpulse backup OUTPUT` briefly stops currently running services, copies the
operator configuration, complete Home Assistant configuration/private state,
Mosquitto retained data and SMS state, writes checksums and restarts the same
services. It excludes ordinary Python logs, OS settings and firmware. Existing
output is protected unless `--force` is used.

Archives are owner-readable on Linux but not encrypted. Treat them as secrets
because they contain Home Assistant credentials, phone-number state and
history. Store them outside `~/labpulse-live`.

`labpulse restore ARCHIVE` validates paths and checksums before replacement,
scaffolds a missing installation, stops services and creates an automatic
rollback archive when existing state is present. It restores source state,
regenerates managed files, starts the stack, waits for Home Assistant and runs
Doctor. It attempts rollback if generation/startup fails, but failing storage
or Docker can also prevent rollback.

Host timezone, NTP, watchdog, Docker policy, modem provisioning, USB identity,
GPIO/I2C enablement and wiring are not restored from an archive.

## Known limitations

- The generated deployment assumes a trusted private network and anonymous
  local Mosquitto; it must not be exposed directly to the public internet.
- YAML duplicate mapping keys are not rejected before schema validation; use
  each key once.
- Some possible service/output names can collide with fixed Compose names; use
  clear project-specific IDs.
- DHT pin names are not automatically cross-checked against numeric GPIO line
  allocations.
- The MQTT JSON/Triton path needs separate external network/TLS provisioning
  and real-instrument validation.
- File replacement is atomic per file, not across the complete deployment.
- Driver reads cannot be interrupted by the runner if a third-party library
  blocks forever.
- SMS is best effort and outputs are manual experimental controls, not safety
  mechanisms.
- Firmware calibration, wiring, PCB choice, enclosure fit and equipment motion
  require physical validation.

Future work belongs in the repository [roadmap](../ROADMAP.md), not in this
guide as if it already exists.
