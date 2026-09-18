# Development

Use this guide when you need a development command, a project convention, or
the steps for trying changed code on a Pi.

New to the code? Start with [Your first day maintaining LabPulse](MAINTAINING.md)
for a checkout-to-first-change walkthrough. This page is the reference for
the conventions and commands you'll use afterward.

## Requirements

What you need depends on what you're checking:

- CPython 3.11 or 3.12 for the supported package matrix;
- Git;
- pipx when exercising the installed `labpulse` command;
- Docker with the Compose plugin for container and deployment checks;
- Bash for deployment-script syntax and Linux workflows;
- no physical hardware for the normal test suite.

You can edit code and run the ordinary Python tests on Windows, macOS, or Linux.
Use a Linux development host for the complete deployment workflow. The tested
Pi and OS combination is described in [Installation](INSTALLATION.md#requirements).

## Editable installation

For a first checkout, follow the
[virtual-environment instructions](MAINTAINING.md#1-get-a-working-checkout).
They work without pipx, Docker, or hardware.

To exercise the pipx-installed command on a dedicated development Pi, install
from the repository root:

```bash
pipx install --editable .
labpulse help
```

Use a host without an existing pipx LabPulse install for this route. Python
source changes are visible the next time the command runs. Reinstall
after changing package metadata, console entry points, dependencies, or package
data declarations.

For direct module execution without pipx:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# PowerShell: .venv/Scripts/Activate.ps1
python -m pip install -e ".[dev]"
python -m labpulse.control --help
python -m labpulse.hardware --help
python -m labpulse.homeassistant --help
python -m labpulse.sms --help
python -m labpulse.output --help
python -m labpulse.deployment --help
```

## Host code and runtime images

The operator CLI and generators run from the installed Python package. Sensor,
output, and SMS services run from a container image, so an editable host install
alone does not test runtime source changes.

Use the commands below in **Bash on a dedicated Linux development host**, from
the checkout with its virtual environment active. Docker and the Compose
plugin must be installed. A development Pi is the closest match to deployment.
Don't run a second LabPulse stack beside a live one: changing `--live-dir`
doesn't isolate the fixed container names or host ports.

Build and select a local image. The Dockerfile installs the wheel in `dist/`,
so rebuild that wheel whenever runtime source changes:

```bash
python -m pip install build setuptools-scm
LABPULSE_VERSION="$(python -m setuptools_scm)"
python -m build
docker build \
  --build-arg LABPULSE_VERSION="$LABPULSE_VERSION" \
  -t labpulse-dev:working .
export LABPULSE_IMAGE=labpulse-dev:working
labpulse --live-dir ~/labpulse-dev-live setup --fake-hardware
labpulse --live-dir ~/labpulse-dev-live up
```

Generation uses `LABPULSE_IMAGE` when it is set. Otherwise it selects the GHCR
tag matching the installed package version. The local tag above stays valid
even when the Git-derived package version contains development-version text.
Use the same Docker daemon for building and running; if it requires `sudo`,
use `sudo docker build` in place of `docker build`.

Complete [Home Assistant onboarding](INSTALLATION.md#open-home-assistant), then
try [the practice alarm](FIRST_STEPS.md#3-make-a-practice-alarm). This development
directory starts with the packaged starter, not the small file generated under
`testing/tmp/`. Use `labpulse --live-dir ~/labpulse-dev-live config` to change it.

After another edit, rebuild the wheel and image using the commands above, then
recreate the stack so containers use the rebuilt image:

```bash
labpulse --live-dir ~/labpulse-dev-live down
labpulse --live-dir ~/labpulse-dev-live setup --fake-hardware
labpulse --live-dir ~/labpulse-dev-live up
```

Keep `LABPULSE_IMAGE=labpulse-dev:working` set in that shell during setup.
`down` preserves saved settings and history. For a host-only change, rebuilding
the worker image isn't needed; for a template change, regenerate its YAML and
restart Home Assistant. Use `down` when finished with the development stack.

## Source tree

```text
src/labpulse/
  control.py         operator CLI and workflow orchestration
  installer.py       packaged setup launcher
  backup.py          backup archive and restore primitives
  doctor.py          read-only diagnostics
  usb.py             interactive USB serial port assignment
  common/            shared typed contracts
  deployment/        Compose rendering and unified generation
  hardware/          hardware service and driver system
  homeassistant/     Home Assistant generation
  output/            controlled-output worker
  sms/               notification delivery

deployment/          packaged Linux workflow scripts
testing/             executable hardware-free tests
firmware/            Arduino library and examples
integrations/triton/ standalone Windows logfile publishers and launcher
hardware/            PCB and enclosure assets
docs/                maintained documentation
```

See [Architecture](ARCHITECTURE.md) for the complete ownership model.

## Package entry-point convention

Standalone process packages keep their small command composition at the
package boundary instead of adding a second forwarding module:

```text
package/__main__.py -> importable domain modules
```

Current examples:

| Package | CLI | Domain modules |
|---|---|---|
| `hardware` | `src/labpulse/hardware/__main__.py` | runner, registry, drivers, publisher |
| `homeassistant` | `src/labpulse/homeassistant/generator.py` | alarm context and templates |
| `output` | `src/labpulse/output/__main__.py` | MQTT service and output driver |
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

Home Assistant SMS fragments in `src/labpulse/common/sms_templates.yaml`
receive generation-time records explicitly through `render_fragment`, for
example `render_fragment(service=service, measurement=measurement)`. They do
not inherit the surrounding template's variables. Shared identity helpers such
as `entity_id` remain available. Square-bracket expressions are expanded by
LabPulse; Home Assistant's runtime expressions remain text for evaluation later.

## Configuration ownership

Configuration is split by the concepts being validated:

- `src/labpulse/common/config.py` owns global settings, cross-references,
  source-aware errors, and the authoritative validated configuration loader;
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

The staged installation procedure is in:

```text
src/labpulse/deployment/generate.py
```

It loads one config document, renders Compose, stages every Home Assistant
artifact, and installs managed live files only after all rendering succeeds.
Replacement is atomic per file, not across the complete output set.

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
| GPIO input/output, DHT11, and X1200 | `test_gpio_input_driver.py`, `test_gpio_output_driver.py`, `test_output_mqtt_service.py`, `test_dht11_driver.py`, `test_x1200_ups_driver.py` |
| MQTT discovery/state | `test_homeassistant_publisher.py` |
| Home Assistant context/generation | `test_homeassistant_entities.py`, `test_homeassistant_generator.py` |
| Home Assistant dashboard YAML | `test_yaml_dashboard.py` |
| Power and setup alarm behavior | `test_power_monitor.py`, `test_setup_grouping.py`, `test_notification_context.py` |
| Compose and staged generation | `test_deployment_generation.py`, `test_unified_generation.py` |
| Packaging and container release | `test_packaging.py`, `test_container_release.py` |
| Fake hardware and USB mapping | `test_fake_hardware.py`, `test_simulate_serial.py`, `test_usb_setup.py` |
| SMS pipeline | `test_sms_container.py` |
| Firmware layout | `test_firmware_layout.py` |
| Documentation links and complete config examples | `test_documentation.py` |

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
for script in deployment/*.sh; do
  bash -n "$script" || exit 1
done
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

A direct driver keeps its configuration, implementation, required container
requirements function, and `DRIVER_DEFINITION` together in one module. The
function may return empty requirements when no host access is needed. See
the [hardware driver package guide](../src/labpulse/hardware/drivers/README.md).

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
- Keep `common` dependency-light and use it for shared contracts and utilities,
  including file-writing functions used by several generators.
- Centralize IDs and MQTT topics.
- Keep alarm decisions in Home Assistant.
- Use strict option models and explicit failure classes.
- Give functions and public types docstrings and type annotations.
- Make cleanup idempotent and safe after partial initialization.
- Preserve user-owned files when generation or validation fails.
- Do not hand-edit generated output as a source change.

## Documentation changes

Update the guide that owns the subject; the [documentation index](README.md#authoritative-homes)
lists those homes. Keep the procedure there and link to it elsewhere, so a
future correction only needs to be made once. Track proposed work in
[GitHub issues](https://github.com/lairdgrouplancaster/LabPulse/issues) and
document established behaviour in the guides. Do not cite private chats,
conversation titles, or task IDs, or include speculative hardware details.
Where a build needs checking, give practical verification steps.

Write for someone who knows their lab but hasn't used LabPulse before. For
each procedure, say where to run it, explain placeholders, and give the reader
a visible way to tell whether it worked. Explain an unfamiliar term where it
first matters. Keep introductory steps short and link to detail when needed.

Check commands and defaults against their implementation. Mark illustrative
output as an example, and distinguish a checked physical build from a software
configuration example. Screenshots need a readable caption and a matching
entry in [screenshot.md](../screenshot.md); don't mark a capture complete until
the real image is present.

Run `python -m pytest testing/test_documentation.py -q` after editing. It checks
maintained local links, anchors, and selected executable examples; it doesn't
verify every command, external link, screenshot, or explanation. For a changed
procedure, also follow the affected steps in a suitable development environment
and record any steps you couldn't check.

## Package and release checks

Follow [Releasing LabPulse](RELEASING.md) for candidate builds, clean installs,
version tags, publication, and partial-release recovery. It is the release
checklist; the workflow source linked there defines what CI actually runs.

## Real-Pi acceptance

Hardware-free tests cannot establish:

- GPIO/I2C/serial permissions and electrical behavior;
- USB enumeration and reconnect behavior under the Pi kernel;
- D-Bus and ModemManager integration;
- Home Assistant behavior across real host restarts;
- long-duration reliability.

Record the source revision, Pi model, OS, configuration, procedure, observed
result, and logs for real-hardware acceptance.

## Change a feature without losing its contract

Start with [the worked maintainer examples](MAINTAINER_EXAMPLES.md), then use
the [package README hierarchy](../src/labpulse/README.md) and architecture guide
to trace the existing procedure for your change.
For a new physical measurement, match firmware/driver output to its config key,
choose its unit and setup membership, then test parser/driver output and MQTT
discovery. For a calculated measurement, add inputs/constants/formula to config
and verify valid, invalid-input, and zero-denominator rendering in
`test_custom_measurements.py`.

For a dashboard change, edit the owning concrete template and only add render
model fields when data genuinely needs deriving. Check normal, shared, empty,
custom, and power setups. For an alarm change, follow helper state, derived
conditions/history, transition actions, and notification gates together; add
failure/recovery and mute/Test-mode assertions. For SMS copy, edit the shared
catalogue, pass generation-time records explicitly, preserve runtime expressions
and `{current_measurement}`, and run notification/SMS tests. Avoid scattering
one operation across helpers merely to shorten it.

For shell syntax checks, run each script separately; `bash -n deployment/*.sh`
only treats the first expansion as the script and the rest as arguments:

```bash
for script in deployment/*.sh testing/real_hardware/*.sh; do
  bash -n "$script" || exit 1
done
```

Documentation checks run with `python -m pytest testing/test_documentation.py`.
They validate maintained relative file links and complete config examples using
the real schema and generators. Fragment snippets are labelled and are not
standalone deployment files.
