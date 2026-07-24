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

`labpulse setup` still copies package code and deployment assets into
`~/labpulse-live`. Rerun setup and rebuild after changing runtime source:

```bash
labpulse setup
labpulse up --build
```

Use fake mode for hardware-free Compose testing:

```bash
labpulse setup --fake-usb
cd ~/labpulse-live
./simulate_serial.py start
labpulse up --build
```

## Repository layout

```text
src/labpulse/common/          shared typed contracts
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
| Config, identity, MQTT contracts | `test_common_contracts.py` |
| Driver registry and options | `test_hardware_factory.py` |
| Lifecycle and retry behavior | `test_hardware_runner.py` |
| Serial protocol and driver | `test_serial_parser.py`, `test_serial_driver.py` |
| DHT11 and X1200 | `test_dht11_driver.py`, `test_x1200_ups_driver.py` |
| MQTT discovery | `test_homeassistant_publisher.py` |
| Home Assistant generation | `test_homeassistant_generator.py`, `test_yaml_dashboard.py` |
| Compose and setup | `test_deployment_generation.py`, `test_packaging.py` |
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
build validation remains roadmap work.

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

Compose and Home Assistant outputs are deterministic. Update source generators
and compare generated output through the deployment tests rather than
committing local live output.

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
- Home Assistant render models and generators;
- starter `config.yaml`;
- configuration documentation;
- validation and generated-output tests.

Do not add driver-specific fields to `ServiceConfig`; place them under
`driver.options`.

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
