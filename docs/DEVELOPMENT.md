# Development

## Requirements

Development requires:

- CPython 3.11 or 3.12 for the supported package test matrix;
- Git;
- pipx for exercising the installed CLI;
- Docker and Compose for generated deployment tests or Pi operation;
- Bash for checking and running deployment scripts;
- no physical hardware for the ordinary test suite.

Python 3.13 and newer may be used experimentally, but are provisional until
they are included in automated package tests. Development may take place on
Windows or another desktop operating system; only the Raspberry Pi deployment
environment in [Supported environments](SUPPORT.md) is a supported runtime.

## Editable installation

From the repository root:

```bash
pipx install --editable . --force
labpulse help
```

Python source changes are then visible to the pipx command. Reinstall after
changing `pyproject.toml`, console entry points, or environment dependencies.

`labpulse setup` installs deployment assets and links the managed generator
environment to the editable pipx package. Runtime services still use an image,
so build and select a local image after changing runtime source:

```bash
python -m pip install setuptools-scm
LABPULSE_VERSION="$(python -m setuptools_scm)"
python -m build
docker build --build-arg LABPULSE_VERSION="$LABPULSE_VERSION" -t "labpulse-dev:$LABPULSE_VERSION" .
export LABPULSE_IMAGE="labpulse-dev:$LABPULSE_VERSION"
labpulse setup
labpulse up
```

Use fake mode for hardware-free Compose testing:

```bash
labpulse setup --fake-usb
cd ~/labpulse-live
./simulate_serial.py start
labpulse up
```

## Repository layout

```text
src/labpulse/common/          shared typed contracts
src/labpulse/deployment/      Compose and unified output generation
src/labpulse/hardware/        hardware acquisition runtime
src/labpulse/homeassistant/   Home Assistant generator
src/labpulse/sms/             notification delivery
deployment/                   packaged Linux workflows
firmware/                     Arduino library and examples
testing/                      executable hardware-free tests
docs/                         maintained product documentation
legacy/                       superseded reference material
```

## Running tests

Tests are currently standalone Python scripts rather than pytest discovery.
Run one:

```bash
python testing/test_hardware_runner.py
```

Run every hardware-free test on Bash:

```bash
for test in testing/test_*.py; do
  python "$test" || exit 1
done
```

On PowerShell:

```powershell
$tests = Get-ChildItem testing -File -Filter 'test_*.py' | Sort-Object Name
foreach ($test in $tests) {
    python $test.FullName
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

Important focused suites:

| Area | Tests |
|---|---|
| Config pipeline, identity, MQTT contracts | `test_config_pipeline.py`, `test_common_contracts.py` |
| Driver registry and options | `test_hardware_factory.py` |
| Lifecycle and retry behavior | `test_hardware_runner.py` |
| Serial protocol and driver | `test_serial_parser.py`, `test_serial_driver.py` |
| DHT11 and X1200 | `test_dht11_driver.py`, `test_x1200_ups_driver.py` |
| MQTT discovery | `test_homeassistant_publisher.py` |
| Home Assistant generation | `test_homeassistant_generator.py`, `test_yaml_dashboard.py` |
| Compose, atomic generation, and setup | `test_deployment_generation.py`, `test_unified_generation.py`, `test_packaging.py` |
| Fake hardware | `test_simulate_serial.py`, `test_usb_setup.py` |
| SMS | `test_sms_container.py` |

Simulated failures intentionally produce warning/error log lines.

## Package checks

Metadata is defined in `pyproject.toml`. Core host dependencies are bounded;
hardware-specific extras are:

```text
labpulse[serial]
labpulse[dht11]
labpulse[x1200]
labpulse[dev]
```

When the build frontend is installed:

```bash
python -m build
```

Before a release, install the wheel and source distribution into clean
environments and verify console entry points and package data. Automated clean
build validation also runs in the release workflow.

## Release process

The Git tag is the single source of the released version. Update the changelog,
run the full hardware-free suite, and push the release commit before creating a
GitHub Release whose tag is `vVERSION`. Do not add a version string to
`pyproject.toml` or `src/labpulse/__init__.py`.

`setuptools-scm` derives the wheel, source-distribution, and installed runtime
version from that tag. The release workflow checks out the exact tag, verifies
the derived version, builds and clean-installs the distributions, smoke-tests
the container, publishes the Python artifacts through TestPyPI Trusted
Publishing, and publishes attested
`linux/amd64` and `linux/arm64` images to GHCR. It publishes immutable full and
major/minor image tags, but no floating `latest` tag.

Between tags, development builds receive an informative version such as
`0.1.2.dev3+g904105e` rather than claiming to be a released build.

TestPyPI Trusted Publishing is a one-time external prerequisite. Configure the
`Tommystorm-cpu/LabPulse` repository, workflow
`.github/workflows/release.yml`, and GitHub environment `testpypi` as the
publisher for the `labpulse` project on TestPyPI. Production PyPI publishing
remains disabled until the release process is deliberately promoted.

Never reuse a released version or move its tag. Correct a release with a new
patch version.

## Deployment development

Source scripts live under `deployment/`. Setup installs the operational
wrappers flat into `~/labpulse-live`.

Check shell syntax:

```bash
bash -n deployment/*.sh
```

Do not run the setup script on a development machine unless creating a real
Linux test installation is intended. It writes a live directory, creates a
virtual environment, and may invoke Docker workflows.

Compose rendering lives in `src/labpulse/deployment/compose.py`; the shell
script is a thin launcher for `python -m labpulse.deployment`. Supplying
`--ha-config-dir` makes that entry point stage Compose and Home Assistant
outputs from one configuration load. Setup and guarded editing use this unified
mode.

Compose and Home Assistant outputs are deterministic. Home Assistant uses
strict Jinja templates with `[% ... %]` generator blocks and `[[ ... ]]`
generator values, leaving Home Assistant's `{% ... %}` and `{{ ... }}` intact.
Update the final-shaped templates directly and compare generated output through
the deployment tests rather than committing local live output. Large documents
are assembled from shallow, feature-named includes; keep those includes tied to
concrete dashboard or alarm behavior instead of introducing generic card,
entity, or automation macros.

## Code organization

- Put behavior in its owning package.
- Keep `common` small and dependency-light.
- Import optional hardware libraries only when connecting.
- Keep identity and MQTT topics centralized.
- Keep alarm decisions in Home Assistant.
- Give functions and public types docstrings and type annotations.
- Prefer injectable clocks, command runners, sockets, or fake buses for tests.
- Keep cleanup idempotent.

## Configuration changes

Configuration changes affect multiple consumers. Update:

- `src/labpulse/common/config.py`;
- relevant driver options;
- Compose generation;
- Home Assistant context calculations and final-shaped YAML templates;
- starter `config.yaml`;
- configuration documentation;
- validation and generated-output tests.

Do not add driver-specific fields to `ServiceConfig`; place them under
`driver.options`. The central loader must return the driver's typed options;
consumers must not call the driver option model again or read raw YAML.

## Documentation changes

Document current behavior, not the chronology of implementation. Update the
smallest authoritative guide:

- operator task → Installation, Configuration, Operations, or Troubleshooting;
- subsystem behavior → Home Assistant or SMS;
- cross-component contract → Architecture or Serial Protocol;
- contribution workflow → Development or Driver Development;
- future work → Roadmap.

Avoid creating new `*_REFACTOR.md`, `*_IMPLEMENTATION.md`, or duplicate to-do
documents.

## Real-Pi acceptance

Hardware-free tests cannot prove:

- device permissions and GPIO/I2C behavior;
- USB reconnect behavior under the Pi kernel;
- modem and D-Bus integration;
- Home Assistant behavior across real restarts;
- long-duration reliability.

Record the revision, Pi model, OS, configuration, procedure, observed result,
and logs for real-hardware checks. Open roadmap items remain incomplete until
their required real-Pi evidence exists.
