# Installation

LabPulse currently installs from a Git repository checkout with pipx. It
creates a self-contained live deployment under `~/labpulse-live`; the checkout
is not the running Compose directory.

## Requirements

The verified reference host is a Raspberry Pi 5 Model B Rev 1.1 with 8 GB RAM,
running Raspberry Pi OS 64-bit based on Debian 12 (Bookworm). Its exact
software inventory, provisional platforms, and pre-1.0 boundaries are defined
in [Supported environments](SUPPORT.md).

The host needs:

- CPython 3.11 or 3.12; the reference Pi uses 3.11.2;
- Python virtual-environment support (`python3-full` on Raspberry Pi OS);
- Git;
- pipx;
- Docker Engine and the plugin-style `docker compose` command; the reference
  Pi uses Engine 29.6.1 and Compose 5.3.1;
- working network access while packages and container images are installed.

Minimum compatible Docker and Compose versions have not yet been established.
Do not use 32-bit Raspberry Pi OS. Raspberry Pi OS Lite, Raspberry Pi OS based
on Debian 13 (Trixie), Raspberry Pi 4, and other 64-bit Debian systems are
provisional until they complete release qualification.

Follow Docker's official
[Debian installation guide](https://docs.docker.com/engine/install/debian/)
and [Compose plugin guide](https://docs.docker.com/compose/install/linux/).
Verify:

```bash
sudo docker run hello-world
sudo docker compose version
```

Install pipx through the operating-system package manager where available:

```bash
sudo apt update
sudo apt install -y python3-full pipx git
pipx ensurepath
```

Start a new shell if `pipx ensurepath` changes the shell configuration. Do not
use `sudo pip`, `--break-system-packages`, or install LabPulse dependencies into
the system Python.

Real SMS delivery additionally requires ModemManager and a supported modem. See
[SMS](SMS.md).

## Install the command

```bash
git clone https://github.com/Tommystorm-cpu/LabPulse.git
cd LabPulse
pipx install .
```

This installs the unified `labpulse` command. Confirm:

```bash
labpulse help
```

LabPulse is not yet published on PyPI. `pipx install labpulse` is therefore not
currently a supported installation command.

## Create a real-hardware installation

```bash
labpulse setup
```

Setup:

- creates `~/labpulse-live`;
- preserves an existing live `config.yaml`;
- creates the private host `.venv`;
- installs bounded generator dependencies into that environment;
- copies the installed LabPulse package into the container build context;
- installs operational helpers;
- writes local Mosquitto and Docker build files;
- generates Compose and Home Assistant YAML.

Setup does not start the stack.

Edit the live configuration:

```bash
labpulse config
```

For enabled serial services, assign stable device paths with every serial
device initially connected:

```bash
cd ~/labpulse-live
./setup_usb_devices.py --config config.yaml
```

The helper asks for one device to be unplugged and reconnected at a time. It
updates only `driver.options.port` and keeps one
`config.yaml.usb-setup-backup`. Do not use `/dev/ttyUSB0` or `/dev/ttyACM0` as
permanent identities; use `/dev/serial/by-id/...`.

Apply any USB mapping and start:

```bash
labpulse config
labpulse up --build
labpulse doctor
```

Open Home Assistant:

```bash
labpulse open
```

From another computer, browse to `http://<pi-address>:8123`. On first startup,
create the Home Assistant account and add the MQTT integration with:

```text
Broker: 127.0.0.1
Port: 1883
```

Home Assistant uses host networking. LabPulse Python containers deliberately
use the Compose hostname `mosquitto:1883` instead.

## Create a simulated installation

Fake mode derives `~/labpulse-live/config.fake.yaml` without changing the
real-hardware settings in `config.yaml`:

```bash
labpulse setup --fake-usb
cd ~/labpulse-live
./simulate_serial.py start
labpulse up --build
labpulse doctor
```

Fake mode converts serial services, the DHT11 room service, and the X1200 power
service to pseudo-serial endpoints while preserving service names,
measurements, and Home Assistant identities.

Always edit `config.yaml`, never `config.fake.yaml`. The guarded
`labpulse config` command currently applies real-hardware Compose, so use a
normal editor in fake mode and rerun `labpulse setup --fake-usb` afterward.

## Alternate live directory

Every operator command accepts a global live-directory override:

```bash
labpulse --live-dir /srv/labpulse setup
labpulse --live-dir /srv/labpulse doctor
```

The `LABPULSE_LIVE_DIR` environment variable provides the same override.

## Development installation

An editable installation follows Python source changes in the checkout:

```bash
cd LabPulse
pipx install --editable . --force
```

Rerun this command after changing package metadata or console entry points.
Rerun `labpulse setup` after changing deployment assets, package code that is
copied into containers, or generated configuration behavior. Rebuild containers
with:

```bash
labpulse up --build
```

See [Development](DEVELOPMENT.md).

## Updating

Until releases exist, update from the checkout:

```bash
cd ~/LabPulse
git pull
pipx install --editable . --force
labpulse setup --backup
labpulse up --build
labpulse doctor
```

`--backup` creates timestamped copies of package-managed files before setup
replaces them. The live `config.yaml` and existing Home Assistant configuration
directory are preserved regardless.

Review changes before updating a production Pi. A formally tested upgrade and
rollback workflow remains roadmap work.

## What to back up

At minimum, retain:

- `~/labpulse-live/config.yaml`;
- the complete `~/labpulse-live/homeassistant/config/` directory;
- `~/labpulse-live/mosquitto/data/` if retained MQTT state matters;
- `~/labpulse-live/logs/sms_subscriptions.json`;
- any local credentials or modem provisioning kept outside the repository.

Do not treat the repository starter config or generated files alone as a
complete system backup.
