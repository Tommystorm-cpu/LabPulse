# Architecture

This document describes the current LabPulse implementation. It is organized
around ownership boundaries: which process owns each decision, which module is
the source of truth, and which files are user-owned or generated.

## Product boundary

LabPulse monitors laboratory infrastructure and produces best-effort alerts.
It does not control equipment and is not a safety-rated alarm, emergency
shutdown system, or protective interlock. Independent protection remains
necessary wherever delayed, missing, or incorrect telemetry could cause harm
or loss. See [Product scope and safety boundary](PRODUCT_SCOPE.md).

## Runtime topology

```text
physical or simulated sensors
            │
            ▼
one labpulse-<service> container per enabled service
  hardware CLI → driver → runner → MQTT publisher
            │
            ▼
        Mosquitto
         │      │
         ▼      ▼
Home Assistant  labpulse-sms
  discovery       request validation
  dashboard       routing and deduplication
  alarm state     modem delivery or dry-run logging
  MQTT requests
```

Generated Compose always contains:

- `homeassistant`;
- `mosquitto`;
- `labpulse-sms`;
- one `labpulse-<service-slug>` container for every enabled service.

Hardware services do not share a Python process. A blocked or failed device
therefore does not stop another sensor service, and Docker can restart workers
independently.

## Installed host layout

The pipx-installed package provides the operator command and packaged setup
assets. `labpulse setup` creates or refreshes:

```text
~/labpulse-live/
  config.yaml                         user-owned source configuration
  config.fake.yaml                    derived only in fake-USB mode
  compose.yaml                        generated
  .venv/                              managed host generation environment
  edit_config.sh                      package-managed workflow helper
  generate_compose.sh                 package-managed low-level wrapper
  generate_homeassistant_config.sh    package-managed low-level wrapper
  setup_usb_devices.py                package-managed USB mapper
  simulate_serial.py                  package-managed simulator
  test_dht11_fault.sh                 package-managed acceptance helper
  test_x1200_faults.sh                package-managed acceptance helper
  homeassistant/config/               Home Assistant live state and generated YAML
  mosquitto/                           broker configuration and retained data
  logs/                                Python logs and SMS worker state
```

The managed `.venv` contains host-only generation dependencies and a `.pth`
link to the exact pipx-installed `labpulse` package. Operators do not activate
it. The live wrappers select it automatically.

Runtime Python services use the image selected during generation. A released
installation defaults to:

```text
ghcr.io/tommystorm-cpu/labpulse:<installed-package-version>
```

## User-owned and generated state

User-owned state includes:

- `~/labpulse-live/config.yaml`;
- Home Assistant accounts, integrations, recorder data, and private storage;
- Mosquitto retained data;
- SMS subscription and processed-request state;
- local modem, operating-system, timezone, watchdog, and hardware setup.

Generated or package-managed state includes:

- `compose.yaml`;
- `config.fake.yaml`;
- `homeassistant/config/configuration.yaml`;
- `homeassistant/config/packages/labpulse_generated.yaml`;
- `homeassistant/config/labpulse-dashboard.yaml`;
- copied deployment and test helpers;
- local Mosquitto configuration;
- the managed host `.venv` and its package link.

Generated files are replaceable projections of the live configuration and
package code. They are not independent configuration sources.

## Command surfaces

LabPulse has one public operator CLI and four package-level process entry
points.

### Operator CLI

`src/labpulse/control.py` owns the `labpulse` command:

```text
labpulse setup
labpulse config
labpulse up | down | restart
labpulse ps | logs
labpulse backup | restore
labpulse doctor
labpulse open | firmware | version | help
```

It resolves the live directory, selects the Docker command, delegates setup,
controls Compose, coordinates backup and restore, and exposes diagnostics.
Operator documentation should use this interface.

`src/labpulse/installer.py` locates package data and launches
`deployment/setup_container_fs.sh`. The shell script owns Linux filesystem
scaffolding; it does not own configuration schema or generated Compose logic.

### Package process entry points

Each package with a standalone process follows the same boundary:

```text
package/__main__.py → package/cli.py → domain modules
```

| Command | CLI responsibility | Domain owner |
|---|---|---|
| `python -m labpulse.hardware` | Compose one hardware worker | `src/labpulse/hardware/` |
| `python -m labpulse.sms` | Load config and compose the SMS worker | subscriber, sender, subscriptions |
| `python -m labpulse.homeassistant` | Generate Home Assistant files | `src/labpulse/homeassistant/` |
| `python -m labpulse.deployment` | Generate deployment files | `src/labpulse/deployment/` |

`cli.py` modules own argument parsing and process composition. Importable
domain modules do not inspect `sys.argv` or exit the interpreter.

## Configuration model and flow

`src/labpulse/common/config.py` is the only production LabPulse YAML loader and
owns the final cross-section validation. Physical and calculated measurement
models live in `common/measurement_config.py`; driver, service, and power models
live in `common/service_config.py`.

The loader returns a `ConfigDocument` containing:

- the resolved source path;
- a fully validated `LabPulseConfig`;
- driver options already converted to the selected driver's Pydantic model.

```text
config.yaml
  │
  ▼
common.config.load_config()
  │
  ├── deployment generation
  ├── Home Assistant generation
  ├── one hardware process per service
  ├── SMS worker
  └── diagnostics
```

Each independent process loads once at startup. Consumers receive typed data
and do not parse YAML or revalidate driver dictionaries. File, YAML, schema,
driver, option, and service-selection failures use the shared `ConfigError`
model with source and field locations.

Cross-component values are centralized:

- stable IDs: `common/identity.py`;
- MQTT topics and SMS request schema: `common/mqtt_contracts.py`;
- message copy: `common/sms_templates.yaml` through `sms_templates.py`;
- fake-runtime derivation: `common/fake_config.py`.

## Deployment generation

`src/labpulse/deployment/compose.py` renders deterministic Compose text from a
validated document and driver resource declarations.

`src/labpulse/deployment/generate.py` owns installation of generated output:

```text
load one ConfigDocument
  ├── render Compose in memory
  └── render Home Assistant into a staging directory
          │
          ▼
replace managed live files only after every render succeeds
```

This prevents a valid Compose file from being installed alongside invalid or
partially rendered Home Assistant files. Setup and `labpulse config` use the
unified path with `--ha-config-dir`.

The shell files `generate_compose.sh` and
`generate_homeassistant_config.sh` are live-directory wrappers around Python
entry points. They are operational conveniences, not generation logic.

### Fake-USB mode

The source of truth remains `config.yaml`. Fake mode derives
`config.fake.yaml` by replacing real transports with supported pseudo-serial
drivers while preserving service names, measurement names, and Home Assistant
identity.

Compose mounts the derived file as `/app/config.yaml`. `labpulse config`
detects that runtime mode, regenerates the derived file, validates it, and
keeps the deployment simulated.

## Hardware process

The container command is equivalent to:

```text
python -m labpulse.hardware --config /app/config.yaml --service NAME
```

The flow is:

```text
hardware/__main__.py
  → load ConfigDocument
  → select ServiceConfig
  → registry.get_driver_definition(driver.type)
  → construct driver from typed configuration
  → construct HomeAssistantMqttPublisher
  → HardwareServiceRunner.run_forever()
```

Ownership is strict:

| Concern | Owner |
|---|---|
| Open hardware and normalize raw values | Driver |
| Classify expected hardware failures | Driver |
| Connect, retry, poll, freshness, and cleanup | Runner |
| Service-health transitions | Runner |
| MQTT discovery, state, availability, and status | Publisher |
| Devices, mounts, and privileged requirements | Driver definition |
| Thresholds, alarm transitions, and notifications | Home Assistant |

Drivers do not publish MQTT or manage retry sleeps. The runner does not import
vendor hardware libraries or understand device protocols.

## Driver contract

Every driver extends `HardwareDriver` and implements:

```text
connect() -> None
read() -> HardwareReadings | None
close() -> None
```

`HardwareReadings.values` maps configured measurement names to finite numeric
values. `None` means no complete sample is ready. `HardwareIssue` can accompany
valid measurements when one part of a multi-function device is degraded.

Expected failure classes are:

- `DriverUnavailable`: connection or initialization failed;
- `ConnectionLost`: an established handle must be recreated;
- `TransientReadError`: one read failed but the connection remains usable.

The runner publishes these service states:

```text
disconnected
reconnecting
online
error
```

The MQTT Last Will publishes `offline` if the process loses its broker
connection unexpectedly.

When no valid batch arrives before `maximum_measurement_age_seconds`, the
runner publishes `error`, closes the driver, and returns to bounded reconnect.
A valid batch is published before the service transitions to `online`, so
Home Assistant cannot interpret cached data as a recovery.

## Driver discovery and container resources

Each public module under `src/labpulse/hardware/drivers/` exports exactly one:

```python
DRIVER_DEFINITION = DriverDefinition(...)
```

The registry imports public modules automatically. The contributor template
lives in `docs/examples`; supporting modules in the production driver package
must begin with `_`.

A `DriverDefinition` contains:

- stable driver ID;
- strict configuration model;
- clearly named driver class;
- container-requirements function;
- default read interval.

The definition validates configuration once and constructs the driver with the
standard `(service_name, config)` constructor. This makes the driver itself
the hardware-to-runner translation layer; there is no separate adapter type.

Every driver supplies a function returning `ContainerRequirements`, containing
devices, mounts, and a privileged flag. Drivers cannot return arbitrary Compose
YAML.

## MQTT boundary

Hardware publication uses:

```text
Measurement state:  home/sensor/<service>/<measurement>/state
Service status:     home/sensor/<service>/status
Sensor discovery:   homeassistant/sensor/<service>_<measurement>/config
Status discovery:   homeassistant/sensor/<service>_status/config
```

Discovery and service status are retained. Numeric measurement state is not.
Home Assistant discovery contains `expire_after`, so freshness depends on
continued valid publication rather than whether a numeric value changes.

The publisher accepts only names declared in the selected service's
`measurements` list. Unexpected driver keys are ignored.

## Stable identity

Service keys and measurement names define identity across:

- MQTT topics;
- Home Assistant unique IDs and entity IDs;
- alarm helpers and automations;
- dashboard references;
- notification request IDs.

Labels, subcategories, icons, units, and setup projection are presentation
metadata. A measurement may appear in several setup views while remaining one
MQTT entity and one alarm state.

## Home Assistant generation and ownership

The standalone entry point is:

```text
python -m labpulse.homeassistant CONFIG_PATH HA_CONFIG_DIR
```

Its modules have separate roles:

| Module | Responsibility |
|---|---|
| `homeassistant/generator.py` | Arguments, config load, rendering, validation, and atomic file replacement |
| `homeassistant/alarm.py` | Typed render model, threshold metadata, alarm package rendering |
| `homeassistant/templates/` | Final-shaped YAML behavior and layout |

LabPulse Jinja uses `[% ... %]` and `[[ ... ]]`, leaving Home Assistant's
`{% ... %}` and `{{ ... }}` expressions intact in generated YAML.

Home Assistant owns:

- threshold mode and values;
- danger observation percentage and window;
- recovery duration and deadband;
- `Normal`, `Danger`, and `Sensor Fault` states;
- whole-service fault and recovery confirmation;
- direct power loss, restoration, and power-sensor faults;
- global, setup, measurement, and power mutes;
- Test mode;
- persistent notification and SMS request creation.

Python publishes measurements and health facts. It does not decide whether a
measurement is dangerous.

## SMS process

The SMS container command is equivalent to:

```text
python -m labpulse.sms --config /app/config.yaml
```

Home Assistant publishes strict JSON requests to:

```text
labpulse/sms/send
```

The worker then:

```text
subscriber
  → validate SmsRequest
  → reject duplicate/recent requests
  → select test or normal recipients
  → apply subscription choices and cooldown
  → queue sequential delivery
  → send through mmcli or log a dry run
  → publish status and per-request result
```

`subscriber.py` owns MQTT intake and request caching. `sender.py` owns message
formatting, recipient routing, queueing, retries, and ModemManager calls.
`subscriptions.py` owns inbound `SUBSCRIBE` and `UNSUBSCRIBE` processing.

## Backup, restore, and diagnostics

`backup.py` owns the checksummed archive format and safe extraction. Backups
capture user-owned runtime state, not generated files as independent sources.

`control.py` coordinates quiescing services, creating archives, scaffolding a
missing live installation, restoring state, regenerating output, starting the
stack, and attempting rollback if recovery fails.

`doctor.py` is read-only. It checks filesystem state, source/runtime config,
runtime mode, host clock, watchdog, driver resource paths, Docker and Compose,
defined/running services, MQTT, and Home Assistant reachability.

## Source tree ownership

```text
src/labpulse/
  control.py         public operator CLI and workflow orchestration
  installer.py       package-data lookup and setup launcher
  backup.py          archive creation, validation, extraction, restore
  doctor.py          read-only installation/runtime diagnostics
  common/            configuration, IDs, MQTT contracts, shared logging/copy
  deployment/        Compose renderer and atomic unified generation
  hardware/          CLI, driver API/registry, runner, parser, MQTT publisher
  homeassistant/     CLI, render context, generators, final YAML templates
  sms/               CLI, MQTT subscriber, delivery, subscriptions

deployment/          Linux setup and guarded-edit workflow assets
testing/             executable hardware-free contract/integration tests
firmware/            Arduino library and device examples
hardware/            PCB and enclosure assets
docs/                current operator and contributor documentation
```

New behavior belongs in the package that owns the decision. `common` is only
for contracts genuinely shared by multiple packages.

## Security boundary

The generated deployment assumes a trusted local network. Mosquitto allows
anonymous access but binds its host port to `127.0.0.1`. Home Assistant is the
user-facing network service.

Real SMS mode receives `/dev` and D-Bus access. DHT11 currently requires a
privileged hardware container. Other drivers declare narrower device access
where possible. Driver code and runtime images must therefore be trusted.

Do not expose Mosquitto outside the host without authentication,
authorization, and transport security.
