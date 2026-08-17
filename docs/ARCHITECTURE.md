# Architecture

LabPulse separates hardware acquisition, transport, alarm decisions,
presentation, and notification delivery so each can fail and be tested
independently.

## Product boundary

LabPulse monitors infrastructure and produces best-effort alerts. It does not
command equipment and must not be used as a safety-rated controller, emergency
shutdown system, certified alarm, or protective interlock. Independent
protective systems remain necessary wherever a missed or delayed measurement
or notification could cause harm or loss.

The authoritative boundary, terminology, and requirements for any future
control work are in [Product scope and safety boundary](PRODUCT_SCOPE.md).

## System overview

```text
physical or simulated sensors
            │
            ▼
labpulse-<service> containers
  driver → runner → MQTT publisher
            │
            ▼
        Mosquitto
         │      │
         ▼      ▼
Home Assistant  labpulse-sms
  dashboard       │
  alarm logic     ▼
  MQTT requests  modem or dry-run log
```

The generated Compose project contains:

- `homeassistant`;
- `mosquitto`;
- `labpulse-sms`;
- one `labpulse-<service-slug>` container per enabled hardware service.

One-service-per-container isolates device failures and makes Docker restart
behavior simple.

## Installation and live state

The pipx environment provides the operator CLI and packaged deployment assets.
`labpulse setup` generates:

```text
~/labpulse-live/
  config.yaml
  compose.yaml
  .venv/
  generate_compose.sh
  generate_homeassistant_config.sh
  edit_config.sh
  simulate_serial.py
  setup_usb_devices.py
  homeassistant/config/
  mosquitto/
  logs/
```

The host `.venv` contains generation/configuration dependencies plus a `.pth`
link to the pipx-installed LabPulse package. Operators do not activate it;
live wrappers select it automatically. The link lets generators use the exact
installed driver manifests without copying application source.

Sensor and SMS services use
`ghcr.io/tommystorm-cpu/labpulse:<package-version>`. The package version,
generated Compose image tag, wheel, and image label are released together.

## Sources of truth and generated output

User-owned state:

- `~/labpulse-live/config.yaml`;
- Home Assistant accounts, integrations, recorder, and private state;
- persisted SMS subscription choices;
- local secrets and modem provisioning.

Generated or package-managed state:

- `compose.yaml`;
- the managed Python-environment link to the installed package;
- Mosquitto's generated config;
- `configuration.yaml`;
- `packages/labpulse_generated.yaml`;
- `labpulse-dashboard.yaml`;
- copied live helper scripts.

Generators must preserve user-owned state and deterministically replace only
their outputs.

## Configuration flow

```text
config.yaml → common.config.load_config()
  │              │
  │              ├── source-aware ConfigDocument
  │              ├── common schema validation
  │              └── typed selected-driver options
  │
  ├── deployment generation
  │     └── driver container requirements
  │
  ├── Home Assistant generation
  │     └── canonical measurement/render model
  │
  ├── hardware services
  │     └── driver selection and measurement allow-list
  │
  └── SMS service
        └── recipients and delivery mode
```

`src/labpulse/common/config.py` is the only production reader for LabPulse
configuration. It returns a `ConfigDocument` containing the resolved source
path and fully validated model. Drivers own the schema beneath
`driver.options`; the loader selects and applies that schema once, so consumers
receive typed options and do not reinterpret raw dictionaries.

Every independent process still loads and validates once at startup. Within a
process, the same document is passed to Compose, Home Assistant, hardware, SMS,
or diagnostic consumers. File, YAML, schema, driver, and option failures use
the same structured configuration error model.

`src/labpulse/deployment/compose.py` is the importable Compose renderer.
`generate_compose.sh` is only a launcher. Setup and guarded editing use the
unified deployment entry point, which loads once, builds Compose and Home
Assistant outputs in staging, and only then replaces managed live files.

Fake setup derives `config.fake.yaml` from the live source config and mounts it
as `/app/config.yaml`. The real source remains unchanged.

## Hardware service flow

```text
python -m labpulse.hardware --service NAME
  → load and validate config
  → select service
  → discover DriverDefinition
  → construct driver from already-typed options and MQTT publisher
  → HardwareRunner.connect/read/retry
  → publish discovery, readings, and service status
```

Ownership:

| Concern | Owner |
|---|---|
| Open hardware and convert raw values | Driver |
| Classify expected hardware failures | Driver |
| Retry, reconnect, polling, and freshness | Hardware runner |
| Service status transitions | Hardware runner |
| MQTT discovery and state | Publisher |
| Driver devices, mounts, and privilege | Driver definition |
| Thresholds and alarm decisions | Home Assistant |

Drivers never publish MQTT or implement retry sleeps. The runner never imports
vendor hardware libraries or understands device protocols.

## Driver contract

Every driver implements:

```text
connect() -> None
read() -> ReadingBatch | None
close() -> None
```

`ReadingBatch.measurements` maps stable configured names to numeric values.
`None` means no complete sample is currently ready.

Expected failure classes are:

- `DriverUnavailable`: connection or initialization failed;
- `ConnectionLost`: an established handle must be recreated;
- `TransientReadError`: one sample failed but the connection remains usable.

`ComponentIssue` accompanies valid readings when only one part of a device is
degraded, such as an X1200 GPIO fault while battery telemetry remains readable.

The runner owns states:

```text
disconnected
reconnecting
online
error
```

If valid readings remain absent beyond
`maximum_measurement_age_seconds`, the runner publishes `error`, closes the
driver, and reinitializes it through the bounded reconnect path. Opening a
hardware handle reports `reconnecting`; only a valid batch restores `online`.
The batch is published before the healthy status transition so Home Assistant
cannot classify a cached pre-restart value as recovered data.

Home Assistant also classifies total expiry of every measurement belonging to
one service as a whole-service fault. This is the liveness fallback for a
hardware call that blocks the runner before it can publish `error`. Partial
telemetry loss remains an individual sensor fault.

The MQTT publisher remembers the runner's current service status. Every broker
connection or reconnection republishes retained discovery and that status. This
prevents a broker restart from leaving a retained Last Will state of `offline`
while the same worker has already resumed measurement publication.

## Driver discovery and deployment

Each public module under `src/labpulse/hardware/drivers/` exports one:

```python
DRIVER = DriverDefinition(...)
```

The registry imports and validates modules automatically. `driver_template.py`
is deliberately excluded. Helper modules inside that directory must begin with
an underscore or they will be treated as drivers.

A definition contains:

- stable driver ID;
- Pydantic options model;
- driver builder;
- declarative resource resolver;
- default read interval.

Compose generation asks the selected definition for `ContainerRequirements`
containing devices, mounts, and privileged status. Drivers cannot emit arbitrary
Compose YAML.

## MQTT boundary

Measurement state:

```text
home/sensor/<service>/<measurement>/state
```

Service status:

```text
home/sensor/<service>/status
```

Home Assistant discovery uses:

```text
homeassistant/sensor/<service>_<measurement>/config
homeassistant/sensor/<service>_status/config
```

Discovery and service status are retained. Numeric measurement state is not
retained. Measurements expire when valid publication stops, not when their
numeric value remains unchanged.

Hardware publishers ignore reading names not declared in the service config.

## Stable identity

Service keys and measurement names form the cross-component identity used by:

- MQTT topics;
- Home Assistant unique IDs and entity IDs;
- alarm helpers and automations;
- dashboard references;
- notification identities.

Labels, setup projection, and subcategories are presentation metadata. Renaming
them does not create new sensor identities.

Logical setups are separate from physical services. A measurement can appear
in several setup views while retaining one MQTT entity and alarm state.

## Home Assistant ownership

The Home Assistant generator receives the already-validated `ConfigDocument`,
builds one small context of enabled services, setup membership and bulk-alarm
groups, then renders final-shaped Jinja YAML. There is no separate Home
Assistant model or card-builder hierarchy. The generator writes:

- core configuration and dashboard registration;
- alarm helpers and transition automations;
- native YAML dashboard views.

Home Assistant owns:

- threshold modes and values;
- observation percentage and duration;
- recovery duration and deadband;
- Normal, Danger, and Sensor Fault state;
- global, setup, measurement, and power delivery mutes;
- Test mode;
- confirmed service fault/recovery;
- confirmed power outage/recovery;
- notification and SMS request creation.

Python publishes facts and health. It does not decide whether a measurement is
dangerous.

## SMS boundary

Home Assistant publishes strict JSON requests to:

```text
labpulse/sms/send
```

The independent SMS worker validates, deduplicates, rate-limits, routes,
queues, retries, sends or logs, and publishes delivery results. This keeps
modem access outside Home Assistant and hardware services.

## Package boundaries

```text
src/labpulse/
  common/          config, identity, MQTT contracts, shared logging
  deployment/      Compose rendering and atomic deployment generation
  hardware/        driver API, registry, runner, parsing, MQTT publishing
  homeassistant/   one generator, derived alarm context, final YAML templates
  sms/             request subscription, routing, modem delivery
  control.py       operator CLI
  doctor.py        read-only deployment diagnostics
  installer.py     packaged setup launcher
```

Cross-component identity, topics, and raw configuration must not be redefined
inside service packages.

## Security boundary

The current deployment assumes a trusted lab network. Mosquitto allows
anonymous access inside the deployment and binds its host port only to
`127.0.0.1`. Home Assistant is the user-facing network service.

Some drivers require privileged or device access. Driver code and container
images must therefore be trusted. Do not expose Mosquitto outside the host
without first adding authentication, authorization, and transport security.
