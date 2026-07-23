# LabPulse roadmap

## Goal

LabPulse should become a reliable, easily installed, maintainable platform for
laboratory infrastructure monitoring. A new lab should be able to install it,
describe local hardware in one configuration file, add standard or custom
sensors, and operate it without maintainer-only knowledge.

The immediate priority is proving reliability for the current laboratory. Open
distribution and third-party extensibility should build on that evidence rather
than outrun it.

## Current foundation

Implemented foundations include:

- a `src/`-layout Python package with pipx commands;
- a generated `~/labpulse-live` Docker Compose installation;
- typed configuration shared by deployment and runtime components;
- one isolated container per enabled hardware service;
- a central hardware lifecycle runner;
- self-contained serial, DHT11, and X1200 drivers;
- automatic in-tree driver discovery and declarative container resources;
- a standard unit-free serial protocol;
- fake serial hardware and controllable alarm scenarios;
- MQTT discovery, exact configured units, and stable entity identity;
- generated native Home Assistant dashboards and alarm logic;
- dry-run, test, and real-modem SMS paths;
- read-only `labpulse doctor` diagnostics.

These are implemented in code but not all have completed long-duration or
real-hardware acceptance testing.

## Priority 0: prove reliable operation

- Complete repeated real-device unplug, reconnect, and recovery tests.
- Verify DHT11 and X1200 startup, sustained failure, and recovery on the Pi.
- Establish alarm behavior across Home Assistant and whole-Pi restarts.
- Verify longer UPS outages, restoration, flapping, and GPIO failure.
- Run sustained soak tests with real and simulated sensors.
- Exercise real SMS delivery, inbound subscription commands, retries, and
  recovery after service interruption.
- Define and test complete backup and reconstruction on a blank Pi.
- Decide how an external system will detect failure of the Pi, broker, Home
  Assistant, or SMS path itself.

Acceptance: the installed system survives ordinary failures and can be rebuilt
without undocumented local knowledge.

## Priority 1: complete operator behavior

- Decide whether notification mutes need expiry or remain manual toggles.
- Make `labpulse config` preserve and regenerate the active fake-USB mode.
- Decide whether short power outage and restoration events should be combined
  into one message.
- Specify any required fridge integration before implementation.
- Improve service health visibility where container-running and
  sensor-connected states differ.
- Retain clear, actionable logs for service, path, MQTT state, and last
  successful reading.

## Priority 2: release engineering

- Build and test wheel and source distributions in clean environments.
- Replace copied source/runtime dependency lists with reproducible released
  artifacts.
- Add continuous integration for tests, formatting, typing, documentation, and
  generated output.
- Constrain and review dependency and container-image versions.
- Publish tagged pre-1.0 releases and multi-architecture container images.
- Define conservative install, update, rollback, and configuration migration
  workflows.
- Add a tested changelog and release checklist.

Acceptance: a Pi can install or update a known LabPulse version and restore the
previous working version without losing live state.

## Priority 3: contributor experience

- Prove the serial-device workflow with someone unfamiliar with the internals.
- Prove the direct-driver workflow using only public documentation and the
  driver template.
- Add reusable driver contract tests.
- Add fixed-output metadata and first-class simulation hooks to driver
  definitions where experience shows they are useful.
- Record real-Pi smoke-test evidence in a consistent form.
- Keep ordinary serial sensor additions configuration-only.

Acceptance: another developer can add and test a sensor without editing central
configuration, registry, runner, Compose, MQTT, or Home Assistant branches.

## Priority 4: open-source readiness and adoption

- Confirm ownership and select licences for software, firmware, documentation,
  PCB files, and 3D models.
- Add citation metadata, issue templates, pull-request templates, and release
  automation.
- Complete a fresh installation in a second environment or laboratory.
- Record and remove assumptions tied to the original lab.
- Establish a realistic long-term maintenance model.
- Archive stable releases in an appropriate long-term repository.

## Later: external driver packages

Only after the in-tree driver workflow is proven:

- declare and version the public driver API;
- discover external drivers through a Python entry-point group;
- reject duplicate IDs and incompatible API versions clearly;
- publish the driver contract-test kit;
- document reproducible derived images containing pinned driver wheels.

Third-party packages should not be installed dynamically from `config.yaml` or
downloaded on every container start.

## Explicit non-goals

The roadmap does not currently call for:

- an asynchronous runtime solely for extensibility;
- grouping all sensors into one process;
- arbitrary Python module paths in configuration;
- driver-generated raw Compose fragments;
- required custom Home Assistant cards, themes, or HACS dependencies;
- hardware-required tests in the ordinary pull-request suite;
- compatibility layers for unreleased prototype layouts.

## Definition of done

A roadmap item is complete only when:

- behavior is implemented in the owning component;
- important normal and failure paths have automated coverage;
- relevant real-Pi behavior has been checked;
- maintained documentation is updated;
- generated outputs have been verified where applicable;
- operational risks and follow-up work are recorded.
