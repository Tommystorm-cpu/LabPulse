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

Install from a repository checkout with pipx:

```bash
cd ~/LabPulse
pipx install .
labpulse-setup

labpulse edit
labpulse up --build
```

Once LabPulse is published, `pipx install labpulse` replaces `pipx install .`.
Pipx owns the command environment; `labpulse-setup` creates or refreshes the
live deployment without replacing an existing live `config.yaml`.

Fake hardware installation:

```bash
cd ~/LabPulse
pipx install .
labpulse-setup -fake_usb

cd ~/labpulse-live
./simulate_serial.py start
labpulse up --build
```

For active development, use `pipx install --editable . --force` so the
installed setup command follows the checkout.

The running Pi is configured through:

```text
~/labpulse-live/config.yaml
```

The repository `config.yaml` is only a new-install starter. Generated
`compose.yaml`, Home Assistant package, and dashboard files are outputs, not
permanent editing targets.

The packaged operator commands are:

```bash
labpulse up                       # start the complete stack
labpulse up --build               # rebuild local images, then start
labpulse down                     # stop without deleting persistent data
labpulse ps                       # show container status
labpulse logs                     # show all logs
labpulse logs -f homeassistant    # follow one service
labpulse edit                     # safely edit, validate, and apply config
labpulse open                     # open Home Assistant in the default browser
```

Standalone aliases (`labpulse-up`, `labpulse-down`, `labpulse-ps`,
`labpulse-logs`, `labpulse-edit`, and `labpulse-open`) are also installed for
shell users who prefer them. `labpulse edit` opens a temporary copy of the live config,
validates it, keeps one rollback copy, regenerates Compose and Home Assistant
YAML, runs Home Assistant's config check, and refreshes the stack through
Docker.
Setup also creates `~/labpulse-live/.venv` and installs the bounded host tooling
dependencies there. LabPulse commands select that interpreter automatically;
users should not install Pydantic globally or activate the environment.

## Source layout

```text
src/labpulse/common/          typed config, identity, MQTT contracts, logging
src/labpulse/hardware/        driver contracts, central lifecycle, parsing, MQTT publishing
src/labpulse/homeassistant/   dashboard/alarm/core configuration generator
src/labpulse/sms/             MQTT alert subscriber and SMS delivery
firmware/                     simple pipe-delimited Arduino sketches
hardware/                     PCB and 3D-printing assets
testing/                      script-based contract tests
docs/                         maintained reference guides
legacy/                       superseded implementations and documentation
```

Home Assistant owns alarm decisions and operator settings. Hardware services
publish measurements and health; the SMS worker delivers validated requests.
