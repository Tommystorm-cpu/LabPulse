# LabPulse

[![Tests](https://github.com/lairdgrouplancaster/LabPulse/actions/workflows/test.yml/badge.svg)](https://github.com/lairdgrouplancaster/LabPulse/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/labpulse)](https://pypi.org/project/labpulse/)
[![MIT licence](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

LabPulse monitors the building services that laboratory experiments rely on:
power, chilled water, compressed air, room conditions and similar systems which
are easy to forget about until something goes wrong. We built it for the
[Laird Group](https://wp.lancs.ac.uk/laird-group/) at Lancaster University and
think of it as the monitoring side of a small-scale building management system.

LabPulse runs on a Raspberry Pi and brings readings from Arduino sensor hubs,
sensors connected directly to the Pi, and other computers into one Home
Assistant dashboard. It records those readings, shows whether each monitoring
service is healthy, and can send an SMS when a confirmed problem needs
attention.

The project began as a Lancaster University internship and has already helped
the group respond quickly to what could otherwise have interrupted an
experiment. Other groups can adapt it by describing their sensors and
measurements in one human-readable YAML configuration file. LabPulse generates
the containers, Home Assistant entities, dashboards and alarms around it.

<p align="center">
  <img src="docs/images/labpulse-overview.png" width="900" alt="Overview of LabPulse monitoring laboratory environment, power, chilled water and compressed air">
</p>

> [!IMPORTANT]
> LabPulse is a monitoring aid, not a safety interlock, emergency shutdown
> system or guaranteed notification channel. Equipment which could cause
> injury, damage or loss still needs suitable independent protection.

## What it does

- Collects measurements from Arduino serial devices, sensors connected directly
  to the Raspberry Pi, UPS hardware, and named messages from other computers.
- Creates Home Assistant dashboards, history, service-health indicators and
  configurable measurement alarms.
- Separates a failed sensor service from an individual missing or dangerous
  reading, so the dashboard gives a useful explanation instead of one generic
  error.
- Sends optional SMS warnings and recoveries through a modem connected to the
  Pi.
- Provides backup, restore, update and diagnostic commands for the installed
  system.
- Includes a complete fake-hardware mode which simulates every configured
  sensor and output without changing the dashboard or container layout.

## Live installation

![Live LabPulse dashboard showing UPS power, chilled-water readings for two Triton fridges, turbo-pump cooling, compressed air, and room conditions.](docs/images/live-monitor.png)

*The live reference installation, supplied 18 September 2026. Readings are
grouped by lab setup, with UPS power information alongside them. The Test mode
banner shows that notifications are routed to the configured test recipients.
Your dashboard reflects your own configured equipment.*

The [System Status example in the user guide](docs/USER_GUIDE.md#system-status)
shows how LabPulse distinguishes service health from missing optional readings.

## How it fits together

```text
 Arduino hubs      Pi sensors      Other computers
      |                |             JSON over MQTT
      +----------------+--------------------+
                           |
                    LabPulse workers
                           |
                   Mosquitto MQTT broker
                           |
                    Home Assistant
              dashboards, history and alarms
                     |               |
              SMS request      manual command
                     |               |
                SMS worker      output worker
                                      |
                                  Pi GPIO
```

MQTT is a lightweight way for the containers to exchange messages; Mosquitto is
the local program which carries them. Each enabled monitoring service runs in
its own container, so a failure in one sensor does not need to stop the rest of
the system. Home Assistant owns the web dashboard, alarm thresholds and
operator controls; the Python workers concentrate on reading hardware and
publishing validated measurements.

## Try it without hardware

New to Raspberry Pi or Home Assistant? Start with
[Your first look at LabPulse](docs/FIRST_STEPS.md), then follow the installation
guide. The walkthrough explains the pieces and gives you a practice alarm to try.

You do not need a finished sensor build to see how LabPulse works. The reference
setup is a Raspberry Pi 5 running 64-bit Raspberry Pi OS based on Debian 12.
After installing the prerequisites in the
[installation guide](docs/INSTALLATION.md#requirements), install LabPulse and
start the fake-hardware deployment with:

```bash
pipx install labpulse
labpulse setup --fake-hardware
labpulse up
labpulse doctor
labpulse open
```

You'll see simulated readings for every enabled sensor, including those that
would normally use serial, I²C, GPIO, UPS hardware or MQTT. Most readings vary
over time; digital inputs stay active. You can try the output switches without
operating any equipment, and SMS messages are logged without being sent. If
you're using the Pi over SSH, open `http://<pi-address>:8123` from another
computer instead of running `labpulse open`.

On the first visit, create a Home Assistant account and add its MQTT integration
using broker `127.0.0.1` and port `1883`. When the setup is ready, the System
Status dashboard should show the example services and their readings should
continue to update. The [installation guide](docs/INSTALLATION.md#create-a-simulated-installation)
walks through onboarding, and the [user guide](docs/USER_GUIDE.md#using-fake-hardware)
explains what you can test in simulation and what needs real hardware.

For convenient dashboard access away from the lab, we recommend the optional
**Nabu Casa / Home Assistant Cloud** subscription. The
[remote-access instructions](docs/USER_GUIDE.md#access-from-outside-the-lab)
also cover **Raspberry Pi Connect** for running shell commands from your browser.

When finished, stop the containers without deleting their state:

```bash
labpulse down
```

## Hardware and support

The reference system is a Raspberry Pi 5 running 64-bit Raspberry Pi OS based
on Debian 12. The software includes these acquisition paths:

| Part | What to expect |
|---|---|
| Raspberry Pi 5, Home Assistant, MQTT and fake-hardware mode | The tested reference setup |
| Standard pipe-delimited Arduino serial devices | The standard way to connect Arduino sensor hubs; tested without hardware and during local commissioning |
| SHT40, DHT11, X1200 UPS and generic GPIO inputs | Drivers are included; verify the real wiring and readings during installation |
| SMS through the Linux ModemManager service | Optional; test the chosen modem, SIM and mobile network locally |
| Named JSON over MQTT and the Triton logfile publisher | Optional links to other computers; configure and test the network boundary locally |
| Generic GPIO outputs | Manual control only; never use them as a safety function |

The hardware-free test suite covers configuration, generators, workers, alarms
and failure handling, but software tests cannot prove wiring, calibration,
modem delivery or equipment behaviour. The [hardware guide](docs/HARDWARE.md)
explains that boundary in more detail. This repository also contains Arduino
firmware and design-reference PCB, enclosure and 3D-printing assets. Their
presence does not mean that a physical design has been electrically verified or
is ready to manufacture.

## Configuration in one place

On an installed Pi, the configuration you own is:

```text
~/labpulse-live/config.yaml
~/labpulse-live/config.d/*.yaml    when measurement files are used
```

Run `labpulse config` to edit and validate it. Compose and Home Assistant files
are generated from this source and should not be maintained separately. The
[`config.yaml`](config.yaml) in this repository is only the starter copied into
a new installation; changing it does not change an existing Pi.

## Where to go next

- **I want to install it:** start with [Installation](docs/INSTALLATION.md).
- **I want to understand the dashboard and alarms:** read the
  [User Guide](docs/USER_GUIDE.md).
- **I am configuring sensors or measurements:** use the
  [Configuration Reference](docs/CONFIGURATION.md).
- **I am operating an existing system:** use the [User Guide](docs/USER_GUIDE.md)
  and [Troubleshooting](docs/TROUBLESHOOTING.md).
- **I want to understand or change the code:** read
  [Architecture](docs/ARCHITECTURE.md), [Development](docs/DEVELOPMENT.md) and
  [Contributing](CONTRIBUTING.md).
- **I want to see what may come next:** read the [Roadmap](ROADMAP.md).
- **I want to browse everything:** use the
  [documentation index](docs/README.md).

## Contributing and getting help

Bug reports, documentation corrections and new hardware ideas are welcome.
Please read [CONTRIBUTING.md](CONTRIBUTING.md) before making a larger change,
particularly a new driver or configuration field. Questions and reproducible
problems can be raised through the repository's
[GitHub issues](https://github.com/lairdgrouplancaster/LabPulse/issues). We
welcome attempts to adapt LabPulse for other laboratories and are happy to
answer questions as time allows.

Please do not put credentials, phone numbers, private network details or a
suspected security vulnerability in a public issue. Use the private process in
[SECURITY.md](SECURITY.md) instead.

If you use LabPulse in published research, please use the repository's
[citation metadata](CITATION.cff) and record the exact release and local
configuration used so the monitoring setup can be reproduced.

## Licence

LabPulse is released under the [MIT License](LICENSE). Third-party hardware
assets may also carry their own attribution or licence information.
