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
nano config.yaml
./generate_compose.sh
./generate_homeassistant_config.sh
docker compose config
docker compose up -d --build
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
`compose.yaml` and Home Assistant package/entity-map files are outputs, not
permanent editing targets.

## Source layout

```text
labpulse_common/          typed config, identity, MQTT contracts, logging
labpulse_hardware/        drivers, parsing, hardware loop, MQTT publishing
labpulse_homeassistant/   dashboard/alarm/core configuration generator
labpulse_sms/             MQTT alert subscriber and SMS delivery
testing/                  script-based contract tests
docs/                     the four maintained guides
```

Home Assistant owns alarm decisions and operator settings. Hardware services
publish readings and health; the SMS worker delivers validated requests.
