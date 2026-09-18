# LabPulse documentation

Start with the route that fits what you're trying to do. You don't need to
read every guide before using LabPulse.

Already looking after a running installation? Open the [User Guide](USER_GUIDE.md).
Something has stopped working? Start with [Troubleshooting](TROUBLESHOOTING.md#find-the-problem).
Changing the code? Follow [Your first day maintaining LabPulse](MAINTAINING.md).
Publishing a version? Use [GitHub release to updated Pi](RELEASING.md#quick-guide-github-release-to-updated-pi).

Use the guides from the same release as your installation. Run
`labpulse version` on the Pi to check its version; the repository's default branch may
describe changes that haven't been released yet.

## New operator

1. Read [Your first look at LabPulse](FIRST_STEPS.md#what-youre-installing) to
   understand what runs where and what the dashboard shows.
2. Follow [Installation](INSTALLATION.md), including getting onto the Pi if
   it's new to you. Start with simulation; no sensors are needed.
3. Try [the dashboard and practice alarm](FIRST_STEPS.md#find-your-way-around).
4. Check [Hardware](HARDWARE.md#choose-a-starting-point), then follow
   [Connect your first sensor](FIRST_SENSOR.md) when you're ready for an Arduino.
5. Use the [User Guide](USER_GUIDE.md) for everyday tasks and
   [Configuration](CONFIGURATION.md) to look up settings. Its
   [YAML basics](CONFIGURATION.md#a-few-yaml-basics) explain how to edit examples.

If something doesn't work, go straight to [Troubleshooting](TROUBLESHOOTING.md).

## Existing operator

- [User Guide](USER_GUIDE.md): commands, dashboards, alarms, SMS, outputs,
  simulation, maintenance, backups, removal, and limitations.
- [Configuration](CONFIGURATION.md): fields, defaults, constraints and complete
  examples.
- [Installation](INSTALLATION.md): Pi preparation, installation, updates, and
  restoring on a replacement Pi.
- [Troubleshooting](TROUBLESHOOTING.md): installation, host, device, reading,
  notification and recovery problems.
- [Hardware](HARDWARE.md): recorded sensor parts, hub assignments, firmware
  pins, and the wiring and calibration checks still needed.
- [Purchasing workbook](LabPulse%20Purchasing.xlsx): consolidated parts, supplier
  links, historical prices, requested additions, and earlier choices.
- [Raspberry Pi main unit](MAIN_UNIT.md): Pi, UPS, modem, USB hub, Gravity board,
  sensor connections, and the touchscreen enclosure design history.
- [Enclosure CAD](../hardware/enclosure/README.md): Fusion assembly, STEP export,
  and the assembly and print information still to be recorded.
- [Triton publisher](TRITON_PUBLISHER.md): secure Pi MQTT listener and unattended
  Windows control-PC installation.
  The [publisher source and quick reference](../integrations/triton/README.md)
  are separate from the Arduino firmware.

The installed source bundle is `~/labpulse-live/config.yaml` plus any
measurement files it references beneath `config.d/`. The repository
`config.yaml` and packaged fragments are starter templates. Generated resolved,
fake-runtime, Compose, and Home Assistant files are not independent settings.

## Contributor

Adding sensor support or sending your first pull request? Follow
[Contributing sensors](../CONTRIBUTING.md#contributing-sensors) and the
[GitHub fork-to-pull-request walkthrough](../CONTRIBUTING.md#making-a-change-through-github).

The [screenshot checklist](../screenshot.md) links to the screenshots and
hardware photos still needed. Keep it updated as the guides change.

1. Follow [Your first day maintaining LabPulse](MAINTAINING.md) to set up a
   checkout, run tests, generate files, and follow one reading through the code.
2. Try [the worked changes](MAINTAINER_EXAMPLES.md), starting with a dashboard
   heading before moving on to configuration and drivers.
3. Use [Architecture](ARCHITECTURE.md), [Development](DEVELOPMENT.md), and the
   nearest [package README](../src/labpulse/README.md) as references.
4. Check the relevant guide and current implementation before deciding what's
   missing. Track proposed changes in
   [GitHub issues](https://github.com/lairdgrouplancaster/LabPulse/issues).
   Use [Releasing](RELEASING.md) when preparing a version for other people to install.

## Authoritative homes

| Subject | Owner |
|---|---|
| Project summary, safety and maturity | [Root README](../README.md) |
| First dashboard visit and practice alarm | [First steps](FIRST_STEPS.md) |
| One Arduino reading from serial output to dashboard | [First sensor](FIRST_SENSOR.md) |
| Research citation metadata | [Citation file](../CITATION.cff) |
| Private vulnerability reporting and supported security boundary | [Security policy](../SECURITY.md) |
| First installation, commissioning, updates and reconstruction | [Installation](INSTALLATION.md) |
| Installation, incident and notification diagnosis | [Troubleshooting](TROUBLESHOOTING.md) |
| Everyday use, notification controls, maintenance, and removal | [User Guide](USER_GUIDE.md) |
| YAML sections, fields, defaults and examples | [Configuration](CONFIGURATION.md) |
| Cross-process design, ownership and failure boundaries | [Architecture](ARCHITECTURE.md) |
| First maintainer session and debugging recipes | [Maintaining](MAINTAINING.md) |
| Worked dashboard, configuration, and driver changes | [Maintainer examples](MAINTAINER_EXAMPLES.md) |
| Development conventions and local builds | [Development](DEVELOPMENT.md) |
| Sensor contributions, GitHub forks, and pull requests | [Contributing](../CONTRIBUTING.md) |
| Release preparation and publication | [Releasing](RELEASING.md) |
| Sensor parts, hub assignments, and physical verification | [Hardware](HARDWARE.md) |
| Main-unit parts, connections, power, and enclosure design | [Raspberry Pi main unit](MAIN_UNIT.md) |
| Triton logfile publication from Windows control PCs | [Triton publisher](TRITON_PUBLISHER.md) |
| One Python package or template tree | Its folder `README.md` |
| Arduino library, examples and serial wire format | [Firmware README](../firmware/README.md) |
| Proposed improvements and bugs | [GitHub issues](https://github.com/lairdgrouplancaster/LabPulse/issues) |
| Historical Pi reliability results | [July 2026 acceptance record](../testing/real_hardware/ACCEPTANCE_2026-07-27.md) |

LabPulse is a monitoring aid, not a safety interlock or guaranteed
notification path. Hardware-free tests validate software contracts; wiring,
calibration, modem delivery and attached-equipment behaviour need physical
acceptance.
