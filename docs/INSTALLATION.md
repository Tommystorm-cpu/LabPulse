# Installation

LabPulse installs its operator command from PyPI with pipx and runs matching
versioned containers from GitHub Container Registry. It creates a
self-contained live deployment under `~/labpulse-live`; a repository checkout
is required only for development.

## Requirements

The verified reference host is a Raspberry Pi 5 Model B Rev 1.1 with 8 GB RAM,
running Raspberry Pi OS 64-bit based on Debian 12 (Bookworm). Its exact
software inventory, provisional platforms, and pre-1.0 boundaries are defined
in [Supported environments](SUPPORT.md).

The host needs:

- CPython 3.11 or 3.12; the reference Pi uses 3.11.2;
- Python virtual-environment support (`python3-full` on Raspberry Pi OS);
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

Operators who intentionally use Docker without sudo can add their account to
the Docker group, log out and back in, then select that command consistently:

```bash
sudo usermod -aG docker "$USER"
export LABPULSE_DOCKER_COMMAND=docker
docker run hello-world
```

Docker-group membership grants root-equivalent access to the host. Keep the
default `sudo docker` route if that is not acceptable for the installation.

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

Correct host time is required for Home Assistant history, alarm ordering and
log timestamps. Before installation, set the intended timezone and confirm NTP
synchronization:

```bash
timedatectl list-timezones
sudo timedatectl set-timezone Europe/London
sudo timedatectl set-ntp true
timedatectl status
```

Replace `Europe/London` with the deployment's actual timezone.

Do not proceed with alarm acceptance until the local time and timezone are
correct and `System clock synchronized` reports `yes`.

## Install the command

```bash
pipx install labpulse
```

This installs the unified `labpulse` command. Confirm:

```bash
labpulse help
```

## Create a real-hardware installation

```bash
labpulse setup
```

Setup:

- creates `~/labpulse-live`;
- preserves an existing live `config.yaml`;
- creates the private host `.venv`;
- installs bounded generator dependencies into that environment;
- links that environment to the exact pipx-installed LabPulse package;
- installs operational helpers;
- writes local Mosquitto configuration;
- selects the GHCR image whose tag matches the installed package version;
- generates Compose and Home Assistant YAML.

Setup does not start the stack.

Edit the live configuration with `labpulse config`. For instructions on how to properly set up your config file, see [configuration](CONFIGURATION.md).

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
labpulse up
labpulse doctor
```

Open Home Assistant:

```bash
labpulse open
```

From another computer, browse to `http://<pi-address>:8123`. On first startup,
create the Home Assistant account before evaluating LabPulse entities. Then
add the MQTT integration with:

```text
Broker: 127.0.0.1
Port: 1883
```

Home Assistant uses host networking. LabPulse Python containers deliberately
use the Compose hostname `mosquitto:1883` instead.

MQTT integration must be connected before LabPulse discovery, service health
and alarm entities are considered ready. Retained discovery messages should
then populate the dashboard without restarting sensor containers.

## First-install acceptance

Complete this check before disabling notification safeguards:

```bash
labpulse doctor
labpulse ps
labpulse logs --tail 50
```

Confirm:

1. Doctor reports no failures; resolve clock, Docker, hardware or watchdog
   warnings that apply to this deployment.
2. Every expected Compose service is running.
3. Home Assistant reports the MQTT integration as connected.
4. The Diagnostics view shows each physical service online and measurements
   continue updating.
5. Alarm Setup shows Global Mute enabled and Test mode enabled.
6. If SMS is configured, add a test recipient and use the phone-book
   notification control to verify one real test message.
7. Run `labpulse restart`, repeat `labpulse doctor`, and confirm measurements
   and service health recover without false recovery notifications.
8. Review recipients, thresholds and mute controls before deliberately
   disabling Test mode or Global Mute.

Create a complete state archive after acceptance. See
[Backup and blank-Pi reconstruction](#backup-and-blank-pi-reconstruction).

## Create a simulated installation

Fake mode derives `~/labpulse-live/config.fake.yaml` without changing the
real-hardware settings in `config.yaml`:

```bash
labpulse setup --fake-usb
cd ~/labpulse-live
./simulate_serial.py start
labpulse up
labpulse doctor
```

Fake mode converts serial services, the DHT11 room service, and the X1200 power
service to pseudo-serial endpoints while preserving service names,
measurements, and Home Assistant identities.

Always edit `config.yaml`, never `config.fake.yaml`. The guarded
`labpulse config` command detects the active fake-USB Compose mount,
regenerates `config.fake.yaml`, and keeps the deployment simulated.

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
To test runtime source changes, build a wheel and local image, select it during
generation, and start the stack:

```bash
python -m build
LABPULSE_VERSION="$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
docker build --build-arg LABPULSE_VERSION="$LABPULSE_VERSION" -t "labpulse-dev:$LABPULSE_VERSION" .
export LABPULSE_IMAGE="labpulse-dev:$LABPULSE_VERSION"
labpulse setup
labpulse up
```

See [Development](DEVELOPMENT.md).

## Updating

Update the installed release with:

```bash
pipx upgrade labpulse
labpulse setup --backup
labpulse up
labpulse doctor
```

`--backup` creates timestamped copies of package-managed files before setup
replaces them. The live `config.yaml` and existing Home Assistant configuration
directory are preserved regardless.

Review changes before updating a production Pi. A formally tested upgrade and
rollback workflow remains roadmap work.

## Backup and blank-Pi reconstruction

After first-install acceptance and before maintenance, create an archive
outside the live directory:

```bash
mkdir -p ~/labpulse-backups
labpulse backup ~/labpulse-backups/labpulse-$(date +%Y%m%d).tar.gz
```

This briefly quiesces the running services to consistently capture
`config.yaml`, complete Home Assistant configuration and private state,
Mosquitto retained data, and SMS subscription/request state. The archive is
checksummed and owner-readable only on Linux, but is not encrypted. Treat it as
a secret because it includes credentials, tokens, phone-number state, and
potentially sensitive history. Copy it to protected storage outside the Pi.

To reconstruct a blank replacement Pi:

1. install Raspberry Pi OS and the prerequisites in this document;
2. install the recorded compatible LabPulse package with pipx;
3. connect the physical hardware;
4. copy the archive onto the host;
5. run:

   ```bash
   labpulse restore /path/to/labpulse-backup.tar.gz
   ```

Restore validates the archive, recreates the live deployment in its recorded
real or fake-hardware mode, restores private state, regenerates managed files,
pulls and starts the versioned stack, waits for Home Assistant, and runs
`labpulse doctor`. If the target already contains LabPulse state, it first
creates a timestamped automatic rollback archive.

Host settings are deliberately not applied from a backup. Recheck timezone and
NTP, the systemd watchdog, Docker-group policy, modem provisioning, USB device
identities, GPIO/I2C access, and physical wiring. See
[Operations](OPERATIONS.md#back-up-and-reconstruct) for security and failure
behavior.
