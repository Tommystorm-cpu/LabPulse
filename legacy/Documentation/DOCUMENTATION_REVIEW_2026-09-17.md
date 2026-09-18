# LabPulse documentation review

Archived on 18 September 2026. Findings and line references below describe
the original review, not current outstanding work. See the maintained
[documentation checklist](../../DOCUMENTATION_TODO.md) for remaining guide tasks.

Review date: 17 September 2026. Baseline: working tree at `17f2234`, including
the uncommitted changes present when the review began. This is an audit of
current behaviour, not a proposal to preserve old prototype implementations.
The initial review did not change documentation or implementation files.

Follow-up work on 17 September 2026 rewrote Installation as a quick start and
expanded Troubleshooting. It also corrected the User Guide, Configuration
Reference, Architecture, package READMEs, and firmware parser guidance, with
matching corrections in Operations, Development, and the Triton publisher
guide. Optional-reading health and calculated-unit differences are documented
as current limitations; runtime behaviour was not changed by this work. The
findings below preserve the original audit and its original line references,
so they are not an up-to-date list of unresolved work.

The configuration tables are substantially closer to the source than the
operational instructions and package summaries. The main problem is that
accurate new explanations coexist with older, contradictory statements. A
general rewrite is less useful than correcting the behavioural contracts,
consolidating repeated workflows, and checking those workflows in tests.

## Scope and evidence

- Read all 28 tracked current Markdown documents: the five root guides, ten
  guides under `docs/`, and thirteen additional folder READMEs.
- Compared them with configuration models, operator command dispatch, setup and
  guarded editing, backup/restore, deployment generation, hardware drivers and
  runner, Home Assistant templates, SMS/output workers, firmware, and CI.
- Inspected the three complete YAML examples, the driver template, starter
  configuration, firmware headers, overview image, citation/package metadata,
  the three hardware spreadsheets, and the 3D-parts README.
- Reviewed legacy entry points for their separation from current instructions.
  Historical Word/PDF documents were inventoried, not revalidated as current
  installation procedures. Physical builds, calibration, network isolation,
  published artifact availability, and historical acceptance claims were not
  independently certified.
- Reviewed the local `labpulse-project` skill because it supplies instructions
  to future work in this checkout. It is outside the tracked documentation set.

Validation on this Windows host, Python 3.13.14:

```text
test_documentation, test_fake_hardware, test_serial_parser,
test_config_editor_bundle, test_mqtt_json_driver:
    29 passed, 6 skipped

test_homeassistant_generator, test_homeassistant_entities,
test_notification_context, test_backup_restore,
test_hardware_runner, test_deployment_generation:
    45 passed
```

The six skipped tests exercise the Linux guarded editor. Its findings below
come from reading the shell workflow, not running a Pi deployment. Python
3.11/3.12 remain the documented CI matrix; this local run does not extend that
qualification. Documentation links and all three complete YAML examples pass.
Passing those tests does not validate the surrounding prose.

## Confirmed discrepancies

Priorities: **P1** should be addressed before relying on the affected recovery
procedure. **P2** affects operation, diagnosis, or contributor understanding.
**P3** is a lower-impact precision or maintenance correction.

### 1. P1 — Blank-Pi restoration omits the external MQTT security files

**Documentation:** [Installation](../../docs/INSTALLATION.md), lines 488–527, and
[User Guide](../../docs/USER_GUIDE.md), lines 472–504, describe reconstruction from the
LabPulse archive. Neither includes restoring the external MQTT certificate,
private key, password database, and ACL before regeneration.

**Source:** [backup.py](../../src/labpulse/backup.py), `SNAPSHOT_PATHS` at line 24,
captures `mosquitto/data` but not `mosquitto/config/certs/server.crt`,
`server.key`, `external-passwords`, or `external-acl`.
[mosquitto.py](../../src/labpulse/deployment/mosquitto.py), lines 8 and 48, requires
all four when the external listener is enabled. The
[restore workflow](../../src/labpulse/control.py), lines 426–431, restores the source
and then regenerates it.

**Consequence:** an archive from a Triton-enabled installation is insufficient
for the documented blank-Pi recovery. Regeneration fails until the missing
security files are provisioned. Automatic rollback archives have the same
coverage limitation.

**Improvement:** publish an exact included/excluded-file table and an external
MQTT recovery procedure, including ownership and permissions. Either extend
the archive contract with tests or explicitly require a separate protected
copy and restore it before regeneration. Keep the offline CA private key and
Windows publisher state separately accounted for. Do not claim a complete
deployment backup until this boundary is resolved.

### 2. P2 — Saving unchanged configuration does not repair generated files

**Documentation:** [Installation](../../docs/INSTALLATION.md), lines 570–573 and
718–719, recommends `labpulse config` to repair damaged generated files or a
stale dashboard. The User Guide also broadly presents this as regeneration on
save.

**Source:** [edit_config.sh](../../deployment/edit_config.sh), lines 168–182, exits
when the source bundle and `config.resolved.yaml` are unchanged. It does not
compare installed Compose, fake-runtime, Mosquitto, or Home Assistant files
against the staged versions before that exit.

**Consequence:** closing an unchanged editor can print “Nothing was restarted”
while a damaged dashboard or fake-runtime file remains damaged. Repairing a
missing/different resolved runtime is a different case and can proceed.

**Improvement:** distinguish editing from repair. Document a mode-preserving
setup/regeneration procedure followed by applying the generated stack, or add
an explicit repair operation. A plain `labpulse setup` selects real hardware,
so repair instructions must retain `--fake-hardware` for simulated installs.
Add a test with valid unchanged source and deliberately damaged projections.

### 3. P2 — Optional readings can still make a service need attention

**Documentation:** [Configuration](../../docs/CONFIGURATION.md), lines 511–514,
[User Guide](../../docs/USER_GUIDE.md), lines 107–108, and
[Triton publisher](../../docs/TRITON_PUBLISHER.md), lines 837–838, promise that an
absent optional reading does not make the service unhealthy.

**Source:** [mqtt_json.py](../../src/labpulse/hardware/drivers/mqtt_json.py), lines
164–180, reports `HardwareIssue(code="missing_measurements")` for any missing
mapped field. Its source mapping does not carry `required` policy. The
[runner](../../src/labpulse/hardware/runner.py), lines 223–230, publishes that issue
as service status; the [health template](../../src/labpulse/homeassistant/templates/alarm/derived_entities.yaml.j2),
lines 57–64, classifies a non-`online` component status as **Needs attention**.

**Reproduction:** a payload containing one required field but omitting one
optional mapped field returns the valid reading plus `missing_measurements`.
This is distinct from whether a missing-reading notification is opened.

**Improvement:** decide the intended contract. Either required policy must
affect driver/component fault reporting, or the guide must qualify the
promise: optionality suppresses missing-reading incidents, but a reported
component fault can still affect service health. Test that distinction end to
end before changing the wording.

### 4. P2 — Danger percentage is time-based, not a count of observations

**Documentation:** [User Guide](../../docs/USER_GUIDE.md), lines 174–182, says that
70% of recent observations must be outside the threshold. The installation
troubleshooting section repeats the observations explanation.

**Source:** [derived_entities.yaml.j2](../../src/labpulse/homeassistant/templates/alarm/derived_entities.yaml.j2),
lines 8–19, configures `history_stats` with `type: ratio`. That measures the
time spent in the tracked state as a percentage of the window, as defined in
the [Home Assistant History Stats documentation](https://www.home-assistant.io/integrations/history_stats/#sensor-type).

**Consequence:** uneven sample spacing can give very different results from a
sample-count percentage. In a fully observed 120-second window, 70% means
84 seconds in the danger state, not 70% of received messages. The history
integration's evaluation schedule also affects when the transition is seen.

**Improvement:** explain elapsed-time evidence, availability gating, recovery,
and evaluation cadence. Use a worked timeline. Keep sample rate, freshness,
missing-data confirmation, danger window, and recovery duration distinct.

### 5. P2 — The no-unit-conversion promise is not true for all generated sensors

**Documentation:** [Configuration](../../docs/CONFIGURATION.md), lines 518–523, and
the User Guide's measurement/history section say configured classes are used
for LabPulse semantics/icons without exposing a convertible Home Assistant
device class.

**Source:** physical MQTT discovery follows that policy, but calculated
sensors explicitly emit `device_class` in
[derived_entities.yaml.j2](../../src/labpulse/homeassistant/templates/alarm/derived_entities.yaml.j2),
lines 29–34. Calculated sensors also emit an icon only when explicitly supplied,
whereas their configuration table describes the icon default as derived.

**Consequence:** the generated contracts differ between physical and
calculated sensors. The universal assurance about conversion cannot be made
from this source. Actual display/conversion depends on the Home Assistant
class, unit, and user settings.

**Improvement:** choose one unit policy, implement it consistently, and test
generated physical and calculated entities side by side. Until then document
the distinction explicitly, especially for calculated temperature differences.

### 6. P2 — Two package guides describe the old simulation topology

**Documentation:** [deployment package README](../../src/labpulse/deployment/README.md),
line 15, says fake mode omits physical outputs;
[output README](../../src/labpulse/output/README.md), line 15, explicitly says it
omits output workers.

**Source:** [compose.py](../../src/labpulse/deployment/compose.py) loops over enabled
outputs in both modes, removes hardware resource declarations in simulation,
and adds `--simulate`. The output process selects `SimulatedOutputDriver`.
The root README and current operator guides correctly describe this.

**Improvement:** update both package summaries to say the workers and switches
remain, with in-memory state and no output hardware access. Remove the
remaining “fake serial hardware” description from the roadmap's current
foundation.

### 7. P2 — The documented driver-health contract omits independent heartbeats

**Documentation:** [Architecture](../../docs/ARCHITECTURE.md), lines 310–338, lists
four runner states and unconditionally says a stale batch causes reconnect
and a valid reading is required before online. The
[hardware README](../../src/labpulse/hardware/README.md) and User Guide's freshness
section repeat that reading-only model.

**Source:** [HardwareDriver.health_status](../../src/labpulse/hardware/driver.py),
line 83, provides independent `SourceHealth`. The
[runner](../../src/labpulse/hardware/runner.py), lines 235–253, bypasses
reading-based reconnection when that health channel is available. It can mark
a publisher online without a fresh measurement and emits `awaiting_heartbeat`.
The architecture guide's later security section already describes this newer
behaviour correctly.

**Improvement:** make the contract state the two supported health paths. Add
`health_status`, `SourceHealth`, `awaiting_heartbeat`, component issue states,
and the `bind_measurements` hook to the contributor reference. Distinguish raw
publisher status from **Working**, which additionally requires current required
readings. A healthy heartbeat with expired data can show **Needs attention**.

### 8. P2 — The serial protocol promises duplicate rejection that does not exist

**Documentation:** [firmware README](../../firmware/README.md), line 258, says
duplicate names are invalid, and elsewhere requires exact name matching.

**Source:** [parse_serial_line](../../src/labpulse/hardware/drivers/serial_pipe.py),
lines 37–61, lowercases labels and assigns each usable number into a dictionary.
A later valid duplicate overwrites an earlier one.

**Reproduction:** `pressure:1|pressure:2` produces `{'pressure': 2.0}`;
`Pressure:1` produces `{'pressure': 1.0}`.

**Improvement:** distinguish producer requirements from parser tolerance. If
duplicates are meant to be rejected, change and test the parser deliberately;
otherwise document the actual overwrite behaviour. Include partial records,
`null`, non-finite values, case normalization, and unknown-channel handling in
one authoritative wire contract.

### 9. P2 — Triton commands assume a different Docker access policy

**Documentation:** [Installation](../../docs/INSTALLATION.md), lines 48–63, defaults
to `sudo docker`, with Docker-group access an explicit alternative. The
[Triton guide](../../docs/TRITON_PUBLISHER.md), lines 507, 516, 698 and 1082 onward,
uses bare `docker run` and `docker exec` without that prerequisite.

**Source:** [docker_command](../../src/labpulse/control.py), line 69, selects the
configured prefix or normally `sudo docker` on the Pi. Raw guide commands do
not use this function or `LABPULSE_DOCKER_COMMAND`.

**Improvement:** use the default documented access policy consistently or
explicitly label the alternative. Also include a small service-name table:
`mosquitto` is the Compose service used by `labpulse logs`; `labpulse-mqtt`
is the container name used by `docker exec`. Current diagnostic wording blurs
the distinction.

### 10. P2 — Editor failure recovery is described inconsistently

**Documentation:** [Installation](../../docs/INSTALLATION.md), lines 746–752,
describes accepted configuration followed by failed recreation and limits its
rollback explanation to validation/check failures. Earlier migration text
instead promises automatic rollback after installation failures.

**Source:** [edit_config.sh](../../deployment/edit_config.sh), lines 250–257,
explicitly restores the previous source bundle, regenerates it, and attempts
to recreate the old stack when the new Compose recreation fails. The retry
can itself fail and does not make the transaction atomic.

**Improvement:** document the exact stages and failure outcomes once: staged
validation, source installation, generated-file installation, Compose/HA
checks, recreation, rollback attempt, and manual recovery if rollback fails.
Do not imply that the new source necessarily remains active after failure, or
that rollback is guaranteed.

### 11. P2 — The hardware guide conflates BCM numbering and chip offsets

**Documentation:** [Hardware](../../docs/HARDWARE.md), lines 36–38 and 47, says Pi
configuration selects BCM GPIO numbers.

**Source:** the GPIO input/output and X1200 drivers use the configured Linux
`gpio_chip` and `gpio_line`; DHT11 uses a Blinka board pin name. The
[driver README](../../src/labpulse/hardware/drivers/README.md) and configuration
reference correctly describe a chip line offset.

**Improvement:** document each identifier explicitly: physical header pin,
BCM signal, gpiochip path plus line offset, and Blinka name. Supply a verified
mapping for the reference Pi/kernel only. Do not imply arbitrary chip line
offsets are universal BCM identities.

### 12. P2 — Operator lists omit two important generated Home Assistant files

**Documentation:** the “Do not edit” lists in
[Configuration](../../docs/CONFIGURATION.md) and [User Guide](../../docs/USER_GUIDE.md)
only show `homeassistant/config/labpulse-*.yaml` for HA output. Installation
also broadly says the existing HA directory is preserved.

**Source:** [generator.py](../../src/labpulse/homeassistant/generator.py), lines
34–41 and 105–122, replaces `configuration.yaml`,
`packages/labpulse_generated.yaml`, and `labpulse-dashboard.yaml`. Existing
`automations.yaml`, `scripts.yaml`, and `scenes.yaml` are preserved. The
architecture and HA package README already state the more precise policy.

**Improvement:** list all managed files at the point operators are told what
they may edit. Explain preservation of accounts/private state/UI files
separately from replacement of managed YAML. Include Mosquitto's generated
configuration versus its operator-provisioned TLS/authentication files.

### 13. P2 — Release and rollback instructions lack reliable version scope

**Documentation:** Installation uses `1.0.0` in executable installation/update
examples; configuration declares itself authoritative for future `0.3.7`;
upgrade procedures contain `VERSION_WITH_MEASUREMENT_FILES` and
`VERSION_WITH_HEARTBEAT`; the rollback example defaults to `0.1.1`.

**Evidence:** local tags inspected extend through `v0.3.6`. This does not prove
which remote artifacts currently exist. [CHANGELOG](../../CHANGELOG.md) has one
`Unreleased` section containing the project's whole modern foundation.
The former `ROADMAP.md` (removed on 18 September 2026) both describes production PyPI publication as implemented
and leaves it unchecked in Track A, while presenting Triton implementation as
future work despite the implemented publisher, driver, and guide.

**Improvement:** identify whether each guide describes the checkout or a
specific release. Replace runnable speculative versions with clearly marked
variables or verified releases. Create release-indexed change/migration notes
from tags and actual publication records. Distinguish implemented Triton
software from remaining site acceptance. State that restore regenerates using
the installed package; it does not install the archive's recorded version.
Only LabPulse's image is exact-versioned; HA `stable` and Mosquitto `2` remain
mutable tags in [compose.py](../../src/labpulse/deployment/compose.py).

### 14. P2 — The local project skill teaches a superseded architecture

**Documentation:** [.codex/skills/labpulse-project/SKILL.md](../../.codex/skills/labpulse-project/SKILL.md),
lines 16, 52, 123–145, 170 and 285–289, says the project is not in live use,
shows a copied `labpulse-python` tree, describes fake USB paths as the main
simulation route, refers to nonexistent `hardware/cli.py`, and names deleted
`SERIAL_PROTOCOL.md`, `DRIVER_DEVELOPMENT.md`, and `HOME_ASSISTANT.md` guides.
It also labels the pytest suite “lightweight script-based tests”.

**Evidence:** package entry points use `__main__.py`; deployments use versioned
images and simulated in-memory drivers; the release workflow explicitly checks
that `labpulse-python` is absent. Current docs describe an operating reference
installation.

**Improvement:** update this local instruction source alongside the public
docs. Prefer a small current repository map with links to maintained contracts.
This prevents future automated changes from reintroducing old assumptions.

### 15. P3 — Fake-mode acceptance incorrectly requires every value to change

**Documentation:** [Installation](../../docs/INSTALLATION.md), line 331, and the
User Guide's fake-mode acceptance say every measurement should be changing.

**Source:** [sensible_measurement_value](../../src/labpulse/hardware/_simulation.py)
returns constant `1.0` for GPIO and names indicating a present/active state.
Outputs also remain at their current state until commanded. Other values can
appear constant when rounded by configured precision.

**Improvement:** require continued publication and freshness for every
configured reading; only require variation for simulated analogue channels
where the generator produces it. Explain that simulation checks plumbing and
alarm controls, not physically accurate Triton values or fault scenarios.

### 16. P3 — Small but definite UI and command-reference errors

- [User Guide](../../docs/USER_GUIDE.md), line 165, calls the disabled alarm mode
  **Off**; the [helper options](../../src/labpulse/homeassistant/templates/alarm/helpers.yaml.j2),
  line 113, use **Disabled**.
- User Guide lines 187–188 describe strictly below/above recovery boundaries;
  [derived entities](../../src/labpulse/homeassistant/templates/alarm/derived_entities.yaml.j2),
  lines 147–149, use inclusive `<=` and `>=`.
- [Triton guide](../../docs/TRITON_PUBLISHER.md), line 977, uses
  **Unavailable — optional** instead of the current **No recent data — optional**.
- [Architecture](../../docs/ARCHITECTURE.md), lines 136–145, omits `update` and
  `uninstall` from its operator command list.
- [Installation](../../docs/INSTALLATION.md), lines 413–419, says every command
  checks for updates and update always fetches fresh release metadata.
  [control.py](../../src/labpulse/control.py), lines 627 and 955, excludes
  `uninstall` and the normal update notifier; an explicitly supplied version
  skips the latest-version JSON lookup. Distinguish that lookup from pipx's
  package-index access.

## Important coverage improvements

These are missing or weak guidance, rather than all being false statements.

### A. Make real-hardware commissioning self-contained

The installation guide sends modem users to User Guide SMS testing, which
sends them to the configuration reference, which only documents recipient
lists and dry-run. There is no complete current host ModemManager installation,
service, SIM/network, modem-detection, and first-message procedure. The sender
selects the first modem reported by `mmcli`; no YAML modem selector exists.
Explain that limitation and the actual host/container boundary.

Similarly, the documented 30-second systemd watchdog decision is in the
roadmap, and Doctor checks it, but a new operator has no maintained setup and
verification procedure. Add these prerequisites and I2C enablement to the
installation guide, tied to the qualified host. Record commands and expected
results instead of relying on maintainer knowledge.

### B. Document switching modes and the first configuration edit

The User Guide refers readers to Installation for changing between fake and
real operation, but Installation supplies separate initial-install paths.
Add a short explicit transition procedure that preserves source and HA state,
reviews enabled hardware/output/SMS configuration, selects the desired setup
mode, applies the stack, and verifies mode in Doctor. Make clear that setup
alone regenerates files but does not start containers, while a changed
`labpulse config` edit recreates the stack. The first real install should tell
operators to disable absent example services before applying the starter.

### C. Consolidate operational ownership

Installation is approximately 770 lines and includes installation,
development, two feature migrations, updates, backup, removal, and extensive
diagnosis. Operations is short and duplicates parts of the User Guide.
Troubleshooting starts with a one-time Recorder purge and covers only a subset
of failures. Development explicitly sends symptom-led recovery to Installation.

Use Installation for first commissioning, User Guide for dashboard behaviour,
Configuration for the schema, Operations for lifecycle/backup/update/removal,
and Troubleshooting for all symptoms. Move release-specific migrations to
versioned release notes. Keep redirecting links so existing references work.
Update the documentation index and contributor ownership rules together.

### D. Turn package summaries into usable extension guidance

The driver README lists the modules but does not walk a contributor through
adding one. Link [driver_template.py](../../docs/examples/driver_template.py), show
where to copy it, give a complete minimal configuration and focused test,
explain lazy dependencies and runtime image rebuilds, and cover input versus
output driver requirements. `container_requirements` is required by
`DriverDefinition`, despite Development calling it optional. Keep a concise
API reference for measurement binding and independent source health.

The real-hardware README describes the fault helpers but lacks their actual
`block`, `block-i2c`, `block-gpio`, `block-all`, `status`, and `restore` usage,
expected states/timing, and restoration check. These details exist in the
scripts and should be discoverable before starting a fault exercise.

### E. Make hardware records identifiable and dated

The three spreadsheets are useful historical evidence but not a current BOM:

- [Internship purchased items.xlsx](purchasing-2026-09-18/Internship%20purchased%20items.xlsx),
  Sheet1 A4, says `SEN057`; [LabPulse Sensors.xlsx](purchasing-2026-09-18/LabPulse%20Sensors.xlsx),
  Sheet1 A10, says `SEN0257`. Reconcile the actual part rather than guessing.
- The purchased-items workbook explicitly marks its UPS as superseded and
  points to X1200 in E12. It should be labelled historical purchases.
- The sensor inventory records “Working”, partial failures, and unknown
  models/locations without observation dates or hardware revisions. It cannot
  establish current commissioning status and lacks the new pressure-hub SHT40.
- [Mini Shopping List.xlsx](purchasing-2026-09-18/Mini%20Shopping%20List.xlsx) describes proposed
  purchases without purchased/installed status or a date. Its prices were not
  checked against current suppliers.
- An Office owner-lock file, `docs/~$Internship purchased items.xlsx`, is tracked.
  Remove it in a cleanup change and ignore Office lock files.

Add a hardware index linking existing design assets and explicitly identifying
their status. Avoid the Hardware guide's blanket “no manufacturer/model” style
of explanation where partial evidence already exists; distinguish recorded,
verified, and unknown parts. Do not turn historical evidence into a validated
wiring guide without physical checks.

### F. Clearly label legacy entry points

`legacy/Installation/QUICKSTART.md` still opens as “LabPulse v2.0” and orders
readers to follow exact factory-reset instructions. The compatibility guide
asserts a different tested hardware/software matrix, and `legacy/Future_work`
describes a single master hub as the new architecture. The legacy README only
points to the current installation much later in its text.

Put a brief historical/unsupported banner and a current-guide link at the top
of each legacy entry document. Add an inventory covering the old Word/PDF
installation material. Preserve its historical content; do not rewrite it to
look like a supported deployment path.

### G. Document the external publisher's operational lifecycle

The Triton guide is detailed but tightly bound to one two-fridge topology.
Separate the reusable publisher/MQTT contract from the local network runbook.
Document certificate expiry/renewal, credential rotation, protected backup,
publisher removal, and how to remove the added host route and service cleanly.
Explain that `recorded_at` is the source record's acquisition time, not the
time an old record is republished.

Review the instruction granting the entire Windows `Users` group Modify access
to the publisher directory: it grants modification of the executable script,
wrapper, CA certificate, and password file, not just log access. Scope access
to the intended publisher/operator identities and separate writable logs from
configuration where appropriate. This recommendation follows the actual
permissions command, not a claim that the current lab has been compromised.

### H. Test documentation contracts, not only links

Keep the existing link/example tests. Add targeted checks tied to behaviour:

1. Complete driver and mode examples, including outputs and a heartbeat source.
2. A restore fixture with the external TLS listener enabled.
3. An unchanged-source repair case with damaged generated files on Linux.
4. Optional missing MQTT fields through runner and rendered service health.
5. Physical and calculated unit/class/icon policy side by side.
6. Serial duplicate/case examples and real generated alarm-mode labels.

Extract field defaults and command options from their owning models/parser
where this avoids duplication, while keeping explanations written for people.
Record a tested source revision and prerequisite versions for operational
runbooks. Avoid brittle tests that merely assert the same sentence appears in
two files.

## Document coverage and disposition

| Document group | Assessment and next action |
|---|---|
| Root README and overview image | Current high-level topology and fake-mode description are broadly sound. Link to one authoritative workflow per task; qualify simulated value variation. |
| Configuration | Tables largely match current models. Resolve optional-health and calculated-unit promises, name all generated files, and state release scope. |
| User Guide | Useful operator structure. Correct timing, heartbeat freshness, unit policy, exact UI names, and backup coverage. |
| Installation | Correct broad pipx/container route, but repair, rollback, prerequisites, and version examples need attention. Move repeated lifecycle and migration material. |
| Operations and Troubleshooting | Expand into authoritative lifecycle and symptom guides; replace duplicated prose with links. |
| Architecture | Broad ownership is accurate. Reconcile its earlier reading-only health contract with its later heartbeat explanation; complete command and driver contracts. |
| Development and Contributing | Mostly aligned with package/CI structure. Improve driver onboarding, documentation ownership, and precise required resources. |
| Hardware, spreadsheets, 3D-parts README | Explicit limitations are useful. Correct GPIO naming, date inventories, reconcile parts, and provide a discoverable asset index. |
| Triton guide | Substantial current implementation coverage. Align Docker policy, optional-health/UI descriptions, version prerequisites, recovery, and lifecycle. |
| Firmware README and examples | Headers generally support the described sensors/calibration. Correct parser guarantees and distinguish the commissioning publisher from heartbeat-aware production use. |
| Python/package/template/deployment READMEs | Most ownership summaries match source. Fix simulated outputs and heartbeat contract; mention external measurement fragments consistently. |
| Testing READMEs and example configs | Complete examples pass. Document real fault commands and fill behavioural documentation-test gaps. |
| CHANGELOG and ROADMAP | Reconcile with release history and implemented features; separate historical acceptance from current qualification. |
| SECURITY and CITATION | No direct current-source contradiction found. Reporting/support policy and citation structure still need maintainer ownership; external reporting availability was not tested. |
| Legacy material | Keep historical, but add prominent current-guide routing. Historical binary contents are outside current-behaviour validation. |
| Local project skill | Update obsolete paths, layout, simulation, and deployment-status assumptions. |

## Suggested delivery order

1. Resolve backup/reconstruction coverage and publish reliable recovery steps.
2. Decide and test optional-health and calculated-unit contracts; correct alarm
   timing, parser behaviour, and heartbeat explanations.
3. Fix repair/rollback procedures, simulation statements, generated-file
   ownership, Docker commands, and exact UI terminology.
4. Consolidate guide ownership, complete commissioning prerequisites, and
   version the changelog/migration notes.
5. Refresh hardware/legacy indexes and the local project skill; add focused
   documentation-contract checks to prevent the same drift recurring.
