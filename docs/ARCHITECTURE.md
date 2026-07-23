# Architecture

LabPulse separates hardware acquisition, transport, alarm decisions,
presentation, and notification delivery so each can fail and be tested
independently.

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
  labpulse-python/
  homeassistant/config/
  mosquitto/
  logs/
```

The host `.venv` contains only generation/configuration dependencies. Operators
do not activate it; live wrappers select it automatically.

Current sensor and SMS containers build from Python source copied into
`labpulse-python/`. Released versioned images are future work.

## Sources of truth and generated output

User-owned state:

- `~/labpulse-live/config.yaml`;
- Home Assistant accounts, integrations, recorder, and private state;
- persisted SMS subscription choices;
- local secrets and modem provisioning.

Generated or package-managed state:

- `compose.yaml`;
- the live Python build context;
- Mosquitto's generated config;
- `configuration.yaml`;
- `packages/labpulse_generated.yaml`;
- `labpulse-dashboard.yaml`;
- copied live helper scripts.

Generators must preserve user-owned state and deterministically replace only
their outputs.

## Configuration flow

```text
config.yaml
  │
  ├── Pydantic validation
  │     ├── common service envelope
  │     └── selected driver's options model
  │
  ├── Compose generation
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

`src/labpulse/common/config.py` is the shared typed configuration model.
Drivers own the schema beneath `driver.options`.

Fake setup derives `config.fake.yaml` from the live source config and mounts it
as `/app/config.yaml`. The real source remains unchanged.

## Hardware service flow

```text
python -m labpulse.hardware --service NAME
  → load and validate config
  → select service
  → discover DriverDefinition
  → validate driver options
  → construct driver and MQTT publisher
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
`maximum_measurement_age_seconds`, the runner publishes `error` while continuing
to read. A later valid batch restores `online`.

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

The Home Assistant generator constructs one canonical catalogue and render
model, then writes:

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
  hardware/        driver API, registry, runner, parsing, MQTT publishing
  homeassistant/   render models, alarm package, dashboard generation
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
