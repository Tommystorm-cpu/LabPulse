---
name: labpulse-project
description: Maintain LabPulse code, Raspberry Pi deployment, Arduino firmware, hardware records, and documentation. Use for work in this repository to find the owning modules, preserve live installation state, and select appropriate validation.
---

# LabPulse project

LabPulse monitors laboratory infrastructure using Raspberry Pi, Arduino,
MQTT, and Home Assistant. It has published releases and live installations.
It provides best-effort monitoring and explicitly configured non-safety GPIO
outputs, not a safety-rated alarm or protective interlock.

This skill is checked into the repository. Keep it aligned with current code
and maintained documentation; do not turn a historical installation detail
or an untested proposal into a universal requirement. Paths in code spans
are relative to the repository root unless identified as installed paths.

## Start with the owning guide

Check the working tree before editing and preserve unrelated work. Read the
guide relevant to the task, then inspect its source and tests. Existing code,
package metadata, and workflows establish implemented behaviour; record any
disagreement with the docs rather than assuming either is current.

| Task | Start here |
|---|---|
| First contribution or repository orientation | [Maintaining](../../../docs/MAINTAINING.md), [Architecture](../../../docs/ARCHITECTURE.md) |
| Development environment, code conventions, container testing | [Development](../../../docs/DEVELOPMENT.md), [test map](../../../testing/README.md) |
| Blank Pi, installed commands, faults or recovery | [Installation](../../../docs/INSTALLATION.md), [User guide](../../../docs/USER_GUIDE.md), [Troubleshooting](../../../docs/TROUBLESHOOTING.md) |
| Configuration schema and examples | [Configuration](../../../docs/CONFIGURATION.md), `src/labpulse/common/` |
| Driver lifecycle or new sensor support | [Driver guide](../../../src/labpulse/hardware/drivers/README.md), [hardware package](../../../src/labpulse/hardware/README.md) |
| Arduino protocol and conversions | [Firmware](../../../firmware/README.md), [hardware evidence](../../../docs/HARDWARE.md) |
| Windows Triton publishers | [Publisher source](../../../integrations/triton/README.md), [deployment guide](../../../docs/TRITON_PUBLISHER.md) |
| Dashboards, alarms, notifications | [Home Assistant package](../../../src/labpulse/homeassistant/README.md), [SMS package](../../../src/labpulse/sms/README.md) |
| Controlled GPIO outputs | [Output package](../../../src/labpulse/output/README.md) |
| Main unit, wiring, enclosure, purchasing | [Main unit](../../../docs/MAIN_UNIT.md), [purchasing workbook](../../../docs/LabPulse%20Purchasing.xlsx) |
| Release or Pi update | [Releasing](../../../docs/RELEASING.md), `.github/workflows/release.yml` |

## Runtime and configuration boundaries

- `src/labpulse/control.py` owns the public `labpulse` CLI. Prefer it in operator
  instructions over low-level wrappers or older command aliases.
- `installer.py` locates packaged assets; `deployment/setup_container_fs.sh`
  prepares the Linux filesystem. Python generation lives in
  `src/labpulse/deployment/`, not the shell wrappers.
- The repository's `config.yaml` and `config.d/` are starter assets. The
  installed source is `~/labpulse-live/config.yaml` plus referenced measurement
  mappings in `config.d/`, or the directory selected with `--live-dir`.
- `common/config.py` loads a validated, source-aware `ConfigDocument`. Keep
  shared IDs and MQTT contracts in `common/identity.py` and
  `common/mqtt_contracts.py`. Consumers use typed settings instead of parsing
  YAML or inventing their own IDs and topics.
- `config.resolved.yaml`, `config.fake.yaml`, `compose.yaml`, and managed Home
  Assistant YAML are generated. Fix their source or generator and regenerate.
  Generation stages all renders before replacing files, but replacement is
  atomic only per file, not across the whole deployment.
- Compose runs Home Assistant, Mosquitto, one SMS worker, one worker per enabled
  sensor service, and one worker per enabled output. There is no supported
  grouped-worker mode to preserve or extend unless the task introduces one.
- LabPulse containers reach MQTT through `mosquitto:1883`. Host-networked Home
  Assistant reaches the loopback publication at `127.0.0.1:1883`. External
  publishers use the separately configured listener; do not broaden broker
  exposure merely to fix an internal connection.
- Drivers acquire and normalize readings; the runner owns retry, scheduling,
  freshness and cleanup; the publisher owns MQTT discovery/state/availability.
  Home Assistant owns thresholds, alarm transitions and notification requests.
  SMS workers deliver requests; output workers enforce GPIO command policy.

Home Assistant generation has two template languages: LabPulse uses
`[% ... %]` and `[[ ... ]]`; Home Assistant's `{% ... %}` and `{{ ... }}` must
survive generation. Read the package guide before changing those templates.

## Change the appropriate boundary

For configuration changes, update the owning model, affected generators and
consumers, starter examples, configuration reference, and relevant tests.
Device-specific settings belong in the driver's strict options model, not in
the global service model. Preserve user-facing measurement and entity identity
unless changing it is an intentional, documented part of the task.

For a hardware driver, use the current driver guide and contributor example.
Keep configuration, device helpers, the named driver, resource requirements,
and `DRIVER_DEFINITION` together. The registry discovers public driver modules;
private support modules start with `_`. Import optional hardware libraries
lazily when connecting so host configuration and tests work without them.
Drivers implement `connect/read/close` and return `HardwareReadings`; they do
not publish LabPulse MQTT output or implement their own retry loop.

Arduino examples use unit-free `name: value | name: value` serial lines.
When changing that contract, inspect `firmware/`,
`src/labpulse/hardware/drivers/serial_pipe.py`, the serial parser/driver tests,
measurement mappings, and firmware docs together. Prefer `/dev/serial/by-id/`
paths for deployed USB devices. Separate the firmware present in the checkout
from the version confirmed flashed onto a board. A conversion constant in code
or a matching part in a spreadsheet is not evidence of completed calibration.

Write code for maintainers who know basic Python but may not know Docker,
MQTT, Jinja, or hardware libraries. Keep the normal operation readable from
top to bottom, use descriptive names, type annotations and useful docstrings,
and explain unfamiliar syntax or important constraints. Avoid abstractions
that scatter one coherent procedure or exist only to make tests convenient.
Tests should supply fake collaborators at the real boundaries.

`legacy/` contains historical implementations and purchasing records. Consult
it for provenance when relevant; do not add support for every legacy shape.
Compatibility work should address a concrete supported-release requirement.
Public command, configuration, protocol or extension changes need the migration
notes and versioning described in [Contributing](../../../CONTRIBUTING.md).

## Simulation and validation

Use `labpulse setup --fake-hardware` on a dedicated development Linux host
for a complete simulated installation. It preserves configured services,
measurements and presentation, runs sensors and outputs in memory, removes
their physical device requirements, and forces SMS dry-run. It does not require
pseudo-terminal USB links. The separate serial simulator remains useful for
testing the serial transport itself.

An editable host install changes the CLI and generators, not the code inside
worker containers. For runtime changes, follow the development guide to rebuild
the wheel and image and select it through `LABPULSE_IMAGE` before regenerating.
A separate live directory alone does not isolate a second stack: container
names and host ports can collide with the live installation.

In the development environment:

```text
python -m pip install --editable ".[dev]"
python -m pytest testing/test_documentation.py
python -m pytest testing/test_control_cli.py
python -m pytest
```

Choose the focused suite that matches the change using the test map; the
commands above are examples, not a requirement to repeat every check. Run the
full hardware-free suite for changes spanning shared contracts or multiple
packages. CI's supported Python matrix is defined in `.github/workflows/test.yml`.
Use shared fixtures in `testing/conftest.py`; do not mutate `sys.path` or add
module-level test runners. Keep disposable artifacts in ignored `testing/tmp/`.

Report what checks prove. Windows runs may skip Linux/symlink checks, YAML
generation tests do not prove a Home Assistant screen works, and fake hardware
does not validate wiring, calibration, UPS switchover, or modem delivery.
Use `testing/real_hardware/` only for deliberately authorised physical checks.
For packaging changes, also verify installed wheel/sdist assets; checkout tests
alone cannot prove scripts or templates were included in the distribution.

## Installed state and release work

Before operating on a Pi, identify the host, logged-in account, installation
directory, and real/fake mode. Keep ordinary commands under the installation's
user; running `sudo labpulse` can select a different home or miss pipx's PATH.
Use the CLI's scoped privilege handling where available.

Treat Home Assistant accounts, `.storage`, history, live configuration,
Mosquitto data and SMS state as user-owned. Updates should preserve them.
Container removal or Docker reinstallation does not reset mounted data.
For a reset, inspect actual mounts and resolve the intended path before
removing anything; a remembered Compose path may no longer exist. Privileged
containers can create root-owned files, so cleanup must handle permissions
without broadening the confirmed deletion target.

For a release, use the tag-derived version and the current release guide.
Publishing a GitHub release triggers the workflow; pushing a tag alone does
not. Confirm both the Python package and matching full-version container image
are available before recommending a Pi update. Neither publication nor a live
update is implied by a request to edit or test code. Never move a published tag.

Test updates on a development Pi first, preserve a backup, and check fresh
readings and affected behaviour afterward. Account for Home Assistant startup
Test mode and notification controls. An attempted update can partly succeed;
do not describe it as automatically rolled back.

## Documentation and evidence

Keep operator instructions on the public CLI and explain unfamiliar terms.
Use Micro in Pi editing examples, consistent with the installation guide,
while respecting an operator's configured `VISUAL` or `EDITOR`.

Follow root `AGENTS.md` for `screenshot.md` maintenance. Use real captures for
screenshots; distinguish live-installation showcases from simulated tutorials.
Mark a documentation task complete only when its evidence or deliverable exists.
Keep unverified acceptance steps explicit in the relevant guide rather than
implying they passed because unit tests are green.

Keep hardware statements dated and sourced. Distinguish requested, purchased,
received, fitted and tested parts; current configuration is not proof of wiring.
Maintain the current purchasing workbook and preserve original records under
`legacy/`. Do not copy phone numbers, credentials, local Home Assistant state,
logs, or private configuration into publishable examples or screenshots.
