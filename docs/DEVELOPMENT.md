# Development

This guide covers the current source tree, package entry-point conventions,
local execution, tests, generated artifacts, and release checks.

## Requirements

Development requires:

- CPython 3.11 or 3.12 for the supported package matrix;
- Git;
- pipx when exercising the installed operator CLI;
- Docker with the Compose plugin for container and deployment checks;
- Bash for deployment-script syntax and Linux workflows;
- no physical hardware for the normal test suite.

Development can take place on Windows, macOS, or Linux. The supported runtime
host is defined separately in [Supported environments](SUPPORT.md).

## Editable installation

From the repository root:

```bash
pipx install --editable . --force
labpulse help
```

Python source changes are immediately visible to the pipx command. Reinstall
after changing package metadata, console entry points, dependencies, or package
data declarations.

For direct module execution without pipx:

```bash
python -m pip install -e ".[dev]"
python -m labpulse.control --help
python -m labpulse.hardware --help
python -m labpulse.homeassistant --help
python -m labpulse.sms --help
python -m labpulse.deployment --help
```

## Host code and runtime images

The operator CLI and generators run from the installed Python package. Sensor
and SMS services run from a container image, so an editable host install alone
does not test runtime source changes.

Build and select a local image:

```bash
python -m pip install build setuptools-scm
LABPULSE_VERSION="$(python -m setuptools_scm)"
python -m build
docker build \
  --build-arg LABPULSE_VERSION="$LABPULSE_VERSION" \
  -t "labpulse-dev:$LABPULSE_VERSION" .
export LABPULSE_IMAGE="labpulse-dev:$LABPULSE_VERSION"
labpulse setup --fake-usb
cd ~/labpulse-live
./simulate_serial.py start
labpulse up
```

Generation uses `LABPULSE_IMAGE` when it is set. Otherwise it selects the GHCR
tag matching the installed package version.

## Source tree

```text
src/labpulse/
  control.py         operator CLI and workflow orchestration
  installer.py       packaged setup launcher
  backup.py          backup archive and restore primitives
  doctor.py          read-only diagnostics
  common/            shared typed contracts
  deployment/        Compose rendering and unified generation
  hardware/          hardware service and driver system
  homeassistant/     Home Assistant generation
  sms/               notification delivery

deployment/          packaged Linux workflow scripts
testing/             executable hardware-free tests
firmware/            Arduino library and examples
hardware/            PCB and enclosure assets
docs/                maintained documentation
```

See [Architecture](ARCHITECTURE.md) for the complete ownership model.

## Package entry-point convention

Standalone process packages keep their small command composition at the
package boundary instead of adding a second forwarding module:

```text
package/__main__.py → importable domain modules
```

Current examples:

| Package | CLI | Domain modules |
|---|---|---|
| `hardware` | `src/labpulse/hardware/__main__.py` | runner, registry, drivers, publisher |
| `homeassistant` | `src/labpulse/homeassistant/generator.py` | alarm context and templates |
| `sms` | `src/labpulse/sms/__main__.py` | subscriber and sender |
| `deployment` | `src/labpulse/deployment/generate.py` | Compose renderer and install transaction |

CLI modules should:

- parse arguments;
- load configuration once;
- compose domain objects;
- translate expected user-facing failures into exit status and messages.

Domain modules should:

- accept explicit typed arguments;
- remain importable without reading `sys.argv`;
- return values or raise domain exceptions rather than exiting;
- keep filesystem/network mutation at clear orchestration boundaries.

The public operator command is different: `control.py` intentionally
coordinates complete installed workflows such as setup, guarded config edits,
backup, restore, diagnostics, and Compose lifecycle commands.

## Configuration ownership

Configuration is split by the concepts being validated:

- `src/labpulse/common/config.py` owns global settings, cross-references,
  source-aware errors, and the only production YAML loader;
- `src/labpulse/common/measurement_config.py` owns physical and calculated
  measurements, including formula validation;
- `src/labpulse/common/service_config.py` owns drivers, service timing, and
  dedicated power-service rules.

`load_config()` returns a source-aware `ConfigDocument` whose selected driver
options are already typed.

When changing configuration:

1. update the shared model or the owning driver's configuration model;
2. update `config.yaml` if the starter shape changes;
3. update fake derivation when the field affects simulated transport;
4. update Compose and Home Assistant consumers only where behavior changes;
5. update `docs/CONFIGURATION.md`;
6. add validation and generated-output tests.

Do not add hardware-specific fields to `ServiceConfig`. Put them beneath
`driver.options` and let the driver definition own validation.

## Generation model

Compose rendering is pure text generation in:

```text
src/labpulse/deployment/compose.py
```

The unified install transaction is in:

```text
src/labpulse/deployment/generate.py
```

It loads one config document, renders Compose, stages every Home Assistant
artifact, and installs managed live files only after all rendering succeeds.

Home Assistant generation is split by responsibility:

```text
src/labpulse/homeassistant/generator.py    command, config/dashboard render, and file install
src/labpulse/homeassistant/alarm.py        derived alarm/dashboard render context
src/labpulse/homeassistant/templates/      final-shaped YAML behavior
```

Generator Jinja uses `[% ... %]` and `[[ ... ]]`. Home Assistant's
`{% ... %}` and `{{ ... }}` must survive into generated YAML.

Prefer shallow, feature-named includes. Keep alarm and dashboard behavior in
readable final-shaped YAML rather than recreating a generic card or automation
builder in Python.

## Running tests

Install the development dependencies and run the complete hardware-free suite:

```bash
python -m pip install --editable ".[dev]"
python -m pytest
```

Run a single module, test, or matching group while developing:

```bash
python -m pytest testing/test_homeassistant_generator.py
python -m pytest testing/test_control_cli.py::test_version_command_reports_the_package_version
python -m pytest -k restore
```

Pytest discovers tests below `testing/`; `testing/conftest.py` owns shared
repository and temporary-directory fixtures. Tests should be small, named for
one observable behavior, and use parametrization when only inputs and expected
results vary. Do not add module-level runners or mutate `sys.path` in tests.

The same suite runs for Python 3.11 and 3.12 on every push and pull request.
Release validation runs it again before building distribution artifacts.

Focused suites:

| Area | Tests |
|---|---|
| Config, IDs, MQTT, shared contracts | `test_config_pipeline.py`, `test_common_contracts.py` |
| Operator CLI, backup, restore, doctor | `test_control_cli.py`, `test_backup_restore.py`, `test_doctor.py` |
| Driver registry and options | `test_hardware_factory.py` |
| Runner lifecycle and retry | `test_hardware_runner.py` |
| Serial protocol and driver | `test_serial_parser.py`, `test_serial_driver.py` |
| DHT11 and X1200 | `test_dht11_driver.py`, `test_x1200_ups_driver.py` |
| MQTT discovery/state | `test_homeassistant_publisher.py` |
| Home Assistant context/generation | `test_homeassistant_entities.py`, `test_homeassistant_generator.py` |
| Home Assistant dashboard YAML | `test_yaml_dashboard.py` |
| Power and setup alarm behavior | `test_power_monitor.py`, `test_setup_grouping.py`, `test_notification_context.py` |
| Compose and atomic generation | `test_deployment_generation.py`, `test_unified_generation.py` |
| Packaging and container release | `test_packaging.py`, `test_container_release.py` |
| Fake hardware and USB mapping | `test_simulate_serial.py`, `test_usb_setup.py` |
| SMS pipeline | `test_sms_container.py` |
| Firmware layout | `test_firmware_layout.py` |

Tests that simulate device failures intentionally emit warning or error logs.

## Hardware-free design

Production code should expose narrow injection points for clocks, subprocess
runners, MQTT clients, serial transports, buses, GPIO readers, and modem
commands. Tests use small fakes rather than broad environment emulation.

Optional hardware libraries must be imported lazily when a driver connects.
Registry discovery, config validation, Compose generation, and ordinary unit
tests must work on a desktop without GPIO, I2C, or serial hardware.

## Deployment scripts

Source assets live under `deployment/` and are copied into the flat live
directory by setup.

```bash
bash -n deployment/*.sh
```

Do not run `setup_container_fs.sh` on a development workstation unless a real
Linux live installation is intended. It creates a live directory and managed
virtual environment and invokes generation workflows.

The shell scripts own Linux interaction and guarded workflow sequencing. They
delegate configuration validation and document generation to Python modules.

## Driver changes

Use `labpulse.serial_pipe` when firmware can emit the standard protocol. Add a
direct driver only when the transport requires Python-owned hardware access or
protocol logic.

A direct driver keeps its configuration, implementation, optional container
requirements function, and `DRIVER_DEFINITION` together in one module. See
[Driver development](DRIVER_DEVELOPMENT.md).

## Code quality

- Organize code in the order a reader encounters the work: configuration,
  domain-specific helpers, the main operation, then integration declarations.
- Keep one operation's decisions together when splitting them into helpers
  would force the reader to jump around to reconstruct the normal path.
- Keep a short call or expression on one line when it remains comfortably
  readable. Do not add vertical structure merely to satisfy a narrow line limit.
- Prefer descriptive names such as `last_successful_read_at` over short names
  that depend on surrounding context.
- Introduce a class, protocol, or data model only when it expresses shared
  state, a real boundary, or a reused contract.
- Put principal collaborators before runtime facilities and private lifecycle
  bookkeeping so the importance of stored state is immediately visible.
- Write for an undergraduate physicist who may know basic Python but not
  advanced Python, shell, YAML/Jinja, MQTT, Docker, or hardware-library idioms.
- Use short comments to translate complicated expressions, slightly advanced
  syntax, and unfamiliar procedures into plain language. Narrating nearby code
  is useful when the syntax would otherwise make the reader stop and decode it.
- Use longer comments for safety constraints and reasons that the code itself
  cannot show. Skip narration only when the nearby code is already obvious to
  that audience.
- Keep the successful path visible and handle expected failures beside the
  operation that can produce them.
- Validate untrusted input once at its system boundary. After conversion to a
  typed internal object, trust it instead of repeating validation downstream.
- Put behavior in the package that owns the decision.
- Keep `common` dependency-light and limited to genuinely shared contracts.
- Centralize IDs and MQTT topics.
- Keep alarm decisions in Home Assistant.
- Use strict option models and explicit failure classes.
- Give functions and public types docstrings and type annotations.
- Make cleanup idempotent and safe after partial initialization.
- Preserve user-owned files when generation or validation fails.
- Do not hand-edit generated output as a source change.

## Documentation changes

Document only current behavior:

- installation or host prerequisites → `INSTALLATION.md`;
- config schema → `CONFIGURATION.md`;
- operator commands → `OPERATIONS.md`;
- symptom-led recovery → `TROUBLESHOOTING.md`;
- Home Assistant behavior → `HOME_ASSISTANT.md`;
- SMS behavior → `SMS.md`;
- component ownership/contracts → `ARCHITECTURE.md`;
- contributor workflow → this guide or `DRIVER_DEVELOPMENT.md`;
- unimplemented work → `ROADMAP.md`.

Do not create parallel implementation-history or refactor documents.

## Package and release checks

Metadata and console entry points live in `pyproject.toml`. The Git tag is the
released version source through `setuptools-scm`.

Build locally:

```bash
python -m build
```

Before release:

1. run the complete hardware-free suite;
2. build wheel and source distribution;
3. install each artifact in a clean environment;
4. verify console entry points and package data;
5. smoke-test the runtime image on supported architectures;
6. update the changelog;
7. create an immutable `vVERSION` release tag.

The release workflow publishes Python artifacts and version-matched AMD64 and
ARM64 images. Never move or reuse a released tag; correct it with a new patch
release.

## Real-Pi acceptance

Hardware-free tests cannot establish:

- GPIO/I2C/serial permissions and electrical behavior;
- USB enumeration and reconnect behavior under the Pi kernel;
- D-Bus and ModemManager integration;
- Home Assistant behavior across real host restarts;
- long-duration reliability.

Record the source revision, Pi model, OS, configuration, procedure, observed
result, and logs for real-hardware acceptance.
