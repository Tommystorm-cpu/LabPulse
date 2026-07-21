# LabPulse Software Roadmap

This is the current software to-do list for the active `docker_refactor/`
system. It replaces older lists written before the Home Assistant, MQTT,
container, simulator, and SMS refactors.

Hardware construction, CAD, wiring, purchasing, and assembly instructions are
outside this document.

## Primary target

By the end of September 2026, the installed LabPulse system should operate
reliably for its own lab with nearly no routine intervention.

That means more than having the required features. The complete system must be
shown to recover from ordinary failures, retain correct alarm behavior, and be
reconstructable from the repository and documented live configuration.

## Working principles

1. Prefer standard, maintained tools such as Python, Docker Compose, MQTT, and
   Home Assistant.
2. Keep sensor/deployment facts in `~/labpulse-ha/config.yaml`, and keep
   thresholds, alarm decisions, and operator controls in Home Assistant.
3. Make changes testable without physical hardware wherever possible.
4. Avoid unnecessary compatibility layers before the first stable release.
5. Keep the project readable, copyable, and suitable for public GitHub
   development.
6. Prioritize reliability for the current lab before adding speculative
   integrations.
7. Keep generated dashboards native-only: no HACS cards, custom frontend
   resources, LabPulse JavaScript, card-mod, or required custom themes.

## Security policy

LabPulse is not intended to hold confidential scientific information. The
project should not spend substantial effort trying to make its implementation,
MQTT traffic, or configuration structure secret. It should remain easy to
inspect, reproduce, and modify.

Assume that the LabPulse Pi could be completely compromised. The required
security boundary is containment:

- compromising LabPulse must not provide access to unrelated university or lab
  systems;
- no university passwords or credentials shared with other services may be
  stored on the Pi;
- Home Assistant access tokens and real phone numbers must not be committed to
  the public repository;
- Home Assistant and MQTT should not be exposed directly to the public internet
  by default;
- SMS duplicate, cooldown, queue, and recipient controls must prevent obvious
  cost or harassment failures;
- the system must be recoverable after compromise or accidental damage.

Additional hardening is justified when it protects monitoring integrity,
availability, third parties, or unrelated infrastructure. Confidentiality for
LabPulse's own sensor measurements is not a primary requirement.

## Priority definitions

| Priority | Meaning |
| --- | --- |
| P0 | Required to claim reliable, nearly unattended operation by September 2026 |
| P1 | Original user-facing requirement that remains incomplete |
| P2 | Engineering maturity needed for maintainability and repeatable releases |
| P3 | Open-source adoption and grant readiness |
| Later | Useful only after the deployed system and contribution path are stable |

## P0 — Prove reliable operation

### End-to-end soak test

- [ ] Agree a continuous soak-test duration; at least 14 days is recommended.
- [ ] Run the complete real Pi, real MQTT, Home Assistant, SMS worker, and
  intended sensors for that period without routine manual restarts.
- [ ] Record every intervention, unexplained container restart, missing measurement,
  false alarm, missed alarm, and duplicate notification.
- [ ] Fix or explicitly accept every failure before declaring the target met.

Acceptance: the agreed soak period completes with no unexplained loss of
monitoring and no routine operator action.

### Restart and power-loss behavior

- [ ] Power-cycle the Pi while measurements are Normal and confirm automatic return.
- [ ] Power-cycle while a measurement is Danger and verify the eventual alarm state
  is correct rather than silently remaining Normal.
- [ ] Restart Home Assistant independently and verify helpers, zone sensors,
  history statistics, alarm state, and automations recover correctly.
- [ ] Restart Mosquitto independently and verify every publisher/subscriber
  reconnects without manual action.
- [ ] Restart each sensor container and the SMS container independently.
- [ ] Verify queued or repeated MQTT SMS requests do not create duplicate texts.

Acceptance: ordinary restarts recover automatically and do not leave the
dashboard displaying a plausible but incorrect healthy state.

### Sensor and USB recovery

- [ ] Test repeated unplug/replug with every real serial Arduino using its
  `/dev/serial/by-id/...` path.
- [ ] Confirm status progresses through disconnected/reconnecting/online.
- [ ] Confirm measurements resume without recreating the container.
- [ ] Confirm a prolonged disconnect becomes Sensor Fault in Home Assistant.
- [ ] Test malformed, partial, and silent serial output for each parser format.
- [ ] Test DHT11 startup failure and sustained read failure on the real Pi.

The serial reconnect implementation and automated tests already exist. The
interactive `setup_usb_devices.py` helper can now identify and assign each
stable `/dev/serial/by-id/...` path by guided unplug/replug, and its workflow can
be rehearsed with the fake-USB simulator's per-device `disconnect` and
`connect` commands. This task remains open until the helper and reconnect
behaviour are verified repeatedly with the actual devices.

### Alarm-state restart semantics

- [ ] Establish and document what happens to Normal, Danger, and Sensor Fault
  across Home Assistant restarts.
- [ ] Verify `history_stats` produces safe behavior immediately after startup.
- [ ] Verify a measurement already outside its threshold cannot remain unnoticed
  because no new threshold crossing occurs after restart.
- [ ] Verify Sensor Fault clears only into a justified Normal or Danger state.
- [ ] Add generator or integration tests for every problem found.

Acceptance: alarm behavior is correct from cold start, not only during a
continuous Home Assistant session.

### Monitoring-system watchdog

- [ ] Decide how to detect failure of the whole Pi or Home Assistant itself.
- [ ] Implement an external heartbeat/watchdog if missed LabPulse operation
  would otherwise be invisible.
- [ ] Ensure the watchdog does not depend solely on Home Assistant to report
  that Home Assistant is down.

This can be a simple external mechanism; it does not need to become a second
monitoring platform.

### Backup and reconstruction

- [ ] Define which complete Home Assistant and LabPulse live state must be
  backed up.
- [ ] Document a complete recovery onto a blank replacement Pi.
- [ ] Perform that recovery using only the public repository, retained live
  configuration/state, and documented credentials.
- [ ] Verify dashboard layout, alarm helpers, MQTT integration, SMS operation,
  and real device mappings after restoration.

Acceptance: another project member can reconstruct the installed system without
discovering an undocumented local step.

## P1 — Incomplete user-facing requirements

### Explicit SMS test mode

- [x] Add a deliberate test-delivery mode distinct from `sms.dry_run`.
- [x] Prefix every test SMS title or body with `[TEST]`.
- [x] Preserve test-mode routing through validation and delivery results.
- [x] Test dry-run logging and the real-modem delivery path for marked messages.
- [x] Make it impossible for a test message to look like an unmarked real alarm.

Current state: Home Assistant starts in test mode, test requests route only to
`sms.test_recipients`, and the SMS service has explicit normal/test routing
tests. Per-number `SUBSCRIBE`/`UNSUBSCRIBE` choices apply to both modes.

### Temporary message suppression

- [ ] Decide whether the existing per-measurement mute toggle satisfies the actual
  user requirement.
- [ ] If temporary behavior is required, add a clear duration or expiry time and
  automatic unmute.
- [ ] Decide whether suppression is global per measurement or individual per
  recipient/user.
- [ ] Keep alarm-state calculation visible while delivery is muted.
- [ ] Make muted/expiry state obvious on the dashboard.

Current state: every measurement has a global mute toggle. It suppresses
notifications and SMS but does not expire. SMS recipients can now opt out and
back in individually; temporary alarm mute expiry remains undecided.

### Power outage message consolidation

- [x] Confirm that UPS/power monitoring remains in scope for the active system.
- [x] Define and implement the dedicated Normal/On Battery/Sensor Fault model.
- [ ] Combine a short outage and restoration into one useful event/message when
  appropriate.
- [x] Avoid sending an outage and restoration pair for harmless brief
  interruptions.
- [ ] Test longer outages and repeated flapping separately.

Current state: the X1200 service publishes read-only MAX17043 voltage/SOC
telemetry and direct GPIO6 external-power state. Home Assistant confirms the
GPIO signal, persists one outage lifecycle, reconciles restarts, and emits
test-mode-capable warning/recovery requests. Battery telemetry is contextual
only. Full live-Pi alert acceptance remains outstanding.

### Fridge parameter integration

- [ ] Identify the fridge system, supported interface/API, and ownership of its
  credentials.
- [ ] List the exact parameters required and whether access is read-only.
- [ ] Decide whether values are dashboard-only or participate in alarms.
- [ ] Implement it through a normal LabPulse driver/service and shared MQTT
  publication path rather than a one-off dashboard hack.
- [ ] Provide a hardware-free test double or fixture.

Current state: no fridge integration exists, and the requirement is not yet
specific enough to implement safely.

## P2 — Engineering maturity

### Installable and versioned Python project

- [ ] Add a `pyproject.toml` for the active Python packages.
- [ ] Define a project version and command-line entry points.
- [ ] Build and test an installable wheel or an equally explicit distributable
  artifact.
- [ ] Stop relying solely on copying unversioned source directories into the
  live build context.
- [ ] Define the boundary between host-side generator dependencies and container
  runtime dependencies.

Current state: the code is organized into importable packages with
`__main__.py`, but it is not a versioned installable distribution.

### Dependency and image reproducibility

- [ ] Pin or constrain Python dependencies in a deliberate, reviewable way.
- [ ] Pin release deployments to known container image versions rather than
  floating tags alone.
- [ ] Document how and when dependency/image updates are tested.
- [ ] Keep a rollback path to the previous working release.

### Continuous integration

- [ ] Run every script-based test automatically for pull requests and main.
- [ ] Add formatting/lint checks.
- [ ] Add static type checking or document intentionally unchecked boundaries.
- [ ] Add Markdown link/fence validation for maintained documentation.
- [ ] Add generated-output validation without committing live generated state.
- [ ] Publish a clear pass/fail status for releases.

### Container and service health

- [ ] Add meaningful health checks where they improve automatic diagnosis.
- [ ] Decide whether Compose should distinguish process-running from
  sensor-connected health.
- [ ] Ensure logs clearly identify the service, device path, parser, MQTT state,
  and last successful measurement.
- [ ] Avoid restart loops that hide a persistent configuration fault.

### Release and upgrade workflow

- [ ] Define the first stable release criteria.
- [ ] Document how repository changes are copied/deployed to an existing Pi.
- [ ] Ensure the setup/update path does not unexpectedly overwrite a live
  dashboard.
- [ ] Add a changelog and tested rollback procedure.
- [ ] Define a compatibility/migration policy when the first stable release is
  near; do not build legacy migration layers prematurely.

### Test coverage gaps

- [ ] Add integration tests for Home Assistant restart and alarm restoration.
- [ ] Add broker reconnect tests for hardware publishers and SMS subscriber.
- [ ] Add long-duration simulator tests covering timer boundaries.
- [ ] Add malformed-config and partial-registry fixtures.
- [ ] Add real-Pi smoke-test instructions that produce a retained test report.

## P3 — Open-source adoption and grant readiness

The Sloan Foundation's Open Source in Science programme emphasizes distributed
development, adoption, maintenance, publication, archiving, and institutional
open-source practice. It states that its grants generally focus on tooling,
institutions, economic models, and incentives rather than funding one
individual software project directly:

<https://sloan.org/programs/digital-technology/open-source-in-science>

LabPulse should therefore be presented as a reusable approach to open
laboratory monitoring and maintainable scientific instrumentation—not simply a
request to finish one lab installation.

### Essential repository files

- [ ] Select and add an explicit open-source software licence.
- [ ] Decide and document licensing for firmware and non-software assets
  separately where necessary.
- [ ] Add `CONTRIBUTING.md` with the development, test, review, and sensor-addition
  workflow.
- [ ] Add `CITATION.cff` and identify how releases should be cited.
- [ ] Add a changelog and release notes.
- [ ] Add issue and pull-request templates.
- [ ] Add a short maintainer/governance statement identifying decision and
  review responsibility.
- [ ] Add contributor attribution appropriate for interns and future external
  contributors.

### Reusable extension path

- [ ] Turn “add a new sensor” into a complete documented contribution path:
  config model, driver/parser, fake input, MQTT discovery, Home Assistant
  entities, tests, and documentation.
- [ ] Provide a minimal example sensor/service that is not tied to the original
  lab.
- [ ] Clearly separate stable public contracts from internal implementation.
- [ ] Decide which driver/parser interfaces are supported extension points.
- [ ] Test an external contribution using only the public documentation.

### Adoption evidence

- [ ] Install LabPulse from scratch in a second environment or lab.
- [ ] Record which original-lab assumptions prevented reuse.
- [ ] Resolve or explicitly document those assumptions.
- [ ] Collect evidence of deployment effort, reliability, and maintainability.
- [ ] Identify a realistic maintenance model after the initial funded work.

### Publication and archiving

- [ ] Create tagged, versioned GitHub releases.
- [ ] Archive stable releases in an appropriate long-term repository.
- [ ] Link software releases to associated hardware/docs/publications.
- [ ] Provide machine-readable citation and contributor metadata.
- [ ] Keep example configuration free of real contact details and access tokens.

## Later software work

Do not start these until required by a real deployment or after the P0/P1 work
is under control:

- additional deployment modes such as grouping services into fewer containers;
- additional I2C sensor types beyond the implemented MAX17043 UPS driver;
- per-user notification preferences beyond the agreed mute requirement;
- a plugin system beyond the existing driver/factory boundary;
- advanced dashboard customization that depends on non-standard Home Assistant
  cards;
- broader security hardening unless the network boundary or data sensitivity
  changes.

## Already implemented — retain and verify

These original to-do items have working implementations and should not remain
listed as new feature work:

- [x] User-facing service and measurement labels are configurable separately from
  stable IDs.
- [x] MQTT discovery, generated alarm YAML, and the YAML dashboard use the same
  deterministic entity IDs.
- [x] Alarm numeric helpers use box input rather than sliders.
- [x] Serial drivers contain reconnect logic after USB loss.
- [x] The DHT11 driver reports sustained read failure, rate-limits repeated
  warnings, and reconnects after unexpected GPIO/library errors.
- [x] Alarm timing includes an observation window, required danger percentage,
  required recovery time, and deadband; MQTT expiry detects stopped measurements
  without treating unchanged values as stale.
- [x] SMS requests have duplicate protection, a short event cooldown, a bounded
  queue, retries, status, and delivery results.
- [x] Every measurement has a mute control that suppresses delivery without hiding
  alarm state.
- [x] The generated dashboard puts the Monitor view first, separates Alarm
  Setup, and provides physical-hub Diagnostics.
- [x] Ordinary measurements select one or more explicit setups; dedicated power
  stays independent, and shared cards retain one physical entity and alarm.
- [x] Setup context is included in measurement notifications without multiplying
  events or cooldown identities.
- [x] The supported YAML-mode dashboard is generated deterministically without
  private Home Assistant dashboard mutation or custom frontend cards.
- [x] Safe SMS dry-run logging exists.
- [x] Fake serial devices and controllable alarm scenarios support testing
  without physical hardware.
- [x] The code is separated into `labpulse_common`, `labpulse_hardware`,
  `labpulse_homeassistant`, and `labpulse_sms` packages.

“Implemented” does not automatically mean “proven on the installed Pi.” Items
with corresponding P0 verification tasks remain part of release acceptance.

## Suggested execution order

1. Close the real-device reconnect and restart tests.
2. Establish correct alarm behavior across Home Assistant/Pi restarts.
3. Run the first soak test and fix what it exposes.
4. Agree temporary mute semantics and complete real-Pi subscription-command acceptance.
5. Complete backup/reconstruction and external watchdog decisions.
6. Add CI, dependency/version discipline, and a release workflow.
7. Add the open-source licence, contribution, citation, and governance files.
8. Prove the sensor-extension workflow and a second installation.
9. Implement power or fridge integration only when their requirements and
   interfaces are concrete.

## Task completion rule

A software task is complete only when:

- the behavior is implemented in the owning component;
- automated tests cover the normal and important failure paths;
- relevant real-Pi behavior has been checked when hardware or operating-system
  integration is involved;
- maintained documentation is updated;
- generated outputs have been verified where relevant;
- the completion evidence is recorded in the issue or release notes.
