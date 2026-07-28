# LabPulse roadmap

## Goal

LabPulse should become a reliable, easily installed, maintainable platform for
laboratory infrastructure monitoring. A lab should be able to install it,
describe local hardware in one configuration file, operate it without
maintainer-only knowledge, and add standard or custom sensors through stable,
documented interfaces.

The immediate priority is delivering useful monitoring in the current
laboratory. Stage 1 established a reliable base; the next priority is a
read-only Triton integration. Release engineering, generic extension systems,
and wider-adoption work should be pulled forward only when a concrete need
justifies them. Equipment control remains a separate, explicitly opt-in
capability and must not turn LabPulse into a safety interlock.

## Current foundation

Implemented foundations include:

- a `src/`-layout Python package with pipx-visible commands;
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
- read-only `labpulse doctor` diagnostics;
- repository-wide MIT licensing;
- a documented monitoring, alerting, and safety boundary;
- a documented reference deployment and pre-1.0 support policy;
- initial packaging, contributor, architecture, and operator documentation.

These foundations exist in code, but not all have completed long-duration,
real-hardware, clean-install, or release-artifact acceptance testing.

## Stage 1: reliable and polished monitoring

Target: `0.1.0-alpha`

Status: complete on 27 July 2026. Stage 2 is now the active roadmap phase.

### Real-hardware reliability

- [x] Complete repeated real-device unplug, reconnect, and recovery tests.
- [x] Verify DHT11 and X1200 startup, sustained failure, and recovery on the Pi.
- [x] Establish alarm behavior across container, Home Assistant, and whole-Pi
  restarts.
- [x] Verify longer UPS outages, restoration, flapping, and GPIO failure.
- [x] Run sustained soak tests with real and simulated sensors.
- [x] Exercise real SMS delivery, inbound subscription commands, retries, and
  recovery after modem or service interruption.
- [x] Test power loss and recovery without corrupting user-owned state.
- [x] Decide how an external system will detect failure of the Pi, broker, Home
  Assistant, or SMS path itself.

Completed 27 July 2026 on the Raspberry Pi 5 Model B Rev 1.1 deployment at
revision `dc6c29f`. Acceptance evidence included repeated container and
whole-Pi restarts, injected DHT11 and X1200 interface failures, real UPS
outages and restoration, an abrupt total power removal, real SMS delivery and
recovery, and two weeks of continuous operation. Measurements, retained
service state, Home Assistant alarms, and SMS notifications recovered without
loss of user-owned state.

Two hardware defects were separated from the software result:

- recurring USB disconnects were isolated to a faulty external USB hub, which
  should be replaced;
- the installed DHT11 can remain unresponsive after a short power interruption
  and recover only after an extended unpowered period, even though its VCC rail
  falls to approximately `0.014 V`. It should be replaced and is not treated as
  reliability-qualified.

The low-effort watchdog decision is to use the Raspberry Pi hardware watchdog
through systemd with a 30-second runtime timeout. A separate external watchdog
is deferred unless unattended operation reveals a failure that the internal
watchdog cannot recover. An external device would need to control the X1200
power path rather than merely interrupt mains input, because the UPS battery
can continue powering the Pi.

### Operator polish

- [x] Make first installation, configuration, generation, startup, and diagnosis
  one coherent documented workflow.
- [x] Make `labpulse config` preserve and regenerate the active fake-USB mode.
- [x] Improve health reporting where container-running and sensor-connected states
  differ.
- [x] Make logs consistently identify the service, driver, device path, connection
  state, and last successful reading.
- [x] Ensure common errors explain the corrective action.
- [x] Expand `labpulse doctor` coverage for installation, configuration, Docker,
  MQTT, devices, generated files, and runtime health.
- [x] Decide whether notification mutes need expiry or remain manual toggles.
- [x] Decide whether short power outage and restoration events should be
  combined into one message.
- [x] Define and test complete backup and reconstruction on a blank Pi.

The completed health-reporting work separates process availability, physical
service state, component faults, and individual measurement validity. Recovery
requires a valid new reading rather than container startup alone.

Notification mutes remain explicit manual toggles. They survive ordinary Home
Assistant restarts and do not expire silently; the dashboard continues to show
the active mute state so an operator must deliberately restore delivery.

Power loss and restoration remain separate notifications. Loss must be
reported as soon as it is confirmed; waiting to combine it with restoration
would delay the actionable warning. The confirmed restoration closes the event
with its duration, while the existing confirmation periods filter brief
transitions.

`labpulse backup` now quiesces running services and creates a private,
checksummed archive of source configuration, complete Home Assistant state,
Mosquitto retained data, and SMS subscription/request state. `labpulse restore`
validates the archive, scaffolds a blank installation in its recorded runtime
mode, creates a rollback archive where applicable, restores and regenerates
the deployment, rebuilds and starts it, waits for Home Assistant, and runs
diagnostics. Hardware-free acceptance covers exact round-trip reconstruction,
tamper and path-traversal rejection, overwrite safeguards, operator
confirmation, automatic rollback creation, and blank-installation routing.
Host and physical settings remain an explicit post-restore checklist.

Acceptance met: the current installation survives ordinary hardware and
service failures and can be operated, backed up, and reconstructed without
undocumented maintainer knowledge.

## Roadmap policy after Stage 1

Future work is ordered by value to the current laboratory, not by an assumed
path to becoming a general software product. A concrete integration should
teach LabPulse what abstractions it needs; speculative protocol, packaging, and
extension systems must not block useful monitoring.

Only the following are hard prerequisites for a read-only integration:

- credentials and secrets are not committed or exposed in logs;
- the integration cannot issue equipment commands;
- connection loss, stale data, invalid data, and recovery are represented
  honestly;
- a hardware-free simulator or recorded fixture covers normal and failure
  paths;
- the existing installation remains recoverable through backup and restore.

The productisation tracks later in this document are selected when their
trigger occurs. They are not mandatory sequential stages.

## Stage 2: Triton read-only vertical slice

Status: active.

### Interface discovery

- Identify the deployed Triton product, software or firmware version, network
  location, and supported interfaces.
- Establish whether data is available through MQTT, HTTP, another network
  protocol, a vendor library, files, or an existing database.
- Obtain a least-privilege read-only account where the interface supports one.
- Record authentication, polling or subscription limits, timestamps, units,
  identifier stability, and expected disconnection behavior.
- Capture sanitized example responses or traffic for hardware-free tests
  without committing credentials or sensitive laboratory data.
- Select the smallest implementation after inspecting the real interface:
  prefer configuration and existing protocols; otherwise add a focused
  in-tree adapter or isolate a necessary vendor dependency in its own
  container. Do not build a public extension framework merely to host one
  integration.

### End-to-end slice

- Read one useful Triton measurement from the real system.
- Give the source and measurement stable LabPulse identities.
- Publish its value, availability, freshness, and connection status through
  the existing MQTT and Home Assistant path.
- Display the measurement and integration health in the generated dashboard.
- Represent authentication failure, timeout, invalid response, stale data,
  disconnect, and recovery without manufacturing a healthy reading.
- Add fixture-backed or simulated adapter, generation, and health tests.
- Document configuration, secret placement, diagnosis, and safe removal.

Acceptance: one real Triton measurement travels from Triton to the LabPulse
dashboard with the correct value, unit, timestamp, freshness, and health;
simulated failure and recovery work without physical Triton access; and the
integration has no command capability.

## Stage 3: complete Triton monitoring

Stage 3 expands only after the vertical slice proves the interface and
implementation shape.

- Inventory the measurements and events that are operationally useful; do not
  mirror every vendor field by default.
- Define labels, units, update intervals, freshness limits, and stable
  identities for the selected data.
- Add those measurements to configuration, MQTT discovery, dashboards,
  diagnostics, and alarm rules.
- Reuse existing service and measurement fault semantics rather than creating
  a parallel Triton health model.
- Add thresholds, mutes, notifications, and SMS only where the required
  operator response is known.
- Rate-limit retries and logs so a Triton or network outage cannot create a
  local resource problem or notification storm.
- Exercise service, Pi and Triton restarts; network interruption; credential
  failure; stale telemetry; invalid payloads; and recovery.
- Complete a real-system soak test and record the evidence.
- Include Triton configuration in backup and reconstruction documentation
  while keeping secrets out of publishable configuration and diagnostics.

Acceptance: required Triton monitoring survives ordinary restarts and
realistic communication failures, recovers only after valid new telemetry, and
behaves consistently with existing LabPulse alarms and diagnostics.

## Later work selected by need

The following tracks retain important work from the earlier roadmap, but none
blocks Stages 2 or 3 unless its trigger is met.

### Track A: release safety baseline

Trigger: updates become frequent, another developer contributes regularly, or
LabPulse is installed from anything other than the maintained checkout.

- Run the existing hardware-free suite in continuous integration.
- Build wheel and source distributions and install both in clean environments.
- Exercise all console commands and packaged deployment assets.
- Add `labpulse version` and include it in diagnostic output.
- Use a short release checklist with changelog, migration notes, backup, and
  recorded real-Pi acceptance.
- Publish to PyPI only when external installation is genuinely useful.
- Convert tests to a conventional runner, add broad formatting and type gates,
  and test multiple Python versions when that improves maintenance rather than
  merely changing tooling.

Acceptance when activated: a release artifact constructs a functioning
deployment without depending on a maintainer's checkout.

### Track B: reproducible updates and rollback

Trigger: LabPulse has published versions or an update introduces the first
real configuration migration.

- Pin release and container versions rather than following mutable tags.
- Report matching versions across the CLI, assets, runtime, and containers.
- Add update preflight, confirmation, automatic state backup, and tested
  rollback to the previous working release.
- Introduce a configuration-schema version only when a released schema needs
  migration.
- Preserve live configuration, Home Assistant state, MQTT data, SMS state,
  secrets, and integration state across updates.
- Publish checksums and a release manifest; add software bills of materials
  when artifacts are distributed.

Acceptance when activated: a Pi can install, update, and roll back a known
release without losing user-owned state.

### Track C: security for the deployed boundary

Trigger: Triton requires network credentials, MQTT leaves the host, remote
access is added, the network is not fully trusted, or LabPulse is offered to
other installations.

The minimum Triton credential and log protections required by Stage 2 happen
immediately. Broader hardening is pulled from this track as the boundary grows.

- Establish a restrictive secrets-file or secrets-directory model.
- Replace anonymous MQTT with separate identities and least-privilege topic
  access where the deployment boundary requires it.
- Keep unencrypted MQTT internal to the trusted host or network and use a VPN
  or TLS for remote clients.
- Document firewall, VPN, SSH, and HTTPS patterns without silently changing
  host firewall or SSH rules.
- Extend Doctor with read-only checks for exposed services, unsafe
  permissions, anonymous access, and unnecessary container privilege.
- Add dependency and vulnerability policy and a private reporting route before
  supporting external users.

Acceptance when activated: credentials are protected, each exposed component
has only the access it needs, and the supported network path is explicit.

### Track D: general external-integration contract

Trigger: Triton proves a reusable boundary, or a second integration such as
Qubex needs the same exchange model.

- Extract the smallest generic measurement and health contract already proven
  by a working integration.
- Include only identities, values, metadata, timestamps, availability,
  freshness, faults, errors, versions, and capabilities that real
  implementations need.
- Keep services producing measurements, integrations exchanging data, and
  outputs delivering events conceptually distinct.
- Publish schemas, examples, conformance tests, and a simulator when an
  independently deployed program needs the contract.
- Prefer a configuration-only or protocol-only Qubex integration when its
  interface permits it.
- Generalize vendor behavior only after a second implementation demonstrates
  that it is genuinely reusable.

Acceptance when activated: Triton and at least one independent implementation
use the same documented boundary without vendor-specific branches in the
contract.

### Track E: external packages and contributor adoption

Trigger: an integration must be released independently, third parties need to
add code without changing LabPulse, or multiple deployments need a stable
extension API.

- Prove the in-tree workflow before declaring an API public.
- Add entry-point discovery, API-version checks, duplicate-ID rejection,
  dependency and capability metadata, and reusable contract tests.
- Pin extension versions and prepare a deterministic runtime image; never
  download arbitrary packages from `config.yaml` or on every container start.
- Record extension provenance in Doctor.
- Keep ordinary serial sensors configuration-only.
- Exercise contributor documentation with someone unfamiliar with the
  internals and remove original-laboratory assumptions as adoption begins.

A future `labpulse extension install labpulse-triton` command is justified only
if Triton genuinely needs independent packaging. It must be controlled and
versioned rather than an unrestricted `pip install`.

Acceptance when activated: an external integration can be installed and
tested without editing LabPulse core or weakening reproducibility.

## Separately gated future work: equipment control

Read-only Triton monitoring does not authorize equipment control. Commands are
a separate project phase requiring an explicit operator decision after
read-only monitoring has been proven.

Before any Triton, Qubex, or other equipment command is enabled, the design
must include:

- per-device opt-in and a constrained allow-list of operations;
- separate control credentials and network permissions;
- command IDs, acknowledgements, timeouts, expiry, and replay protection;
- an append-only audit trail;
- safe behavior after LabPulse, network, or equipment communication loss;
- manual override and independent local interlocks;
- real-system failure testing in a controlled maintenance window;
- a clear statement that LabPulse is not a safety interlock.

Acceptance: read-only monitoring remains independently usable, every command
has an attributable result or explicit timeout, stale commands cannot execute,
and loss of LabPulse cannot defeat the equipment's local protections.

## Long-term 1.0 readiness

Target: `1.0.0` only if LabPulse is being maintained as a reusable product.

- Installation, operation, backup, necessary upgrades, rollback, and
  reconstruction are proven on the supported deployment.
- Compatibility promises cover only interfaces that real integrations use.
- Releases are reproducible if releases are being distributed.
- Security defaults match the actual supported network boundary.
- Hardware-free regression tests and relevant real-Pi acceptance both pass.
- Operator documentation has been exercised outside its authoring context.
- The project has a credible maintenance and vulnerability-response model if
  it has external users.

Use in multiple laboratories, PyPI publication, a public extension ecosystem,
and a broad compatibility matrix are desirable only when LabPulse is actually
being adopted beyond the current laboratory.

## Explicit non-goals

The roadmap does not currently call for:

- an asynchronous runtime solely for extensibility;
- grouping all sensors into one process as the only deployment mode;
- arbitrary Python module paths in configuration;
- driver-generated raw Compose fragments;
- dynamic package installation from `config.yaml`;
- packages downloaded afresh on every container start;
- required custom Home Assistant cards, themes, or HACS dependencies;
- hardware-required tests in the ordinary pull-request suite;
- compatibility layers for unreleased prototype layouts;
- using LabPulse as a safety-rated control system or interlock.

## Definition of done

A roadmap item is complete only when:

- behavior is implemented in the owning component;
- important normal and failure paths have automated coverage;
- relevant real-Pi behavior has been checked;
- maintained documentation is updated;
- generated outputs and packaged artifacts have been verified where
  applicable;
- operational and security risks are recorded;
- upgrade or compatibility effects are documented;
- remaining follow-up work is explicit.

The active delivery order is:

```text
reliability and operator polish
  -> Triton read-only vertical slice
  -> complete Triton monitoring
  -> select later tracks only when their trigger occurs
```

Equipment control is never implied by progress through the monitoring roadmap.
