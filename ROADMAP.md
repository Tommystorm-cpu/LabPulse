# LabPulse roadmap

## Goal

LabPulse should become a reliable, easily installed, maintainable platform for
laboratory infrastructure monitoring. A lab should be able to install it,
describe local hardware in one configuration file, operate it without
maintainer-only knowledge, and add standard or custom sensors through stable,
documented interfaces.

The immediate priority is proving and polishing the monitoring system used in
the current laboratory. Release engineering, security, and extensibility should
build on that foundation rather than outrun it. Equipment control is a later,
explicitly opt-in capability and must not turn LabPulse into a safety interlock.

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
- initial packaging, contributor, architecture, and operator documentation.

These foundations exist in code, but not all have completed long-duration,
real-hardware, clean-install, or release-artifact acceptance testing.

## Stage 0: product boundaries and immediate containment

- Define the initial product as monitoring and alerting, not safety-critical
  equipment control.
- Define the initially supported Raspberry Pi, operating-system, Python,
  Docker Compose, and Home Assistant environments.
- Document what is and is not supported during pre-1.0 development.
- Treat the network containing the current Pi as untrusted until confirmed
  otherwise. Place it behind an appropriate firewall, private network, or VPN
  before exposing Home Assistant or adding external integrations.

Network containment is an operational prerequisite. It does not require the
full LabPulse security feature set to be implemented first.

## Stage 1: reliable and polished monitoring

Target: `0.1.0-alpha`

### Real-hardware reliability

- Complete repeated real-device unplug, reconnect, and recovery tests.
- Verify DHT11 and X1200 startup, sustained failure, and recovery on the Pi.
- Establish alarm behavior across container, Home Assistant, and whole-Pi
  restarts.
- Verify longer UPS outages, restoration, flapping, and GPIO failure.
- Run sustained soak tests with real and simulated sensors.
- Exercise real SMS delivery, inbound subscription commands, retries, and
  recovery after modem or service interruption.
- Test power loss and recovery without corrupting user-owned state.
- Decide how an external system will detect failure of the Pi, broker, Home
  Assistant, or SMS path itself.

### Operator polish

- Make first installation, configuration, generation, startup, and diagnosis
  one coherent documented workflow.
- Make `labpulse config` preserve and regenerate the active fake-USB mode.
- Improve health reporting where container-running and sensor-connected states
  differ.
- Make logs consistently identify the service, driver, device path, connection
  state, and last successful reading.
- Ensure common errors explain the corrective action.
- Expand `labpulse doctor` coverage for installation, configuration, Docker,
  MQTT, devices, generated files, and runtime health.
- Decide whether notification mutes need expiry or remain manual toggles.
- Decide whether short power outage and restoration events should be combined
  into one message.
- Define and test complete backup and reconstruction on a blank Pi.

Acceptance: the current installation survives ordinary hardware and service
failures and can be operated and rebuilt without undocumented maintainer
knowledge.

## Stage 2: packaging, continuous integration, and releases

Target: `0.2.0-alpha`

LabPulse already has a `pyproject.toml`, bounded core dependencies, package-data
declarations, and pipx commands. This stage turns those foundations into a
reproducible release process rather than redesigning the package.

### Automated quality gates

- Run the complete hardware-free suite in continuous integration.
- Convert or wrap the standalone test scripts in a conventional test runner so
  selection, failure reporting, and coverage are easier to manage.
- Test every supported Python version.
- Build wheel and source distributions for every proposed release.
- Install both artifacts into clean environments and exercise all console
  entry points and packaged deployment assets.
- Check formatting, typing, shell syntax, documentation links, and
  deterministic generated Compose and Home Assistant output.
- Publish reusable driver contract tests.

### Release model

- Use Semantic Versioning for the product, with compatibility still allowed to
  evolve during `0.x`.
- Use release candidates before deploying a final version to the real Pi.
- Require a changelog, release checklist, migration notes, and recorded
  real-Pi acceptance for each release.
- Add `labpulse version` and include the version in diagnostic output.
- Version the configuration schema independently from the package version.
- Automate package publication from a tagged release.
- Publish LabPulse to PyPI so normal installation becomes:

  ```text
  pipx install labpulse
  labpulse setup
  ```

Acceptance: the wheel and source distribution both produce a functioning CLI
and deployment from clean environments, and releases do not depend on a
maintainer's local checkout.

## Stage 3: reproducible deployment, updates, and rollback

Target: `0.3.0-alpha`

- Publish versioned multi-architecture container images.
- Ensure the CLI, deployment assets, Python runtime, and containers report the
  same LabPulse release version.
- Pin image versions rather than following mutable `latest` tags.
- Constrain and review Python, system-package, and base-image dependencies.
- Produce a release manifest identifying all package and image versions.
- Add an update preflight check and explicit operator confirmation.
- Back up user-owned state before applying migrations.
- Add versioned configuration migrations only after a released schema requires
  them; do not add compatibility layers for unreleased prototype layouts.
- Provide and test rollback to the previous working release.
- Preserve live configuration, Home Assistant state, MQTT data, SMS
  subscription state, and local secrets across updates.
- Publish checksums and software bills of materials for release artifacts.

Acceptance: a Pi can install, update, and restore a known LabPulse version
without losing user-owned state.

## Stage 4: supported security baseline

Target: `0.4.0-beta`

- Replace anonymous MQTT access with generated or operator-supplied
  credentials.
- Give hardware publishers, Home Assistant, SMS, and integrations separate
  identities.
- Add MQTT access-control rules so each component can use only the topics it
  requires.
- Keep unencrypted MQTT internal to the host or private deployment network;
  require a VPN or TLS for remote clients.
- Establish a secrets-file or secrets-directory model with restrictive
  permissions.
- Document supported firewall, private-network, VPN, SSH, and HTTPS deployment
  patterns.
- Extend `labpulse doctor` with read-only security checks for network-facing
  services, anonymous MQTT, unsafe permissions, and unnecessary container
  privilege.
- Reduce container privileges, mounts, and device access where practical.
- Add dependency and vulnerability-update policies.
- Add a `SECURITY.md` with a private vulnerability-reporting route.
- Check backups, logs, and diagnostic output for accidental disclosure of
  credentials or private network information.

LabPulse setup should not silently alter host firewall or SSH rules. It should
inspect, warn, and provide documented guidance because the correct rules depend
on the laboratory network and incorrect automation could lock out the
operator.

Acceptance: the supported network model is explicit, normal deployment does
not rely on anonymous trust, and external access has a documented secure path.

## Stage 5: contributor and adoption readiness

Target: `0.5.0-beta`

- Prove the standard serial-device workflow with someone unfamiliar with the
  internals.
- Prove the direct-driver workflow using only public documentation, the driver
  template, and the contract-test kit.
- Add fixed-output metadata and first-class simulation hooks to driver
  definitions where contributor experience shows they are useful.
- Record real-Pi smoke-test evidence in a consistent form.
- Keep ordinary serial sensor additions configuration-only.
- Add issue and pull-request templates and a concise contribution checklist.
- Remove assumptions tied specifically to the original laboratory where they
  are discovered.
- Establish a realistic long-term maintenance model.

A clean installation outside the primary development setup is valuable late
acceptance evidence, but deployment in another laboratory is not a prerequisite
for developing the release or extension architecture. Broader multi-lab
validation belongs near 1.0 or after the project is otherwise ready for
adoption.

Acceptance: another contributor can add and test a sensor without editing
central configuration, registry, runner, Compose, MQTT, or Home Assistant
branches.

## Stage 6: protocol-level external integrations

Target: `0.6.0-beta`

The first external integration mechanism should be a versioned protocol that
external software can use without installing Python code inside LabPulse.

- Define a stable MQTT contract for measurement publication.
- Include stable source and measurement identity, numeric values, units or
  metadata, availability, freshness, component faults, acknowledgements,
  errors, protocol version, and advertised capabilities.
- Define generic outbound events or output destinations independently from
  vendor-specific integrations.
- Publish schemas, examples, conformance tests, and a small simulator.
- Allow external software to supply measurements through configuration and the
  protocol without modifying LabPulse core code.
- Keep these concepts distinct in configuration:

  ```yaml
  services:       # sources producing measurements
  integrations:   # external systems exchanging data or events
  outputs:        # destinations such as MQTT, webhooks, or files
  ```

- Do not require an external process to run inside a LabPulse container when a
  network contract is sufficient.
- Keep read-only measurement exchange separate from equipment-control
  commands.

Acceptance: an independently deployed program can publish valid measurements
and health to LabPulse using only the documented contract.

## Stage 7: external Python extension packages

Target: `0.7.0-beta`

Only add external packages after the in-tree driver API and contributor
workflow have been proven.

- Declare and version a public driver and extension API.
- Discover installed extensions through a Python entry-point group.
- Require extension metadata containing its ID, API version, dependencies, and
  capabilities.
- Reject duplicate IDs and incompatible API versions clearly.
- Publish a small extension SDK and contract-test package.
- Pin exact extension package versions in an installation lock file.
- Build or select a derived runtime image containing the pinned extension
  wheels.
- Record extension provenance and versions in `labpulse doctor`.
- Do not install arbitrary packages merely because they appear in
  `config.yaml`.
- Do not download packages on every container start.

A future command such as:

```text
labpulse extension install labpulse-triton
```

should resolve an approved package, validate compatibility, pin it, prepare the
appropriate runtime image, regenerate deployment, and report what changed. It
should not be a thin wrapper around an uncontrolled `pip install`.

Third-party extensions should normally live in separate repositories and be
released independently. A small set of reference drivers may remain in the
main LabPulse repository.

## Stage 8: specific integrations and controlled outputs

Target: experimental pre-1.0 releases

Qubex and Triton should validate the general contracts rather than define
them.

- Prefer a configuration-only or protocol-only Qubex integration if it can
  publish or consume the standard MQTT contract.
- Use the same contract for Triton measurements when its available interface
  permits it.
- If Triton requires a proprietary protocol, vendor library, or network API,
  implement it in a separately released `labpulse-triton` package.
- Keep vendor-specific options and dependencies outside the LabPulse core
  configuration model.
- Promote generally useful capabilities into the contract only after they have
  at least one concrete implementation.

Equipment control requires a separate, explicitly enabled contract with:

- per-device opt-in and constrained allowed operations;
- separate control credentials and MQTT permissions;
- command IDs, acknowledgements, timeouts, and expiry;
- replay protection and audit logs;
- safe behavior after communication loss;
- manual override and local interlocks;
- a clear statement that LabPulse is not a safety interlock.

Read-only measurements and events must be proven before LabPulse is permitted
to command equipment.

## Stage 9: 1.0 readiness

Target: `1.0.0`

- Installation, operation, backup, upgrade, rollback, and reconstruction are
  proven on supported hardware.
- Core configuration and extension compatibility policies are published.
- Releases are reproducible and their provenance is recorded.
- The security defaults match the documented deployment model.
- Hardware-free continuous integration and real-Pi acceptance both pass.
- Operator and contributor documentation have been exercised by people other
  than their authors.
- At least one clean installation independent of the primary development
  setup has been completed.
- The project has a credible maintenance and vulnerability-response model.
- Stable releases can be archived in an appropriate long-term repository.

Use in multiple laboratories is desirable evidence after the product is ready
for adoption, not a condition that should block reaching a mature release.

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

The intended order is:

```text
reliability and operator polish
  → CI and package releases
  → reproducible updates and rollback
  → supported security baseline
  → contributor readiness
  → protocol-level integrations
  → external packages
  → controlled outputs
```
