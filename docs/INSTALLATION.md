# LabPulse Installation Guide

This guide takes you from a Raspberry Pi to a working LabPulse
dashboard. You can start with simulated readings or connect real sensors.
Both use the same configuration and Home Assistant interface.

New to LabPulse? Read [What you're installing](FIRST_STEPS.md#what-youre-installing)
first. It explains the pieces and the terms used here.

LabPulse installs with pipx and runs its services in Docker containers. You do
not need a repository checkout or a local container build. For everyday use
after installation, read the [User Guide](USER_GUIDE.md).

## Contents

- [Requirements](#requirements)
- [Get onto the Pi](#get-onto-the-pi)
- [Prepare the Pi](#prepare-the-pi)
- [Install LabPulse](#install-labpulse)
- [Create a simulated installation](#create-a-simulated-installation)
- [Create a real-hardware installation](#create-a-real-hardware-installation)
- [Open Home Assistant](#open-home-assistant)
- [Check the installation](#check-the-installation)
- [Changing the configuration](#changing-the-configuration)
- [Switching between simulated and real hardware](#switching-between-simulated-and-real-hardware)
- [Updating](#updating)
- [Backups and restoring on a new Pi](#backups-and-restoring-on-a-new-pi)
- [Troubleshooting](#troubleshooting)

## Requirements

The reference system is a Raspberry Pi 5 with 8 GB RAM, running 64-bit
Raspberry Pi OS based on Debian 12 (Bookworm). LabPulse's automated tests cover
Python 3.11 and 3.12. Other Pi models and operating-system versions need their
own deployment checks; 32-bit Raspberry Pi OS is not supported by the published
runtime images.

You will need:

- a Pi, a suitable power supply, and storage for its operating system;
- a working network connection and an account which can use `sudo`;
- Python, pipx, Docker Engine, and the Docker Compose plugin;
- a browser on the Pi or another computer on the same trusted network;
- for real hardware, the connected sensors and their wiring details.

Simulation needs no sensors, modem, or output hardware. Real SMS delivery
additionally needs a supported modem, an active SIM, and ModemManager on the
Pi. Review the [hardware guide](HARDWARE.md) before wiring physical devices.

## Get onto the Pi

If the Pi already runs the OS described above and you can open its terminal,
skip to [Prepare the Pi](#prepare-the-pi).

### Install the operating system

For a fresh installation, you'll also need another computer and a way to
write the Pi's storage, such as a microSD card reader.

**On your own computer**, follow Raspberry Pi's
[getting-started instructions](https://www.raspberrypi.com/documentation/computers/getting-started.html)
to write Raspberry Pi OS to the Pi's storage using Raspberry Pi Imager. Choose
the 64-bit Bookworm version used by the reference setup, rather than assuming
the latest default is the same version. Writing an image erases the selected
storage, so check which card or drive you've selected.

In Imager, set a hostname, create your user account, and configure the network.
Enable SSH if you want to use the Pi from another computer. Keep a note of
the username and hostname you chose. Boot the Pi and let it join the network.

### Open a terminal

With a keyboard and screen attached to the Pi, open **Terminal** on its
desktop. A terminal is the window where you type commands and read their
results. On a Lite installation, log in at the text prompt instead.

For remote access, open PowerShell on Windows or Terminal on macOS/Linux
**on your own computer**. Connect using your Pi's username and hostname:

```bash
ssh YOUR_USERNAME@YOUR_HOSTNAME.local
```

Replace both uppercase placeholders; don't type them literally. For example,
an account named `alex` on a Pi named `labpulse-pi` uses
`ssh alex@labpulse-pi.local`. Check that the address is your Pi before accepting
its first connection prompt. If using password login, the password won't show
as you type. After login, commands in this window run on the Pi.

If the hostname doesn't connect, use the Pi's IP address instead. You can find
it in your router's device list or by running `hostname -I` in a terminal on
the Pi. Raspberry Pi's [remote-access guide](https://www.raspberrypi.com/documentation/computers/remote-access.html)
has more help with addresses and SSH.

### Which computer do I use?

| Task | Where to do it |
|---|---|
| Install LabPulse or run a `labpulse` command | The Pi's terminal, either directly or through SSH |
| View readings and change alarms | A browser on your own computer or on the Pi |
| Upload Arduino firmware | The computer with the Arduino connected by USB |

In command examples, copy the commands without the surrounding code fences.
`sudo` asks to run a command with administrator privileges; `~` means your
user's home directory. Run commands one at a time and check for errors before
moving on.

## Prepare the Pi

Run these commands in a terminal on the Pi, either locally or over SSH. Use
your usual user account for installation and later LabPulse commands.

Install the Python tools and a text editor:

```bash
sudo apt update
sudo apt install -y python3-full pipx nano
pipx ensurepath
```

Open a new terminal, or reconnect over SSH, if `pipx ensurepath` changes your
PATH. Check that `python3 --version` and `pipx --version` work.

Install Docker Engine using Docker's
[Debian installation guide](https://docs.docker.com/engine/install/debian/#install-using-the-apt-repository),
including the `docker-compose-plugin` package. Verify the installation:

```bash
sudo docker run --rm hello-world
sudo docker compose version
```

LabPulse normally uses `sudo docker` for container operations. It does not
require membership of the Docker group. If Compose is missing, follow Docker's
[Compose plugin instructions](https://docs.docker.com/compose/install/linux/).

Set the Pi's timezone and enable clock synchronisation. Replace
`Europe/London` with the lab's timezone:

```bash
sudo timedatectl set-timezone Europe/London
sudo timedatectl set-ntp true
timedatectl status
```

Check that the time is correct and `System clock synchronized` says `yes`
before testing alarms. Use the same timezone in LabPulse's configuration.

## Install LabPulse

```bash
pipx install labpulse
labpulse version
labpulse help
```

pipx keeps LabPulse's dependencies in an isolated environment. Run this without
`sudo`; do not install them into the system Python. The LabPulse worker image
is selected to match the installed package version.

Choose **one** of the next two paths. To explore the dashboard first, use the
simulated installation.

## Create a simulated installation

```bash
labpulse setup --fake-hardware
labpulse up
```

Setup creates `~/labpulse-live`, copies the starter configuration on a new
installation, and generates the deployment. `labpulse up` downloads missing
images and starts the containers; the first run can take several minutes.

You'll see the same sensors and switches as you would with real hardware.
LabPulse supplies simulated readings, and the switches don't operate any
equipment. SMS runs in dry-run mode: messages are logged but aren't sent.

Continue to [Open Home Assistant](#open-home-assistant). You can edit the
configuration later with `labpulse config`; simulation stays enabled. If the
Pi uses a timezone other than `Europe/London`,
set the matching `timezone` through that editor before checking timestamps.

## Create a real-hardware installation

Connect the hardware and enable required Pi interfaces before starting workers.
For I2C sensors such as SHT40 or X1200, enable I2C through `sudo raspi-config`
as described in the [Pi configuration guide](https://www.raspberrypi.com/documentation/computers/configuration.html#enable-or-disable-i2c),
and follow any reboot prompt. Arduino boards need the matching
[LabPulse firmware](../firmware/README.md).

Create the live directory:

```bash
labpulse setup
```

Setup generates files but does not start the stack. Its starter describes the
example lab, so review it before use:

```bash
labpulse config
```

Select `config.yaml` in the editor menu. Use the
[Configuration reference](CONFIGURATION.md) to:

- set `timezone` to match the Pi;
- keep only the services you need enabled, with at least one enabled service;
- set each driver's port, bus, pin, or other hardware options;
- match measurement names and units to the firmware or data source;
- keep `sms.dry_run: true` while testing, and leave unused outputs disabled.

Find stable serial paths with `ls -l /dev/serial/by-id/` and put the appropriate
path in each service's `driver.options.port`. For interactive board
identification, see [Assigning serial devices](TROUBLESHOOTING.md#assigning-serial-devices).

Saving a changed configuration validates it, generates the deployment, checks
the Home Assistant configuration, and recreates the containers. It can
therefore start real workers immediately. An unchanged edit may exit without
restarting anything. Ensure the stack is running with:

```bash
labpulse up
```

For a Triton control PC, follow the separate [Triton publisher guide](TRITON_PUBLISHER.md)
for its network, credentials, and publisher setup. For a modem, complete
[SMS host setup](TROUBLESHOOTING.md#sms-host-setup) before enabling real delivery.

## Open Home Assistant

On the Pi, run `labpulse open`. Over SSH, open `http://<pi-address>:8123` in a
browser on your own computer. Replace `<pi-address>` with the Pi's network
address, without the angle brackets. For example, if its address is
`192.168.1.50`, open `http://192.168.1.50:8123`. Allow Home Assistant time to
finish startup.

1. Create the Home Assistant account and complete onboarding.
2. Open **Settings → Devices & services**, choose **Add integration**, and
   select [MQTT](https://www.home-assistant.io/integrations/mqtt/#configuration).
3. Set the broker to `127.0.0.1` and port to `1883`. The standard local listener
   does not require a username or password.
4. Open the **LabPulse** dashboard from the sidebar.

Home Assistant connects through the Pi's local address. LabPulse worker
containers use `mosquitto:1883`; keep that hostname in the live configuration.
Once MQTT is connected, the LabPulse sensors and switches should appear
automatically.

## Check the installation

```bash
labpulse ps --all
labpulse doctor
```

Doctor should report no failures. Read its warnings and resolve those relevant
to this installation, including host clock and
[watchdog configuration](TROUBLESHOOTING.md#host-clock-or-watchdog-warning).
Then check the dashboard:

1. **System Status** shows the expected services as **Working** and their
   required readings are current.
2. **Monitor** shows the expected setups, readings, and controls. Simulated
   analogue values generally change; digital states may stay constant while
   continuing to publish.
3. **Alarm Setup** has **Mute all notifications** and **Test mode** enabled on
   a new installation. Review thresholds and recipients before unmuting.
4. For real hardware, compare readings with the physical instruments and test
   one failure and recovery. Follow [Testing SMS](USER_GUIDE.md#testing-sms)
   before relying on modem delivery.

Run `labpulse restart`, allow the services to recover, and check again. Test
mode turns on whenever Home Assistant starts; the global mute choice is
restored. Doctor checks installation and connectivity, but cannot prove
calibration or that a text message reached a handset.

Create a [backup](#backups-and-restoring-on-a-new-pi) once everything is working. To
stop a demonstration without deleting configuration or history, run `labpulse down`.

If you're using simulation, continue with
[Your first look at LabPulse](FIRST_STEPS.md#find-your-way-around). It walks
through a reading, its history, and a practice alarm. To connect an Arduino,
use [Connect your first sensor](FIRST_SENSOR.md).

## Changing the configuration

Your settings live in these files:

```text
~/labpulse-live/config.yaml
~/labpulse-live/config.d/       measurement files referenced by config.yaml
```

Use `labpulse config` to edit them. You can also select files directly, such as
`labpulse config config.yaml config.d/triton-01-measurements.yaml`. See
[measurement files](CONFIGURATION.md#moving-measurements-into-configd) for the
file format. The configuration in the repository is a starting example for new
installations.

LabPulse replaces `compose.yaml`, `config.resolved.yaml`, `config.fake.yaml`
when used, and these Home Assistant files during generation:

```text
homeassistant/config/configuration.yaml
homeassistant/config/packages/labpulse_generated.yaml
homeassistant/config/labpulse-dashboard.yaml
```

Don't edit those generated files by hand; LabPulse will overwrite your changes.
It keeps your Home Assistant accounts and saved settings, along with
automations, scripts, and scenes you've created in Home Assistant.

For a different installation directory, put `--live-dir` before the command,
for example `labpulse --live-dir /srv/labpulse setup`. Use that same directory
for subsequent commands, or set `LABPULSE_LIVE_DIR` consistently.

## Switching between simulated and real hardware

Stop the current stack with `labpulse down`. To select simulation, run:

```bash
labpulse setup --fake-hardware
labpulse up
```

To select real hardware, review the configured devices, outputs, and SMS
settings first, then run:

```bash
labpulse setup
labpulse up
```

Setup preserves the live source configuration and Home Assistant private
state. Real mode uses the configured hardware and `sms.dry_run` setting;
simulation's forced dry-run no longer applies. If you need to edit the source
before switching, use `labpulse config` in the current mode, then stop the
stack again before running setup. Repeat the installation checks afterward.

## Updating

Record `labpulse version`, make a backup, and review release notes before running:

```bash
labpulse update
```

The command installs the latest PyPI release, preserves the active hardware
mode, refreshes managed files, recreates the stack, waits for Home Assistant,
and runs Doctor. If that version is already installed, it exits without
recreating anything. Confirm that readings resume in **System Status**.

Updates don't automatically mute notifications or create a backup. Make your
backup first, and use the dashboard's mute controls if you need to pause
notifications during maintenance.
For a particular published release, pass its version to `labpulse update`;
use `labpulse help update` for the syntax. If an update fails, follow
[update recovery](TROUBLESHOOTING.md#update-failed-or-sms-worker-is-offline).

## Backups and restoring on a new Pi

Save an archive outside the live directory:

```bash
mkdir -p ~/labpulse-backups
labpulse backup ~/labpulse-backups/labpulse-$(date +%Y%m%d-%H%M%S).tar.gz
```

LabPulse briefly stops running services to copy the source configuration,
Home Assistant state, Mosquitto retained data, and SMS subscription/request
state. It restarts those services before compressing the archive. Archives
contain private data and are not encrypted; copy them to protected storage
outside the Pi.

External MQTT certificates, keys, passwords, and ACLs under
`~/labpulse-live/mosquitto/config/` are **not included**. A Triton-enabled
installation needs a separate protected copy of those files. Host settings,
firmware, and Windows publisher files also require separate records.

On a replacement Pi, prepare the host, install the recorded compatible LabPulse
release, and reconnect the hardware. Restore any external MQTT security files
to their original live paths and permissions before running:

```bash
labpulse restore /path/to/labpulse-backup.tar.gz
```

Restore asks for confirmation, restores the recorded hardware mode, regenerates
managed files with the **currently installed package**, starts the stack, and
runs diagnostics. It does not install the package version recorded in the
archive. Existing state receives a rollback archive before replacement.

Recheck the host clock, watchdog, interfaces, modem, and device identities.
See [backup and restore troubleshooting](TROUBLESHOOTING.md#backup-or-restore-fails)
for failures and [the User Guide](USER_GUIDE.md#backups-and-restoration) for
ordinary backup use.

## Troubleshooting

Start with:

```bash
labpulse doctor
labpulse ps --all
labpulse logs --tail 100
```

Use [Troubleshooting](TROUBLESHOOTING.md) for installation failures, missing
devices or readings, generated-file repair, alarms, SMS, and recovery. Edit
the source with `labpulse config`; use the repair procedure when generated
files alone are damaged.

For dashboard and alarm operation, continue with the [User Guide](USER_GUIDE.md).
For a source checkout or local image, use [Development](DEVELOPMENT.md).
To remove the deployment, follow [Removing an installation](USER_GUIDE.md#removing-an-installation).
