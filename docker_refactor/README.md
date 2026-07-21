# LabPulse Docker Runtime

This is the active Docker-based LabPulse implementation for Raspberry Pi. It
runs Home Assistant, Mosquitto, one SMS worker, and one Python container per
enabled sensor service.

The complete documentation has four reference guides and one roadmap:

1. [Architecture](docs/ARCHITECTURE.md)
2. [Code internals](docs/CODE_INTERNALS.md)
3. [Setup and troubleshooting](docs/SETUP_AND_TROUBLESHOOTING.md)
4. [Arduino and C++ notes](docs/ARDUINO_AND_CPP.md)
5. [Software roadmap](docs/SOFTWARE_TODO.md)

The [documentation index](docs/README.md) explains which guide answers each
type of question.

## Quick start

Real hardware:

```bash
cd ~/LabPulse/docker_refactor
./setup_container_fs.sh

cd ~/labpulse-ha
./edit_config.sh
```

Fake hardware:

```bash
cd ~/LabPulse/docker_refactor
./setup_container_fs.sh -fake_usb

cd ~/labpulse-ha
python3 simulate_serial.py start
docker compose up -d --build
```

The running Pi is configured through:

```text
~/labpulse-ha/config.yaml
```

The repository `config.yaml` is only a new-install starter. Generated
`compose.yaml`, Home Assistant package, and dashboard files are outputs, not
permanent editing targets.

`edit_config.sh` opens a temporary copy of the live config, validates it, keeps
one rollback copy, regenerates Compose and Home Assistant YAML, runs Home
Assistant's config check, and refreshes the stack through `sudo docker`.

## Source layout

```text
labpulse_common/          typed config, identity, MQTT contracts, logging
labpulse_hardware/        drivers, parsing, hardware loop, MQTT publishing
labpulse_homeassistant/   dashboard/alarm/core configuration generator
labpulse_sms/             MQTT alert subscriber and SMS delivery
firmware/                 simple pipe-delimited Arduino sketches
testing/                  script-based contract tests
docs/                     the four maintained guides
```

Home Assistant owns alarm decisions and operator settings. Hardware services
publish measurements and health; the SMS worker delivers validated requests.
