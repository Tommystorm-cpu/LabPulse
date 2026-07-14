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

### Runtime readings and alerts

```text
sensor
  -> driver
  -> normalized dict[str, float]
  -> configured-reading filter
  -> MQTT discovery and state topics
  -> Home Assistant sensor entities
  -> zone sensors and history statistics
  -> alarm-state automations
  -> persistent notification and MQTT SMS request
  -> validated SMS queue
  -> dry-run log or ModemManager
```

UPS power is the deliberate exception to the generic zone/history path. Its
MAX17043 or simulated telemetry still follows the same driver/MQTT boundary,
but Home Assistant uses a dedicated `Normal` / `Possible On Battery` /
`Sensor Fault` lifecycle with persistent candidate deadlines. Possible battery
operation is inferred from sustained low UPS voltage; mains is not measured.

The key boundary is between facts and decisions:

- Python hardware services publish values and connection health.
- Home Assistant owns thresholds, timing, mute controls, alarm state, and
  operator-facing notifications.
- The SMS worker validates and delivers an already-decided alert. It does not
  decide whether a reading is dangerous.

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

The service key selects configuration and therefore its driver, parser,
readings, labels, and hardware path. One container per service isolates device
disconnects and restarts.

### `labpulse-sms`

The SMS worker has a persistent MQTT session and a bounded background delivery
queue. In safe `dry_run` mode it only logs masked recipients. In real mode it
uses `mmcli`, so Compose additionally exposes D-Bus and devices to this one
container.

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
- serial, DHT11, and read-only MAX17043 UPS drivers
- compatibility parsing of current Arduino text
- MQTT discovery, state, and service-health publishing

Its output boundary is a normalized `dict[str, float]` plus a health string.

### `labpulse_homeassistant`

Runs as an offline generator on the Pi host, not as a long-running sensor
container. It turns typed config into:

- Home Assistant core configuration
- the generated alarm package
- a diagnostic entity map
- an optional/reset starter dashboard

It may optionally query the live Home Assistant entity registry to discover
renamed MQTT entity IDs.

### `labpulse_sms`

Owns alert-request validation, duplicate/flood protection, recipient fan-out,
the bounded delivery queue, dry-run logging, `mmcli` retries, and result/status
publishing.

## Configuration and state ownership

The live config describes deployment facts:

```text
~/labpulse-ha/config.yaml
```

It owns enabled services, hardware access, parser choice, readings, display
metadata, MQTT connection settings, SMS mode, and recipients.

A MAX17043 service receives only its configured `/dev/i2c-N` device mapping.
It does not require privileged mode or a broad `/dev` mount.

Home Assistant owns operator state after generation:

- minimum/maximum thresholds
- alarm mode and mute state
- observation, recovery, and stale-data timing
- live dashboard layout
- accounts and integrations

This distinction prevents a normal regeneration from destroying tuned values
or dashboard edits.

## Generated versus user-owned files

| File | Owner | Normal regeneration |
| --- | --- | --- |
| `compose.yaml` | Compose generator | replaced |
| `configuration.yaml` | Home Assistant generator | replaced |
| `packages/labpulse_generated.yaml` | alarm generator | replaced |
| `labpulse_entity_map.yaml` | core generator | replaced |
| `automations.yaml`, `scripts.yaml`, `scenes.yaml` | Home Assistant UI | created only if missing |
| active Overview store (`.storage/lovelace.<id>` or legacy `.storage/lovelace`) | Home Assistant UI/user | resolved through `lovelace_dashboards`; preserved unless reset or synchronized explicitly |

The dashboard seed is intentionally different from live dashboard state. It is
used only when `--reset-dashboard` is requested.

## Identity contract

Machine identifiers are derived from the service key and reading name. For:

```yaml
services:
  pressure_monitor:
    readings:
      - name: pressure
```

the shared identity functions produce:

```text
stable unique ID: labpulse_pressure_monitor_pressure
default entity:  sensor.labpulse_pressure_monitor_pressure
state topic:     home/sensor/pressure_monitor/pressure/state
```

Labels such as `Pressure` are presentation and can change safely. Renaming the
service key or reading name changes MQTT topics, unique IDs, generated helper
IDs, and history continuity.

Home Assistant is allowed to rename an entity ID while retaining its unique
ID. The optional registry resolver therefore reconciles by
`(platform, unique_id)`, not by display name.

## Home Assistant alarm ownership

Each reading has a persistent state:

```text
Normal
Danger
Sensor Fault
```

Instantaneous binary sensors describe whether the reading is in the danger,
recovery, or fault zone. A `history_stats` sensor measures the percentage of
the observation window spent in danger. Automations write the persistent state
only when the timing and zone conditions are met.

Muting suppresses persistent notifications and SMS requests; it does not stop
zone calculation or state transitions. This keeps the dashboard truthful while
silencing delivery.

## Failure behavior

- A missing serial device does not terminate the service loop. The driver
  reports disconnected/reconnecting and periodically retries. Home Assistant
  trusts the last valid sample until Maximum Reading Age expires, so a brief
  reconnect does not immediately notify.
- Individual DHT11 timing failures are ignored; sustained missing updates are
  caught by Home Assistant stale detection.
- Parser output not declared in config is ignored instead of creating surprise
  MQTT entities.
- A missing/invalid SMS field is rejected before it reaches the delivery queue.
- Duplicate SMS request IDs and rapid repeated events are suppressed.
- Normal Home Assistant generation preserves the live dashboard.
- Strict entity-registry resolution fails before writing if an expected entity
  is missing, disabled, or ambiguous.

## Where changes belong

| Change | Owning source |
| --- | --- |
| Enable hardware or change a live USB path | `~/labpulse-ha/config.yaml` |
| Add/validate a config field | `labpulse_common/config.py` |
| Change stable IDs | `labpulse_common/identity.py` |
| Change topics or SMS request fields | `labpulse_common/mqtt_contracts.py` |
| Change acquisition or reconnect behavior | `labpulse_hardware/drivers/` |
| Adapt current Arduino text | `labpulse_hardware/legacy_parsing/serial_parser.py` |
| Change discovery/state publishing | `labpulse_hardware/homeassistant_publisher.py` |
| Change Home Assistant model/IDs | `labpulse_homeassistant/data_models.py` |
| Change generated alarm behavior | `templates/alarm/alarm_logic.yaml` |
| Change reset-dashboard layout | `templates/dashboard/dashboard_seed.yaml` |
| Change alert transport/delivery | `labpulse_sms/` |
| Change containers or mounts | `generate_compose.sh` |
