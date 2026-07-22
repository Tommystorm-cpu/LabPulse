# LabPulse Architecture

LabPulse is a Raspberry Pi monitoring system. Sensor services acquire facts,
MQTT transports them, Home Assistant decides whether they are dangerous, and a
separate SMS worker delivers alerts. The split keeps hardware failures,
operator settings, presentation, and modem behavior independently testable.

This document describes the implemented `docker_refactor/` architecture. Code
and function details are in [CODE_INTERNALS.md](CODE_INTERNALS.md).

## System at a glance

The repository is used to generate a live Compose project at:

```text
~/labpulse-ha/
```

The running system is:

```text
Physical or simulated sensors
        |
        v
labpulse-<service> containers       one per enabled service
        |
        | MQTT discovery, values, and health
        v
Mosquitto
   |                         |
   v                         v
Home Assistant          labpulse-sms
   |                         |
   | alarm transition        | dry-run log or mmcli
   +---- labpulse/sms/send -->+----> cellular modem
```

Home Assistant and Mosquitto are infrastructure containers. Each configured
sensor service and the SMS worker run the project’s Python code.

## The two main flows

### Deployment and generation

```text
repository docker_refactor/
  -> setup_container_fs.sh
  -> ~/labpulse-ha/
       config.yaml                  live user configuration
       generate_compose.sh
       generate_homeassistant_config.sh
  -> compose.yaml                   generated deployment
  -> Home Assistant YAML/dashboard generated from config.yaml
  -> docker compose up
```

`setup_container_fs.sh` is the bootstrap and code-copy step. After it has run,
normal operator work happens from `~/labpulse-ha`, not from the checkout.

### Runtime measurements and alerts

```text
sensor
  -> driver
  -> normalized dict[str, float]
  -> configured-measurement filter
  -> MQTT discovery and state topics
  -> Home Assistant sensor entities
  -> zone sensors and history statistics
  -> alarm-state automations
  -> persistent notification and MQTT SMS request
  -> validated SMS queue
  -> dry-run log or ModemManager
```

UPS power is the deliberate exception to the generic zone/history path. Its
X1200 driver publishes MAX17043 battery telemetry plus a normalized
`mains_present` value read directly from GPIO6. Home Assistant uses a dedicated
`Normal` / `On Battery` / `Sensor Fault` lifecycle. Brief GPIO changes are
confirmed for configured periods, and one persistent outage latch prevents
duplicate warning or recovery messages. Voltage and percentage do not decide
whether an outage occurred.

The key boundary is between facts and decisions:

- Python hardware services publish values and connection health.
- Home Assistant owns thresholds, timing, mute controls, alarm state, and
  operator-facing notifications.
- The SMS worker validates and delivers an already-decided alert. It does not
  decide whether a measurement is dangerous.

Each hardware publisher also owns an MQTT Last Will on its existing retained
status topic. A lost process or MQTT connection therefore publishes `offline`.
Home Assistant classifies `disconnected`, `reconnecting`, `error`, `offline`,
`unknown`, and `unavailable` as whole-service failures. After confirmation it
sends one hub-level alert and suppresses new per-measurement stale faults until the
service-wide condition has recovered. Component degradation such as the X1200
`gpio_fault` remains outside that classification and keeps its dedicated alert.

## Runtime containers

### `labpulse-homeassistant`

Home Assistant provides the UI, entity registry, recorder/history, editable
helpers, template sensors, alarm transition automations, and dashboard. It uses
host networking so its MQTT integration connects to `127.0.0.1:1883`.

### `labpulse-mqtt`

Mosquitto is the message boundary between components. Compose exposes it only
on the Pi loopback address. LabPulse Python containers connect through the
Compose hostname `mosquitto`; Home Assistant connects through the host address
`127.0.0.1`.

### `labpulse-<service>`

Every enabled key under `services:` becomes one container, for example:

```text
pressure_monitor -> labpulse-pressure-monitor
pump_room        -> labpulse-pump-room
```

All use the same entry point:

```bash
python -m labpulse_hardware --service <service-key>
```

The service key selects configuration and therefore its driver, measurements,
labels, and hardware path. One container per service isolates device
disconnects and restarts.

### `labpulse-sms`

The SMS worker has a persistent MQTT session and a bounded background delivery
queue. Validated requests carry a strict `test_mode` flag: normal requests fan
out to `sms.recipients`, while test requests fan out only to
`sms.test_recipients`. In safe `dry_run` mode it only logs masked recipients.
In real mode it uses `mmcli`, so Compose additionally exposes D-Bus and devices
to this one container. It also accepts `SUBSCRIBE` and `UNSUBSCRIBE` only from
numbers in either configured list. One persistent subscription choice filters
both normal and test delivery.

## Python package boundaries

### `labpulse_common`

Shared contracts only:

- Pydantic configuration models and the one config loader
- stable slug/entity identity rules
- MQTT topic and SMS payload contracts
- common logging setup

It must not acquire hardware, render dashboards, or send messages.

### `labpulse_hardware`

Owns the live acquisition process:

- service-loop orchestration
- driver selection
- serial, DHT11, and X1200 UPS drivers
- strict parsing of the standard pipe-delimited serial format
- MQTT discovery, state, and service-health publishing

Its output boundary is a normalized `dict[str, float]` plus a health string.

### `labpulse_homeassistant`

Runs as an offline generator on the Pi host, not as a long-running sensor
container. It turns typed config into:

- Home Assistant core configuration
- the generated alarm package
- the generated `labpulse-dashboard.yaml` dashboard

### `labpulse_sms`

Owns alert-request validation, duplicate/flood protection, recipient fan-out,
the bounded delivery queue, persistent allow-listed subscription commands,
dry-run logging, `mmcli` retries, and result/status publishing.

## Configuration and state ownership

The live config describes deployment facts:

```text
~/labpulse-ha/config.yaml
```

It owns enabled services, hardware access, measurements, display
metadata, MQTT connection settings, SMS mode, and recipients.

Thresholds, alarm modes, and per-measurement timing are configured through the
generated masonry Alarm Setup landing page and its native setup subviews. The
landing page pairs each setup navigation tile with its setup mute control while
retaining the same control in the corresponding subview. A confirmed
bulk editor copies timing to all ordinary measurements or one logical setup. These
values are Home Assistant state rather than deployment configuration. A fresh
installation starts with every ordinary-measurement alarm mode disabled and the
global notification mute enabled. After that first initialization, Home
Assistant restores the operator's choices across restarts.

Each setup subview separates measurement selection, editable alarm settings, and
read-only live alarm status into three columns. The live column owns alarm state,
observed danger, and danger/recovery/fault zones. The Diagnostics view remains
physical and uses one compact masonry column per service: connectivity, paired
health indicators, latest raw measurements, and dedicated power state.

The Monitor view also has a native filtered problem summary derived from the
canonical physical catalog. It is nested inside the first masonry column,
absent while healthy, and surfaces only confirmed service faults, persistent
measurement alarm states, and power lifecycle faults. This avoids threshold-edge
flicker, page-wide masonry repacking, new aggregate helpers, and duplicate
shared measurements. Per-entity filter conditions omit individually muted
measurements and shared measurements whose owning setups are all muted. The
global notification gate does not conceal system health.

An X1200 service receives only its configured `/dev/i2c-N` device mapping.
It does not require privileged mode or a broad `/dev` mount.

Home Assistant owns operator state:

- minimum/maximum thresholds
- alarm mode and mute state
- per-measurement observation, danger-percentage, and recovery timing
- accounts and integrations

The LabPulse dashboard layout is generated from `config.yaml` and the
canonical measurement catalog. Normal regeneration replaces that one YAML file
without changing operator-tuned helper values or Home Assistant-owned state.

## Generated versus user-owned files

| File | Owner | Normal regeneration |
| --- | --- | --- |
| `compose.yaml` | Compose generator | replaced |
| `configuration.yaml` | Home Assistant generator | replaced |
| `packages/labpulse_generated.yaml` | alarm generator | replaced |
| `labpulse-dashboard.yaml` | dashboard generator | replaced |
| `automations.yaml`, `scripts.yaml`, `scenes.yaml` | Home Assistant UI | created only if missing |

`configuration.yaml` registers the generated file as the YAML-mode
`labpulse-monitor` dashboard. LabPulse has no private-dashboard mutation,
backup, restore, or synchronization path.

## Identity contract

Machine identifiers are derived from the service key and measurement name. For:

```yaml
services:
  pressure_monitor:
    measurements:
      - name: pressure
```

the shared identity functions produce:

```text
stable unique ID: labpulse_pressure_monitor_pressure
entity ID:       sensor.labpulse_pressure_monitor_pressure
state topic:     home/sensor/pressure_monitor/pressure/state
```

Labels such as `Pressure` are presentation and can change safely. Renaming the
service key or measurement name changes MQTT topics, unique IDs, generated helper
IDs, and history continuity.

LabPulse entity IDs are generated infrastructure referenced by static alarm and
dashboard YAML. Change friendly labels in `config.yaml`; do not manually rename
LabPulse entity IDs through Home Assistant.

## Home Assistant alarm ownership

Each measurement has a persistent state:

```text
Normal
Danger
Sensor Fault
```

Instantaneous binary sensors describe whether the measurement is in the danger,
recovery, or fault zone. A `history_stats` sensor measures the percentage of
the observation window spent in danger. Automations write the persistent state
only when the timing and zone conditions are met.

Per-measurement and power mutes suppress their own persistent notifications and SMS
requests. Each logical setup also has a restored-state mute that gates the
ordinary measurements assigned to it. The independent global mute gates every
delivery path without writing setup, measurement, or power mute helpers, so every
choice survives other mute cycles. A shared measurement has one physical alert; all
of its setup gates must be open for that alert to be delivered. Setup mutes do
not apply to physical service-health alarms or dedicated power alarms. Test mode
does not alter alarm evaluation; it marks notifications `[TEST]` and sends SMS
only to the configured test list. Zone calculation and state transitions
continue under either mode.

The Alarm Setup phone-book action publishes a validated `notification` request
through the same path. It therefore inherits test/live recipient selection,
persistent unsubscribe filtering, deduplication, and delivery-result reporting.

## Failure behavior

- A missing serial device does not terminate the service loop. The driver
  reports disconnected/reconnecting and periodically retries. Home Assistant
  trusts the last valid sample until the MQTT measurement's configured
  `expire_after` elapses, so a brief reconnect does not immediately notify.
- Individual DHT11 timing failures are tolerated. Sustained missing samples
  change service health to `error` at the configured maximum age while MQTT
  expiry makes measurements unavailable; valid samples restore `online`.
- Unexpected DHT11 GPIO/library failures release the device and retry setup at
  the configured reconnect interval without requiring a container restart.
- Parser output not declared in config is ignored instead of creating surprise
  MQTT entities.
- A missing/invalid SMS field is rejected before it reaches the delivery queue.
- Duplicate SMS request IDs and rapid repeated events are suppressed.
- Normal Home Assistant generation replaces only generated LabPulse files.

## Where changes belong

| Change | Owning source |
| --- | --- |
| Enable hardware or change a live USB path | `~/labpulse-ha/config.yaml` |
| Add/validate a config field | `labpulse_common/config.py` |
| Change stable IDs | `labpulse_common/identity.py` |
| Change topics or SMS request fields | `labpulse_common/mqtt_contracts.py` |
| Change any user-facing SMS wording | `labpulse_common/sms_templates.yaml` |
| Change acquisition or reconnect behavior | `labpulse_hardware/drivers/` |
| Change the standard serial contract | `labpulse_hardware/serial_parser.py` and Arduino firmware |
| Change discovery/state publishing | `labpulse_hardware/homeassistant_publisher.py` |
| Change measurement render types/IDs | `labpulse_homeassistant/measurement_model.py` |
| Change aggregate Home Assistant models/construction | `labpulse_homeassistant/render_model.py` |
| Change generated alarm behavior | `templates/alarm/alarm_logic.yaml` |
| Change generated dashboard layout | `labpulse_homeassistant/dashboard/` and `templates/dashboard/` |
| Change alert transport/delivery | `labpulse_sms/` |
| Change containers or mounts | `generate_compose.sh` |
