# LabPulse Open Source Roadmap

## Purpose

LabPulse should become a versioned application platform with a small,
deliberately supported driver SDK.

It should not remain a collection of Python directories copied into a Docker
build context. It also does not need an elaborate plugin ecosystem immediately.
The recommended progression is:

1. Make the current application installable, testable, versioned, and
   releasable.
2. Establish one clean in-repository driver extension contract.
3. Prove that contract with an independent contributor.
4. Then permit separately distributed driver packages through standard Python
   entry points.

The goal is that another developer can add a sensor without first understanding
LabPulse configuration internals, Compose generation, MQTT discovery, Home
Assistant generation, and every supported hardware library.

## Foundations to preserve

The current architecture already has several good boundaries:

- one process and container per sensor service;
- a normalized `dict[str, float]` measurement boundary;
- typed central configuration;
- hardware-independent tests and fake serial devices;
- lazy hardware imports so unrelated services do not load Pi-specific
  libraries;
- a central hardware runner owning retry, freshness, status transitions, and
  cleanup;
- MQTT as the boundary between acquisition and Home Assistant;
- Home Assistant owning alarm decisions, thresholds, timing, and presentation;
- stable service and measurement identities shared across generated components.

These should be retained while improving the contributor and installation
experience. A grouped deployment mode, asynchronous runtime, or new alerting
architecture is not required for this work.

## Current extension friction

The lifecycle and configuration seams are now centralized. Drivers implement
`connect/read/close`, return `ReadingBatch`, classify expected failures for
`HardwareRunner`, and register a typed `DriverSpec`. Driver-specific options and
Compose resource requirements no longer expand the shared `ServiceConfig` or
the driver factory.

The remaining extension friction is packaging optional hardware dependencies,
declaring fixed output metadata, first-class simulation hooks, contributor
scaffolding, and eventually loading separately distributed registrations.

Distribution presents a separate problem. The setup script currently generates
a Dockerfile and unversioned requirements before copying source packages into
`~/labpulse-ha`. This is useful during prototyping, but it does not provide a
clear installed version, dependency lock, upgrade boundary, or reliable
rollback.

## Target driver architecture

### Use one driver identity

**Status: implemented for the built-in serial-pipe, DHT11, and X1200 drivers.**

Configuration should use one flat driver identifier rather than mixing a
transport with device subtype fields:

```yaml
services:
  room_environment:
    driver:
      type: labpulse.dht11
      options:
        pin: D4
    device_name: "Room Environment"
    measurements:
      - name: temperature
        setups: [cryogenics_room]
      - name: humidity
        setups: [cryogenics_room]
```

Built-in identifiers could include:

- `labpulse.serial_pipe`
- `labpulse.dht11`
- `labpulse.x1200`

This avoids an expanding combination of `driver`, `gpio_sensor`, `i2c_sensor`,
and device-specific fields in the shared configuration model.

The common configuration reader validates the service envelope, finds the
selected driver specification, and then allows that specification to validate
its own `options`. Unknown driver IDs, conflicting registrations, and invalid
options must fail during configuration validation before Compose or Home
Assistant files are generated.

### Introduce a driver specification

**Status: the dependency-light deployment definitions, internal runtime registry,
typed option models, lazy builders, default poll intervals, and declarative
device/mount/privilege requirements are implemented. Host-side Compose
generation does not import Pydantic or hardware libraries. API versioning,
fixed output metadata, and public plugin discovery remain future work.**

Each registered driver should provide a `DriverSpec` containing:

- a stable driver ID;
- a driver API compatibility version;
- its Pydantic options model;
- a factory that constructs the driver;
- the measurements it normally produces, including default units and Home
  Assistant metadata where those outputs are fixed;
- declarative container requirements such as devices, groups, capabilities,
  and mounts;
- optional simulation support.

The deployment generator should consume these structured resource requirements.
A driver should not emit arbitrary Compose YAML.

Built-in drivers should initially use an explicit internal registry. This makes
the extension seam testable without committing to a public third-party plugin
API too early.

### Centralize lifecycle behaviour

Before declaring the driver API stable, the core hardware runner should own:

- retry and backoff;
- the core `online`, `reconnecting`, `disconnected`, and `error` states;
- poll scheduling where appropriate;
- last-success and measurement-freshness tracking;
- consistent exception handling and logging;
- idempotent cleanup.

Drivers should own:

- hardware or library initialization;
- device protocol and value conversion;
- classification of temporary versus connection-losing failures;
- optional component degradation such as the X1200 GPIO fault.

A small synchronous public contract is sufficient:

```text
connect
read -> ReadingBatch | None
close
```

`ReadingBatch` can retain the existing normalized numeric readings while also
providing a future home for component-health information. There is no need to
introduce an asynchronous framework while each service runs independently.

### Preserve the zero-code serial path

The easiest extension path should remain an Arduino or other serial device that
emits the standard unit-free pipe-delimited protocol.

Adding one of these sensor hubs should require:

- firmware;
- a service and measurement declaration;
- a simulator fixture;
- no new Python driver.

The contributor guide should start by asking whether the device can emit the
standard serial contract. Only direct GPIO, I2C, SPI, network APIs, or unusual
protocols should require a new Python driver.

## Python package direction

LabPulse should become one Python distribution with one import namespace and
clear internal subpackages:

```text
pyproject.toml
src/
  labpulse/
    api/
    config/
    drivers/
    runtime/
    homeassistant/
    sms/
    deploy/
tests/
docs/
firmware/
```

This is one distribution, not one monolithic module. The existing responsibility
boundaries should remain intact inside the `labpulse` namespace.

Because the current Docker refactor is not yet in live use, the namespace and
configuration changes should be made cleanly before the first stable release.
Legacy import paths and configuration compatibility layers should not be added.

The package should install a single `labpulse` command with subcommands such as:

```text
labpulse init
labpulse validate
labpulse generate
labpulse doctor
labpulse drivers list
labpulse run --service NAME
labpulse simulate
```

Starter configuration, Home Assistant fragments, SMS templates, and other
runtime templates should be installed as package data and loaded through
`importlib.resources`.

Runtime configuration should be located through an explicit `--config` option,
an environment variable, or the documented live default
`~/labpulse-ha/config.yaml`. It should not be found relative to an unpacked
source directory.

### Dependencies

Dependencies should be divided into deliberate optional groups:

```text
labpulse
labpulse[serial]
labpulse[dht11]
labpulse[x1200]
labpulse[sms]
labpulse[all]
labpulse[dev]
```

Release dependency versions should be constrained and tested. Development
dependencies should include pytest, linting, formatting, type checking, build
validation, and documentation checks.

The release process should build and test both a wheel and source distribution.
Python package metadata should define the CLI and, later, the third-party driver
entry-point group.

## Installation and deployment

The Python package and the Pi installer are related but distinct artifacts:

1. The Python distribution provides code, metadata, CLI commands, and the
   driver API.
2. A versioned multi-architecture container image is the primary Raspberry Pi
   runtime.
3. A conservative bootstrap/update tool manages the live Compose project.

### Use the released image as the setup tool

The preferred installation flow is:

1. A small bootstrap script pulls a pinned LabPulse image.
2. It runs `labpulse init` from that image against `~/labpulse-ha`.
3. The same image validates config and generates Compose and Home Assistant
   files.
4. Generated Compose runs that exact image version.

This gives configuration validation, generation, hardware runtime, and SMS
runtime one coherent LabPulse version. A fresh Pi then needs Docker and the
Compose plugin, but not host PyYAML, copied source trees, or a separately
synchronized Python environment.

The bootstrap/update workflow must:

- preserve `~/labpulse-ha/config.yaml`;
- preserve Home Assistant-owned configuration and state;
- show the intended changes;
- validate before replacing generated files;
- retain a tested rollback path to the previous image and generated
  configuration;
- offer `labpulse doctor` before services are started;
- avoid floating `latest` tags in released deployments.

### Third-party driver images

Third-party packages should not be downloaded dynamically from names in
`config.yaml`, and containers should not install plugins on every startup.

Once external plugins are supported, the reproducible approach is a derived
image containing pinned driver wheels:

```dockerfile
FROM ghcr.io/example/labpulse:0.x.y
RUN pip install labpulse-driver-bme280==1.2.3
```

The same derived image can then run validation, generation, diagnostics, and the
sensor service, so the driver registry is consistent in every phase.

## Contributor experience

Add a root `CONTRIBUTING.md` and a focused driver-authoring guide. They should
provide two complete walkthroughs:

1. A configuration-only serial sensor.
2. A small fakeable direct-hardware driver, such as a BME280 example.

The documentation should explain:

- which interfaces are public and which are internal;
- the standard serial contract;
- driver configuration and measurement metadata;
- stable service and measurement identity rules;
- container resource declarations;
- fake-device and real-device test expectations;
- the review and release process.

A driver contribution should be complete only when it includes:

- typed driver options;
- the driver implementation;
- declared outputs and container resources;
- hardware-free unit tests;
- disconnect and recovery tests;
- a simulator or fake bus/device;
- example configuration;
- user documentation;
- relevant real-Pi smoke-test evidence.

A small scaffold command may eventually create these files, but it should follow
a proven manual workflow rather than define an untested architecture.

## Testing and continuous integration

The current script-driven tests should move to normal pytest discovery and
shared fixtures. Tests must remain runnable without Raspberry Pi hardware.

CI should check:

- wheel and source-distribution builds;
- installation into a clean environment;
- unit and integration tests that do not require hardware;
- linting and formatting;
- static typing;
- maintained Markdown links and fences;
- configuration schema validation;
- generated Compose and Home Assistant output;
- package-data inclusion;
- release image construction.

Real hardware tests should be explicitly marked and documented. They should
produce a retained smoke-test report rather than being required in ordinary
pull-request CI.

The driver layer should have reusable contract tests covering:

- loading without unrelated optional hardware dependencies;
- valid and invalid driver options;
- declared measurement names and numeric output;
- temporary read failures;
- connection loss and recovery;
- idempotent cleanup;
- minimal container-resource declarations;
- fake-hardware operation.

After the external plugin interface is stabilized, these contract tests should
be made available to separately distributed driver packages.

## Open-source project requirements

Before actively soliciting external contributions, the repository needs an
explicit open-source license. The copyright ownership of work produced at
Lancaster University and by previous contributors should be confirmed before a
license is selected.

Software, firmware, documentation, images, PCB files, and 3D models may require
separate licensing decisions. Use established licenses rather than a custom
license.

The repository should also add:

- `CONTRIBUTING.md`;
- `CODE_OF_CONDUCT.md`;
- `SECURITY.md`;
- `CHANGELOG.md`;
- `CITATION.cff`;
- issue and pull-request templates;
- a short maintainer and governance statement;
- contributor attribution.

The first published versions should be pre-1.0 releases. The application
version, configuration `schema_version`, and driver API version should be
separate concepts. A compatibility and migration policy should be defined near
the first stable release, but migration code should not be written until a real
schema change requires it.

## Development phases

### Phase 1: Open-source and test baseline

- Confirm ownership and add the licensing structure.
- Add contribution, governance, security, citation, and release files.
- Convert tests to pytest without changing runtime behaviour.
- Add CI for tests and generated-output validation.
- Establish a clean developer installation.

Acceptance: a new developer can clone the repository, install development
dependencies, and run the complete hardware-free test suite from one documented
command.

### Phase 2: Installable application

- Add `pyproject.toml`.
- Move active Python code under the `labpulse` namespace.
- Package all required YAML and template resources.
- Add the `labpulse` CLI and explicit configuration lookup.
- Build and test wheel and source distributions.

Acceptance: LabPulse installs into a clean environment with no `sys.path`
manipulation or dependency on the repository layout.

### Phase 3: Unified generation and diagnostics

- Move Compose and Home Assistant generation behind `labpulse generate`.
- Add `labpulse validate`, `labpulse doctor`, and `labpulse drivers list`.
- Remove duplicated raw YAML parsing from shell-embedded Python.
- Ensure generators and runtimes use the same typed configuration.

Acceptance: one installed LabPulse version can initialize, validate, diagnose,
generate, and run the complete application.

### Phase 4: Driver extension seam

- Add the internal driver registry and `DriverSpec`.
- Split common service configuration from driver-owned options.
- Introduce declarative container requirements.
- Centralize common lifecycle and retry behaviour. Completed as the
  `HardwareRunner` foundation.
- Adapt serial, DHT11, and X1200 as the first built-in specifications.
- Add reusable driver contract tests.

Acceptance: adding an in-tree hardware driver does not require editing the
central configuration model, central factory branches, or Compose generator
branches.

### Phase 5: Prove contributor usability

- Publish the serial and direct-driver walkthroughs.
- Add a minimal lab-independent example sensor.
- Ask a developer unfamiliar with the internals to add a test sensor using only
  the public documentation.
- Record and fix every undocumented assumption.
- Perform a second clean installation outside the original development
  environment.

Acceptance: an external developer completes the sensor workflow without
maintainer-only instructions or direct edits to internal registries.

### Phase 6: Versioned Pi releases

- Publish a pinned multi-architecture image.
- Use the released image for initialization and generation.
- Add conservative install, update, rollback, and diagnostics workflows.
- Test upgrade and rollback on a Raspberry Pi.
- Publish tagged pre-1.0 releases and release notes.

Acceptance: an operator can install or update LabPulse without copying source
directories and can restore the previous working release without losing live
configuration or Home Assistant state.

### Phase 7: External driver packages

- Declare the public driver API and its compatibility policy.
- Discover external drivers through a `labpulse.drivers` Python entry-point
  group.
- Detect duplicate IDs and incompatible API versions clearly.
- Document reproducible derived images with pinned plugin wheels.
- Publish the driver contract-test kit.

Acceptance: a separately distributed driver package can be installed into a
derived LabPulse image and used for validation, generation, diagnostics, fake
tests, and runtime acquisition without modifying the main repository.

## Explicit non-goals

This roadmap should not introduce:

- runtime installation of arbitrary plugins from configuration;
- arbitrary Python module paths in user configuration;
- driver-generated raw Compose fragments;
- one separately published distribution for every current internal package;
- a new asynchronous or grouped runtime solely for extensibility;
- compatibility layers for prototype paths or configuration forms;
- floating container tags in released deployments;
- hardware-required tests in the normal contributor test suite.

## Definition of success

The open-source extension work is successful when:

- the repository grants clear permission to use, modify, and redistribute its
  components;
- a clean checkout installs and tests with standard Python tooling;
- the running Pi uses a known, reportable LabPulse version;
- ordinary serial sensors remain configuration-only additions;
- a direct hardware driver is isolated to its implementation, options,
  metadata, resources, tests, and documentation;
- a contributor can follow the public guide without learning internal
  generation code;
- installation, upgrade, and rollback preserve live user state;
- the public plugin boundary is introduced only after the simpler in-tree
  extension path has been proven.
