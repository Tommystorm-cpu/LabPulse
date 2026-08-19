# LabPulse

LabPulse is a Raspberry Pi monitoring platform for laboratory infrastructure.
It reads Arduino serial, GPIO, I2C, and simulated sensors; publishes numeric
measurements and service health over MQTT; generates a Home Assistant dashboard
and alarm package; and can deliver notification requests through an SMS modem.

LabPulse is a monitoring and best-effort alerting aid. It is not a safety-rated
controller, protective interlock, emergency shutdown system, or guaranteed
notification channel. See [Product scope and safety boundary](docs/PRODUCT_SCOPE.md).

## Current system

An installed deployment contains:

```text
Raspberry Pi host
  ~/labpulse-live/config.yaml         operator-owned source of truth
  ~/labpulse-live/compose.yaml        generated deployment

Docker Compose
  homeassistant
  mosquitto
  labpulse-sms
  labpulse-<service>                  one per enabled sensor service
```

Each hardware container selects one configured driver, normalizes readings,
and publishes MQTT discovery, state, and health. Home Assistant owns threshold
interpretation, alarm timing, persistent alarm state, dashboard presentation,
mutes, Test mode, and notification creation. The SMS worker independently
validates, routes, deduplicates, queues, and delivers requests.

The repository `config.yaml` is a new-install template. An installed Pi always
uses:

```text
~/labpulse-live/config.yaml
```

## Install

The current published release is `0.1.1` on TestPyPI with a matching public
runtime image on GHCR:

```bash
pipx install \
  --index-url https://test.pypi.org/simple/ \
  --pip-args="--extra-index-url https://pypi.org/simple/" \
  "labpulse==0.1.1"

labpulse version
labpulse setup
labpulse config
labpulse up
labpulse doctor
labpulse open
```

For a hardware-free deployment:

```bash
labpulse setup --fake-usb
cd ~/labpulse-live
./simulate_serial.py start
labpulse up
labpulse doctor
```

See [Installation](docs/INSTALLATION.md) for prerequisites, real hardware,
Home Assistant onboarding, updates, and backup acceptance.

## Operator commands

```text
labpulse setup       create or refresh the live installation
labpulse config      edit, validate, generate, check, and apply configuration
labpulse up          start all or selected services
labpulse down        stop containers without deleting persistent state
labpulse restart     restart all or selected services
labpulse ps          show container status
labpulse logs        inspect container output
labpulse doctor      run read-only host and deployment diagnostics
labpulse backup      create a checksummed state archive
labpulse restore     reconstruct an installation from an archive
labpulse open        open Home Assistant
labpulse version     show the installed package version
labpulse firmware    show firmware source/download information
labpulse help        show general or command-specific help
```

Use `labpulse help COMMAND` for exact syntax. See
[Operations](docs/OPERATIONS.md) for workflow details.

## Code organization

```text
src/labpulse/
  control.py         operator CLI and installed workflows
  installer.py       setup asset launcher
  backup.py          backup and restore primitives
  doctor.py          read-only diagnostics
  common/            validated config, stable IDs, MQTT contracts
  deployment/        Compose rendering and atomic unified generation
  hardware/          driver API, registry, runner, parser, MQTT publisher
  homeassistant/     CLI, render context, generators, YAML templates
  sms/               CLI, subscriber, delivery, subscriptions

deployment/          packaged Linux setup/config workflow scripts
testing/             hardware-free contract and integration tests
firmware/            Arduino library and device examples
hardware/            PCB and enclosure assets
docs/                current operator and contributor documentation
```

Standalone process packages use `__main__.py → cli.py → domain modules`. The
complete ownership and data-flow description is in
[Architecture](docs/ARCHITECTURE.md).

## Documentation

- [Documentation index](docs/README.md)
- [Installation](docs/INSTALLATION.md)
- [Configuration](docs/CONFIGURATION.md)
- [Operations](docs/OPERATIONS.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Home Assistant and alarms](docs/HOME_ASSISTANT.md)
- [SMS notifications](docs/SMS.md)
- [Supported environments](docs/SUPPORT.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Development](docs/DEVELOPMENT.md)
- [Driver development](docs/DRIVER_DEVELOPMENT.md)
- [Serial protocol](docs/SERIAL_PROTOCOL.md)
- [Firmware](firmware/README.md)
- [Roadmap](ROADMAP.md)

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before changing code. New sensors that
can emit the standard pipe-delimited serial protocol usually require firmware,
configuration, and tests rather than a new Python driver.

## Licence

LabPulse is licensed under the [MIT License](LICENSE). Unless otherwise noted,
this includes the software, firmware, documentation, PCB design files, and
mechanical design files in this repository.
