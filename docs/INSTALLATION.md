# Installation

LabPulse installs its operator command from TestPyPI with pipx and runs a
matching versioned container image from GitHub Container Registry. It creates
a self-contained live deployment under `~/labpulse-live`; a repository
checkout is required only for development.

## Distribution

The commands below retain `0.1.1` as a **historical pinned distribution
example**, not a claim that it is the latest release or contains all features
in this checkout. Select a published package and matching GHCR image for your
installation, then use that version consistently. Confirm availability in the
project's release records before installation. For current working-source
features, use the [development installation](#development-installation).
Install published packages from TestPyPI with the production PyPI index
available for dependencies. The required command is in
[Install the command](#install-the-command).

For that pinned example, the expected runtime image name is:

```text
ghcr.io/tommystorm-cpu/labpulse:0.1.1
```

Public distributions do not require a repository checkout or local container
build. Registry visibility and package availability must be verified for the
version selected; a Git tag alone is not proof of successful publication.

## Requirements

The verified reference host is a Raspberry Pi 5 Model B Rev 1.1 with 8 GB RAM,
running Raspberry Pi OS 64-bit based on Debian 12 (Bookworm). Other Raspberry
Pi models and 64-bit Debian releases remain provisional until they complete the
same installation, restart, hardware, alarm, SMS, and recovery checks.

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
[SMS behaviour](USER_GUIDE.md#sms-behaviour).

Check the [hardware guide](HARDWARE.md) before connecting physical devices.
Enable required interfaces and confirm pin allocations before starting workers.

Correct host time is required for Home Assistant history, alarm ordering and
log timestamps. Before installation, set the intended timezone and confirm NTP
synchronization:

```bash
timedatectl list-timezones
sudo timedatectl set-timezone Europe/London
sudo timedatectl set-ntp true
timedatectl status
```

Replace `Europe/London` with the deployment's actual timezone. The current
Compose generator also hard-codes Home Assistant `TZ: Europe/London`; there is
no YAML timezone setting. A non-London deployment needs that implementation
limitation resolved and Home Assistant's timezone checked explicitly.

Do not proceed with alarm acceptance until the local time and timezone are
correct and `System clock synchronized` reports `yes`.

## Install the command

```bash
pipx install \
  --index-url https://test.pypi.org/simple/ \
  --pip-args="--extra-index-url https://pypi.org/simple/" \
  "labpulse==0.1.1"
```

The arguments are currently necessary:

- `--index-url https://test.pypi.org/simple/` tells pipx to obtain LabPulse
  from TestPyPI;
- `--pip-args="--extra-index-url https://pypi.org/simple/"` allows pip to
  obtain LabPulse's ordinary dependencies from production PyPI, because
  TestPyPI is not a dependency mirror;
- `"labpulse==0.1.1"` pins the historical example; replace the version with
  the published release you have chosen.

This installs the unified `labpulse` command into a user-owned isolated
environment; administrator rights are not required. Confirm the installed
release:

```bash
labpulse version
labpulse help
```

Expected version output:

```text
LabPulse 0.1.1
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

Edit the live configuration with `labpulse config`. The complete schema and
built-in driver examples are in the
[Configuration reference](CONFIGURATION.md).

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
4. The System Status view shows each physical service working and measurements
   continue updating.
5. On first installation, Alarm Setup shows Global Mute enabled and Test mode
   enabled. Later restarts restore the global mute choice but reset Test mode on.
6. If SMS is configured, follow the [SMS acceptance procedure](USER_GUIDE.md#sms-behaviour)
   to deliberately test a reviewed recipient; dry-run never sends a real message.
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

With the starter config, fake mode converts the known serial placeholders,
`room_environment` DHT11/SHT40, and the power service to pseudo-serial endpoints.
It does not convert arbitrary hardware configurations. Inspect the
[exact substitutions](CONFIGURATION.md#fake-configuration) when adapting a lab.
This walkthrough requires a supported Linux host, but no physical sensors,
modem, or outputs. It is not a Windows-native simulator.

Always edit `config.yaml`, never `config.fake.yaml`. The guarded
`labpulse config` command detects the active fake-USB Compose mount,
regenerates `config.fake.yaml`, and keeps the deployment simulated.

After starting the simulated stack, complete the same Home Assistant account
and MQTT onboarding as the real path. Keep SMS dry-run enabled. Confirm the
pressure reading changes, then follow
[simulation controls](USER_GUIDE.md#choose-real-hardware-or-simulation)
to exercise stale/danger/recovery states. These validate the software path,
not physical wiring. Restart the simulator after a host reboot before expecting
its pseudo-terminal paths to exist. Setup does not install a simulator boot service.

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
python -m pip install setuptools-scm
LABPULSE_VERSION="$(python -m setuptools_scm)"
python -m build
docker build --build-arg LABPULSE_VERSION="$LABPULSE_VERSION" -t "labpulse-dev:$LABPULSE_VERSION" .
export LABPULSE_IMAGE="labpulse-dev:$LABPULSE_VERSION"
labpulse setup
labpulse up
```

See [Development](DEVELOPMENT.md).

## Updating

Update to the latest LabPulse version published on TestPyPI:

```bash
labpulse update
```

If that version is already installed, the command exits without changing the
installation or restarting containers. To select a specific release instead:

```bash
labpulse update 0.1.1
```

Every LabPulse command performs a quick, best-effort check for a newer release
after it finishes. The TestPyPI result is cached for six hours, so normal
commands do not wait for the network each time. When an update is available,
the cached result still prints the installed and available versions and suggests
`labpulse update`. A failed check is silent and cached for ten minutes, so normal
operation remains responsive when the Pi is offline or TestPyPI is unavailable.
The `labpulse update` command always fetches fresh release metadata.

Update resolves the latest version from TestPyPI only, installs that exact
version with pipx using fresh package-index metadata, refreshes package-managed
deployment assets with backups, preserves the active real-hardware or fake-USB
mode, pulls images, and recreates every container. During that planned outage
it publishes a retained maintenance request before recreating runtime services.
Home Assistant applies maintenance and publishes an acknowledgement with the
same request ID; update does not stop SMS or disrupt any container until that
acknowledgement arrives. It then stops the SMS worker. Every notification
path is gated before an SMS MQTT request can be queued. Update waits only for
fresh required physical readings, lets classification settle, then clears
maintenance and verifies the matching acknowledgement before starting SMS and
running `labpulse doctor` through the newly installed command.

If maintenance acknowledgement or required fresh telemetry does not arrive
within two minutes, update exits with SMS delivery stopped and update
maintenance active instead of risking a notification flood. Repair the
reported service or required reading, confirm telemetry is current, then run
`labpulse up labpulse-sms`; that command clears maintenance with the same
acknowledged handshake before resuming delivery.

`--backup` creates timestamped copies of package-managed files before setup
replaces them. The live `config.yaml` and existing Home Assistant configuration
directory are preserved by the update workflow.

Create a state backup and review the release notes before updating an installed
Pi.

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
identities, GPIO/I2C access, and physical wiring. The archive and failure
behaviour are explained in the [User Guide](USER_GUIDE.md#backup-and-restoration).

## Troubleshooting

Start with these read-only or observational commands:

```bash
labpulse doctor
labpulse ps --all
labpulse logs --tail 100
```

Follow the system in order: host hardware, service container, Mosquitto, Home
Assistant entity, alarm automation, then SMS delivery. Confirm the last
working boundary before changing the next one. Do not alter several layers at
once.

### pipx cannot find or install LabPulse

The release workflow publishes LabPulse to TestPyPI rather than production
PyPI. Use the complete pinned command from [Install the command](#install-the-command),
including production PyPI as the dependency index. Confirm the selected
version exists and then run `labpulse version`. Do not use `sudo pip` or
`--break-system-packages` to bypass installation errors.

If the command is not found after installation, open a new shell after
`pipx ensurepath`, inspect `pipx list`, and ensure the pipx binary directory is
on `PATH`.

### Installation or generated files are missing

If `compose.yaml` or the live directory is missing, run:

```bash
labpulse setup
```

For a non-default directory, put the global option before the action:

```bash
labpulse --live-dir /path/to/live setup
```

If generated files are damaged but the source config is valid, rerun setup or
`labpulse config`. Do not reconstruct them by hand. Setup preserves the live
source and Home Assistant directory; `--backup` also retains timestamped copies
of package-managed files.

### Docker cannot run

Check the service and plugin-style Compose command:

```bash
sudo systemctl status docker
sudo docker version
sudo docker compose version
```

LabPulse normally selects `sudo docker` for a non-root Linux user. If the
operator intentionally uses Docker-group access, export
`LABPULSE_DOCKER_COMMAND=docker` consistently. A permission-denied response is
a host Docker policy problem, not a sensor problem.

### Host clock is not synchronized

Incorrect time makes history, alarm ordering and logs misleading. Inspect
`timedatectl status`, select the deployment timezone and enable NTP. Do not
accept alarm timestamps until `System clock synchronized` reports `yes`.
The generated Home Assistant container currently also has a known
`Europe/London` timezone limitation.

### Configuration is rejected

Use `labpulse config` so errors include the source path and field location.
Check YAML indentation, required labels and measurements, exact registered
driver IDs, option spelling, setup references, stable lowercase IDs, timing
ranges and international-format SMS numbers. Unknown fields are rejected.

Use every mapping key once. The current YAML loader accepts duplicate keys and
the later value can hide the earlier one before model validation.

### Containers exit or restart repeatedly

Inspect the selected service rather than the entire stack:

```bash
labpulse ps --all
labpulse logs --tail 100 labpulse-pressure-monitor
```

Common causes are a config mounted from the wrong mode, missing host devices,
incorrect driver options, Docker permissions or an unavailable MQTT broker.
Compare `compose.yaml` with `config.yaml` (or generated `config.fake.yaml`) and
run Doctor before editing code.

### MQTT connection is refused

The generated broker is reachable from LabPulse containers as
`mosquitto:1883`. Home Assistant uses host networking and connects to
`127.0.0.1:1883`. Check `labpulse-mqtt` logs, port 1883 in Doctor, and the Home
Assistant MQTT integration. `localhost` inside a sensor container refers to
that container, not Mosquitto.

### A real serial device is missing

Confirm the stable device exists on the host and inside the generated worker:

```bash
ls -l /dev/serial/by-id/
labpulse doctor
```

Close Arduino serial monitors that may own the port. Rerun
`~/labpulse-live/setup_usb_devices.py --config config.yaml` if boards were
replaced or identities changed, then apply with `labpulse config`. Do not make
`/dev/ttyUSB0` or `/dev/ttyACM0` the permanent identity.

### Fake serial readings do not appear

Fake setup creates configuration and mounts but does not start the simulator.
Run:

```bash
cd ~/labpulse-live
./simulate_serial.py start
./simulate_serial.py status
labpulse restart
```

Verify the configured endpoint names and `/tmp/labpulse-fake-serial` paths.
The simulator must be restarted after a host reboot. It does not cover arbitrary
renamed services or every driver.

### Serial data repeatedly reconnects or becomes stale

Inspect raw Arduino output at the configured baud rate only after stopping the
worker that owns the port. Each line must terminate with a newline and contain
at least one usable `name:value` field. Names must match configured measurement
keys. Look for empty output, `null` channels, malformed fields, firmware resets,
USB power problems and a read interval longer than the maximum measurement age.

### GPIO input or output is unavailable

Confirm the configured `/dev/gpiochipN` exists, the line offset is correct and
no other process owns the line. Physical header pins and Linux line offsets are
not interchangeable. Pi GPIO uses 0 V/3.3 V; never drive it with a higher
voltage.

An input publishes numeric 0/1 and does not debounce or count pulses. For an
output, check availability, command logs, polarity and safe-state configuration.
Latch readback proves only the Pi line. Check the custom interface and equipment
feedback separately.

### DHT11, SHT40 or X1200 is unavailable

For DHT11, confirm the Blinka pin name, wiring and container privilege. A few
timing errors can be transient; sustained errors indicate hardware access or
sensor trouble.

For SHT40, confirm I2C is enabled, `/dev/i2c-<bus>` exists, the configured
address is present and no other service is using the device incorrectly. CRC
failures indicate corrupt or incomplete transfers.

For X1200, check both I2C battery telemetry and the configured mains GPIO.
GPIO-only failure can leave voltage/charge available while reporting a power
component fault. Confirm polarity against the installed board revision rather
than changing alarm logic to hide an inverted signal.

### A named MQTT or calculated measurement is unavailable

For named MQTT input, verify broker/topic agreement, protocol/version,
`recorded_at`, exact case-sensitive external field names and record age. The
external publisher and local-only generated broker need separately provisioned
network/TLS access.

For a calculated measurement, inspect every physical input entity. Inputs must
be numeric and available and every divisor non-zero. Calculations cannot depend
on other calculated measurements. Fix the physical source or formula rather
than forcing an available result.

### A Home Assistant entity or dashboard is missing

Confirm MQTT is connected, the corresponding service is enabled and publishing,
and discovery topics have arrived. Restart the affected worker after MQTT
onboarding if necessary. Run `labpulse config` to regenerate a stale dashboard;
do not edit generated dashboard YAML or `.storage` as the source fix.

Unexpected units and icons come from the measurement's exact configured `unit`,
`device_class` and optional `icon`. LabPulse intentionally does not request
Home Assistant unit conversion.

### An alarm does not trigger or recover

Check that the measurement is alarmed, its threshold includes the observed
value, enough observations satisfy the danger proportion/window, and Test mode
or mutes have not been confused with alarm state. Recovery requires continuous
safe data beyond the deadband for the complete recovery time.

Missing required data has its own confirmation delay. A complete service outage
suppresses subordinate reading incidents. Measurements configured with
`required: false` are deliberately silent when their data is absent.
Inspect Alarm Setup and the User Guide's
[alarm behaviour](USER_GUIDE.md#measurement-alarm-behaviour).

### Alarm state changes but no SMS is received

Check Global Mute, the relevant setup mute, Test mode, normal versus test
recipient lists, `sms.dry_run`, `labpulse-sms` logs and the per-request result.
In dry-run mode no real SMS is expected. For real delivery, confirm
ModemManager sees the modem and the configured recipient has not unsubscribed.
Modem acceptance is not proof of handset delivery.

### Configuration was accepted but containers did not refresh

`labpulse config` can successfully install configuration and then encounter an
external Docker recreation failure. Run `labpulse ps --all`, inspect Compose
and Home Assistant logs, and rerun `labpulse up` after correcting Docker or
hardware access. The prior source is rolled back for validation/check failures,
but no workflow can make several filesystem and daemon operations one atomic
transaction.

### Backup or restore fails

Keep archives outside the live directory and ensure the destination does not
already exist unless `--force` is intentional. A restore validates member
paths, types and checksums; do not bypass an archive rejection. Confirm enough
disk space and permissions for the live directory and rollback archive.

If restore reports that Home Assistant did not become ready, the state may
already have been restored. Inspect container status and logs before repeating
the operation. Preserve the automatic pre-restore archive. Host packages,
timezone, interfaces, modem and wiring still require manual reconstruction.

### Asking for help

Record the Pi model, operating system and architecture, Python version, Docker
and Compose versions, LabPulse version, enabled driver IDs, runtime mode,
`labpulse doctor` output and relevant logs. Remove credentials, tokens, phone
numbers and private network details before sharing them.
