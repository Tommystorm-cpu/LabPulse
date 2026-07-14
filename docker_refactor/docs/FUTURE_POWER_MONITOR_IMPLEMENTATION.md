# Future UPS and Power Monitoring Implementation

## Purpose

This document records the old LabPulse UPS/power-monitor behaviour and the
recommended way to recreate it in `docker_refactor`. It is an implementation
specification, not a description of functionality that already exists in the
current refactor.

The immediate target matches the current live Pi: read INA219 telemetry from
the UPS HAT and infer a probable power outage from sustained battery discharge.
This inference is temporary and must be clearly isolated in generated Home
Assistant power logic so it can later be replaced by a direct mains-present
signal. The INA219 telemetry, dashboard, outage history, mute control, and SMS
delivery should remain useful after that replacement.

The implementation monitors power. It must not switch mains loads, control the
UPS, or shut down the Pi.

## What the old system did

The Raspberry Pi was powered through a Waveshare UPS HAT with two batteries.
An INA219-compatible monitor on I2C bus 1, normally at address `0x42`, was used
to infer whether the UPS was charging, idle, or discharging.

The richer archived implementation:

- configured the INA219 registers before reading it;
- read battery/bus voltage and signed current;
- estimated battery percentage from configurable empty and full voltages;
- classified current above `40 mA` as charging, below `-49 mA` as
  discharging, and the range between them as idle;
- detected an outage after at least `0.25 s` of discharge;
- confirmed restoration with three non-discharging checks;
- sent an outage SMS and a matching recovery SMS;
- recorded the last outage start and duration;
- published Home Assistant discovery and retained MQTT state; and
- ran continuously as a restarting systemd service.

Its dashboard exposed battery level, voltage, current, charging status, last
outage date, and last outage duration.

The later `pi_scripts/powerpub.py` rewrite was simpler. It sampled every two
seconds, inferred battery operation from voltage below `voltage_max - 0.2`, and
sent immediate outage and recovery messages. It dropped the original
confirmation behaviour and last-outage entities. It is useful background, but
it is not the target design.

Source material:

- `archive_v1_pi_code/Python publishing scripts/UPS_Monitoring_code.py`
- `archive_v1_pi_code/Service Scripts/power_monitor.service`
- `pi_scripts/powerpub.py`
- `pi_scripts/config.yaml`
- the UPS panel visible on the old live Home Assistant dashboard

## Important uncertainty to resolve on the live Pi

The repository uses `6.0 V` and `7.92 V` as the empty/full battery range, but
the live dashboard previously showed approximately `4.13 V` and `92.4%`.
Those values cannot have been produced by the archived percentage calculation
using the documented range.

Before deploying percentage calculation or discharge inference:

1. Identify the exact Waveshare UPS HAT model and hardware revision.
2. Confirm whether its reported voltage is the two-cell pack voltage, a
   per-cell voltage, or another rail.
3. Confirm the live I2C bus and address with `i2cdetect -y 1`.
4. Record raw voltage and signed current on mains, while charging, at idle, and
   with mains deliberately removed.
5. Verify current polarity; HAT revision or wiring may reverse it.
6. Determine the correct empty/full voltage values from the real hardware and
   battery arrangement.
7. Check whether the HAT exposes a reliable power-good signal.

Do not deploy the old `6.0 V`/`7.92 V` values merely because they exist in the
repository. Battery percentage is only an estimate and must be labelled as
such.

## Target behaviour

### Telemetry

Publish the following entities under one `Raspberry Pi UPS` device:

| Entity | Type | Notes |
| --- | --- | --- |
| Battery Level | numeric sensor, `%` | Clamped estimate using verified configuration |
| Battery Voltage | numeric sensor, `V` | Calibrated INA219 bus/battery reading |
| Battery Current | numeric sensor, `mA` | Signed current with verified polarity |
| Charging Status | enum/template sensor | `charging`, `idle`, `discharging`, or `unknown` |
| Power State | enum/template sensor | `Normal`, `On Battery`, or `Sensor Fault` |
| Last Outage Start | timestamp/helper-backed sensor | Start of the last confirmed outage |
| Last Outage Duration | duration/helper-backed sensor, `s` | Duration of the last confirmed outage |
| Service Status | existing LabPulse status sensor | Hardware-service health |

Use shared LabPulse identities and MQTT topic helpers. Do not restore the old
hard-coded Home Assistant IDs as a separate naming system.

Routine voltage, current, and battery-level readings should update once per
second. A one-second interval is fast enough for the proposed confirmation
times without creating the old script's roughly 30 ms MQTT stream.

### Responsibility split

The initial implementation should use this ownership boundary:

```text
INA219
  -> Python driver: voltage/current/battery telemetry and hardware health
  -> MQTT
  -> Home Assistant: discharge inference and power-specific state machine
  -> MQTT SMS request
  -> Python SMS worker: validated modem delivery
```

Python must not decide whether an outage alert should be sent. The INA219
driver should publish facts and faults only. Home Assistant should infer the
temporary on-battery signal, confirm outage/recovery, retain lifecycle state,
apply mute controls, compose messages, and request SMS delivery.

### Dedicated power alarm semantics

Power must not use the normal LabPulse five-minute aggregate/percentage alarm
logic. That logic is appropriate for noisy continuous readings such as
temperature, flow, and pressure. Power is a discrete lifecycle event.

The user-facing power states are:

- `Normal`
- `On Battery`
- `Sensor Fault`

Internally, Home Assistant may also track outage and recovery candidates:

```text
Normal -> outage candidate -> On Battery -> recovery candidate -> Normal
   |              |               |                |
   +--------------+               +----------------+

Any state -> Sensor Fault when telemetry becomes stale/unavailable
Sensor Fault -> justified Normal or On Battery after fresh evidence returns
```

Initial configurable defaults:

- telemetry publication: `1 s`;
- confirmed outage: continuously discharging for `10 s`;
- confirmed recovery: continuously not discharging for `15 s`; and
- sensor fault: required evidence stale/unavailable for `15 s`.

The old `0.25 s` threshold is not a requirement and should not be retained as
the default. A short discharge of less than ten seconds may remain visible in
entity history but must not send an outage/recovery SMS pair.

### Restart-safe timing

Do not rely only on a Home Assistant state trigger with `for:`. Its pending
timer does not survive a Home Assistant restart or automation reload.

Generate persistent helpers for at least:

- outage-candidate start/deadline;
- recovery-candidate start/deadline;
- confirmed outage start;
- whether an outage is currently active;
- last completed outage start; and
- last completed outage duration.

Automations should set a persistent deadline when a candidate begins, cancel
it if the evidence reverses early, and confirm it only if the evidence still
matches at the deadline. A Home Assistant-start automation must reconcile the
helpers with current fresh telemetry so restart cannot silently miss an
outage, invent a recovery, or duplicate an SMS.

For outage duration, preserve the first discharging time as the start and the
first stable non-discharging time as the end; the confirmation delay should not
be added to the reported duration.

### Alerts

An outage notification should contain:

- the inferred outage start time;
- clear wording that UPS discharge indicates battery operation;
- current battery level and voltage if valid; and
- an instruction to check the lab supply or circuit breakers.

A recovery notification should contain restoration time, total outage
duration, and confirmation that discharge has stopped.

Only send a recovery for an active, confirmed outage. Respect the normal
LabPulse mute mechanism without hiding the underlying state. Existing SMS
request validation, deduplication, queueing, retries, dry-run mode, and delivery
results must be reused rather than recreated in the power logic.

## Recommended implementation architecture

### 1. Configuration

Extend the validated `services` configuration instead of restoring the old
top-level `ups_monitor` block. A representative live configuration is:

```yaml
services:
  ups_monitor:
    enabled: true
    driver: i2c
    i2c_sensor: ina219_ups
    i2c_bus: 1
    i2c_address: 0x42
    device_name: "Raspberry Pi UPS"
    read_interval_seconds: 1
    battery_telemetry:
      empty_voltage: VERIFY_ON_LIVE_PI
      full_voltage: VERIFY_ON_LIVE_PI
    power_detection:
      source: ups_current_inference
      charging_current_ma: 40
      discharging_current_ma: -49
      outage_confirm_seconds: 10
      restore_confirm_seconds: 15
      maximum_reading_age_seconds: 15
```

The exact schema may be refined during implementation, but all values must be
validated and named configuration. Reject inverted current thresholds,
non-positive timing values, impossible battery ranges, unsupported I2C
addresses, and a power-detection source that is not implemented.

`power_detection.source` is the replacement seam. The initial value is
`ups_current_inference`; a future direct detector can use a value such as
`gpio_mains_contact` without changing user-facing power entities.

### 2. INA219 driver

Add an INA219 UPS driver under `labpulse_hardware/drivers/` and select it from
the existing factory for `driver: i2c` plus `i2c_sensor: ina219_ups`.

The driver must:

- open the configured I2C bus and address;
- configure/calibrate the INA219 for the verified HAT;
- read bus voltage and signed current correctly;
- calculate only the configured battery estimate;
- return explicit failures for missing, malformed, or impossible readings;
- reconnect after the I2C device becomes available again;
- close the SMBus handle cleanly; and
- contain no Home Assistant, outage-state, dashboard, or SMS logic.

Use the archived current-register implementation as a behavioural reference.
Do not copy the later script's apparent use of the shunt-voltage register as if
it were a calibrated current register.

The existing `dict[str, float]` driver contract can remain numeric if charging
status and power state are generated as Home Assistant template entities.

### 3. Generated Home Assistant power package

Create power-specific generation/templates instead of passing the service
through the generic five-minute alarm template.

The generated package must contain:

- a fresh/stale telemetry check;
- a charging-status template based on verified current thresholds;
- a canonical binary evidence entity consumed by the lifecycle automations;
- persistent candidate/outage/history helpers;
- outage, recovery, fault, and Home Assistant-start reconciliation
  automations;
- a dedicated mute control;
- validated SMS-request actions; and
- template entities for `Normal`, `On Battery`, and `Sensor Fault`.

For `ups_current_inference`, the canonical evidence entity is derived from
fresh signed current. Sustained current below the configured discharging
threshold is battery evidence. Charging or stable idle current is
non-discharging evidence. Unknown, unavailable, or stale current is a sensor
fault and must never be treated as zero current or mains restoration.

The dashboard/entity metadata must visibly say that the power state is inferred
from UPS discharge. Do not present it as a direct measurement of mains.

### 4. Future direct-mains option

The preferred future source is an electrically isolated mains-present signal,
for example:

- a mains-powered relay with a voltage-free contact installed on the monitored
  circuit by a competent electrician; or
- for a prototype, a certified enclosed low-voltage adapter driving a
  low-voltage relay or opto-isolated input.

Only an isolated, Pi-safe low-voltage signal may reach GPIO. Never connect
mains or 5 V directly to a 3.3 V Raspberry Pi GPIO.

When `gpio_mains_contact` is implemented:

1. retain the INA219 service for battery voltage, current, percentage, and
   charging telemetry;
2. replace only the generated canonical evidence source;
3. stop using current direction to infer mains presence;
4. reuse the same persistent power lifecycle, entities, dashboard, mute, and
   SMS automations; and
5. remove `ups_current_inference` cleanly when the direct detector is proven.

During migration, both signals may be displayed for comparison, but only the
configured source may drive alerts. Disagreement is diagnostic information,
not permission to run two alert automations.

### 5. MQTT, discovery, and retained state

Use shared identity and topic helpers. Discovery metadata must use correct
device classes and omit `state_class: measurement` from enum, timestamp, and
helper-backed entities.

Retain only state that is deliberately required after reconnect/restart. The
Home Assistant package owns outage lifecycle persistence. Routine telemetry
must use availability/freshness checks so an old retained value cannot appear
current after the hardware service stops.

### 6. Dashboard

Generate a UPS section resembling the useful old layout:

- battery gauge;
- compact voltage/current/charging list;
- clearly labelled inferred power state;
- last outage start and duration;
- service/sensor fault visibility; and
- power mute control in Alarm Setup rather than on every telemetry row.

This is one physical UPS device, not seven independent alarmable sensors.

### 7. Container access

The generated live Compose service must receive only the required I2C device,
normally `/dev/i2c-1`. Do not run the container privileged merely to access
I2C.

Setup/troubleshooting documentation must cover enabling I2C, checking the bus
and address, container permissions/device mapping, inspecting service/MQTT
state, and safely performing a controlled outage test with healthy batteries.

## Test-Pi simulation design

The feature must be testable without an INA219 or UPS HAT before deployment to
the live Pi.

Extend the existing fake-serial simulator rather than requiring fake I2C
kernel devices. The test-Pi `ups_monitor` service should keep the same service
name, reading names, Home Assistant identities, dashboard, and automations as
the live service, but use a simulated serial input:

```yaml
services:
  ups_monitor:
    enabled: true
    driver: serial
    parser: ups_simulator
    serial_port: /tmp/labpulse-fake-serial/ups_monitor
    device_name: "Raspberry Pi UPS"
    read_interval_seconds: 1
    # The same readings, display metadata, telemetry calibration, and
    # power_detection block as the live I2C service.
```

The simulator should emit a simple labelled contract that normalizes to the
same readings returned by the INA219 driver, for example:

```text
Voltage: 4.13 V | Current: 0.0 mA | BatteryLevel: 92.4 %
```

Add controllable power scenarios to `simulate_serial.py`, with commands in the
same style as the existing simulator:

```text
python3 simulate_serial.py set ups_monitor.power mains
python3 simulate_serial.py set ups_monitor.power battery
python3 simulate_serial.py set ups_monitor.power charging
python3 simulate_serial.py set ups_monitor.power stale
python3 simulate_serial.py clear ups_monitor.power
```

Suggested values:

| Scenario | Voltage | Current | Meaning |
| --- | ---: | ---: | --- |
| `mains` | about `4.13 V` until calibrated | stable idle current | Normal inferred mains operation |
| `charging` | plausible rising voltage | above charging threshold | Normal, charging |
| `battery` | plausible falling voltage | below discharging threshold | Outage candidate/On Battery |
| `stale` | no new line | unavailable/fault after configured age |

Do not use deliberately impossible numbers to represent a fault; stop updates
so the actual freshness logic is exercised.

The simulator/parser route is not a backwards-compatibility requirement for
live hardware. It is a hardware-free test adapter that should remain small and
clearly documented.

## Required simulated acceptance run

On the test Pi, with `sms.dry_run: true`:

1. Start `mains` and confirm telemetry, `Normal`, and service health.
2. Select `battery` for less than ten seconds, return to `mains`, and confirm
   that no outage or recovery SMS request is produced.
3. Select `battery` for more than ten seconds and confirm exactly one
   `On Battery` transition and one dry-run outage request.
4. Return to `mains` for less than fifteen seconds, switch back to `battery`,
   and confirm no false recovery or duplicate outage request.
5. Return to `mains` for more than fifteen seconds and confirm one recovery,
   with correct start and duration.
6. Select `stale` for more than fifteen seconds and confirm `Sensor Fault`, not
   `Normal` or `On Battery`.
7. Restore fresh readings and confirm the fault clears only into a state
   justified by current evidence.
8. Repeat sustained outage/recovery while muted and confirm state/history still
   update but SMS delivery is suppressed.
9. Restart Home Assistant during an outage candidate, recovery candidate, and
   confirmed outage; confirm reconciliation and no duplicate messages.
10. Restart Mosquitto and the simulated hardware service independently and
    confirm recovery without manual entity repair.
11. Inspect Home Assistant automation traces, MQTT topics, dry-run SMS logs,
    last-outage helpers, and dashboard state after each case.

Document exact test-Pi setup, generation, Compose, simulator, log-inspection,
and reset commands so another project member can reproduce the run.

## Automated testing requirements

At minimum, add hardware-free tests for:

- strict config validation for INA219 and power settings;
- INA219 register conversion, byte order, signed current, and calibration;
- percentage clamping and current classification boundaries;
- I2C setup failure, disappearance, reconnect, and invalid readings;
- the UPS simulator output and parser;
- stable service/reading identities between simulated serial and live I2C
  configurations;
- exclusion from the generic aggregate alarm generator;
- generation of power-specific helpers, templates, states, and automations;
- ten-second outage and fifteen-second recovery semantics;
- stale evidence becoming `Sensor Fault`;
- candidate cancellation and repeated flapping;
- restart-reconciliation generation and duplicate prevention;
- retained last-outage state and correct duration calculation;
- mute behaviour and dry-run SMS payloads;
- dashboard rendering; and
- Compose generation for fake serial and real `/dev/i2c-1` modes.

Run the existing relevant parser, factory, publisher, Home Assistant generator,
SMS, common-contract, and deployment-generation tests as well as new tests.

## Live-Pi deployment sequence

Only after the complete simulated acceptance run passes:

1. Record the exact live HAT model and battery arrangement.
2. Detect the I2C address and capture raw readings without modifying the live
   system.
3. Verify voltage calibration, current polarity, and thresholds on mains and
   battery.
4. Replace only the test service's serial driver/parser/port with the live
   INA219 I2C settings; keep the same service/readings/display/power settings.
5. Generate Compose and Home Assistant configuration with SMS still in dry-run
   mode.
6. Confirm live telemetry on mains before deliberately removing power.
7. Perform one brief interruption, one sustained outage, and one restoration.
8. Inspect state/history/messages before enabling one controlled real-recipient
   SMS test.

## Acceptance criteria

The implementation is complete when:

- the live HAT model, I2C address, voltage scale, battery range, and current
  polarity are recorded;
- Python publishes telemetry and hardware health but contains no outage-alert
  decision logic;
- power uses its dedicated discrete Home Assistant lifecycle rather than the
  generic five-minute aggregate alarm;
- telemetry updates once per second;
- outage, recovery, and stale thresholds default to `10 s`, `15 s`, and `15 s`;
- pending timers and active-outage state reconcile correctly after Home
  Assistant restart/reload;
- outage inference is clearly labelled and isolated behind the configured
  evidence source;
- all target entities and service health appear under one UPS device;
- the battery gauge agrees with a separately verified measurement closely
  enough for the chosen estimation method;
- brief discharge does not send an outage/recovery pair;
- confirmed outage and recovery each produce at most one eligible SMS request;
- mute suppresses delivery without hiding state or history;
- stale/missing telemetry becomes `Sensor Fault` rather than mains restoration;
- the full automated suite and required test-Pi simulation run pass;
- swapping later to a direct mains evidence entity requires no rewrite of the
  power lifecycle, dashboard, or alert delivery; and
- active architecture, setup, internals, and roadmap documentation are updated
  so this temporary plan is no longer needed.

When this system is implemented, delete this file
