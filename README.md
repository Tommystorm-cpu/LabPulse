# LabPulse

LabPulse is a Raspberry Pi monitoring platform for laboratory infrastructure.
It reads Arduino, GPIO, I2C, and simulated sensors; publishes measurements and
device health over MQTT; presents them in Home Assistant; and can deliver alarm
notifications through an SMS modem.

LabPulse is currently pre-release software. Installation is supported from a
repository checkout; it is not yet published on PyPI and released container
images are not yet available.

## How it works

Each enabled sensor service runs in its own container. A shared hardware runner
connects to the configured driver, normalizes numeric readings, and publishes
Home Assistant MQTT discovery and state. Home Assistant owns thresholds,
alarm timing, dashboards, notification muting, and alarm transitions. A
separate SMS container validates and delivers notification requests.

The live Raspberry Pi installation is generated at:

```text
~/labpulse-live/
```

The only sensor configuration that operators edit is:

```text
~/labpulse-live/config.yaml
```

The repository `config.yaml` is a starter template, not the configuration used
by an installed system.

## Quick start

Install Docker Engine with the Compose plugin, Python with virtual-environment
support, Git, and pipx. Then clone this repository and install LabPulse:

```bash
git clone https://github.com/Tommystorm-cpu/LabPulse.git
cd LabPulse
pipx install .
labpulse setup
labpulse config
labpulse up --build
labpulse doctor
labpulse open
```

For a hardware-free installation:

```bash
labpulse setup --fake-usb
cd ~/labpulse-live
./simulate_serial.py start
labpulse up --build
```

See [Installation](docs/INSTALLATION.md) for prerequisites, real-hardware
setup, development installs, and updates.

## Main commands

```text
labpulse setup       create or refresh ~/labpulse-live
labpulse config      safely edit, validate, generate, and apply config
labpulse up          start the stack
labpulse down        stop the stack without deleting persistent data
labpulse restart     restart all or selected services
labpulse ps          show container status
labpulse logs        inspect container logs
labpulse doctor      run read-only installation and runtime diagnostics
labpulse open        open Home Assistant
labpulse firmware    show firmware download information
labpulse help        show command help
```

The complete command reference is in [Operations](docs/OPERATIONS.md).

## Documentation

- [Documentation index](docs/README.md)
- [Installation](docs/INSTALLATION.md)
- [Configuration reference](docs/CONFIGURATION.md)
- [Operations](docs/OPERATIONS.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Home Assistant and alarms](docs/HOME_ASSISTANT.md)
- [SMS notifications](docs/SMS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Development](docs/DEVELOPMENT.md)
- [Adding hardware drivers](docs/DRIVER_DEVELOPMENT.md)
- [Serial protocol](docs/SERIAL_PROTOCOL.md)
- [Firmware](firmware/README.md)
- [Roadmap](ROADMAP.md)

## Repository layout

```text
config.yaml          new-install configuration template
deployment/          packaged Linux setup and generation scripts
docs/                operator and contributor documentation
firmware/            Arduino library and example device firmware
hardware/            PCB and 3D design files
src/labpulse/        Python application package
testing/             hardware-free contract and integration tests
legacy/              superseded implementations retained for reference
```

## Contributing

LabPulse welcomes fixes, documentation improvements, simulator scenarios, and
new hardware support. Read [CONTRIBUTING.md](CONTRIBUTING.md) before starting.
For sensors that can emit the standard serial protocol, new Python code is
usually unnecessary.

## Project status

The project is pre-1.0 and its public compatibility policy is still being
defined. See [ROADMAP.md](ROADMAP.md).

## Licence

LabPulse is licensed under the [MIT License](LICENSE). Unless otherwise noted,
this includes the software, firmware, documentation, PCB design files, and
mechanical design files in this repository.
