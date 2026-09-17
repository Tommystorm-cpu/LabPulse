# LabPulse documentation

The guides here explain complete workflows that cross several code packages.
Implementation details for one package live in the nearest source-folder
README.

## New operator

1. Read [Installation](INSTALLATION.md) and complete either the real-hardware
   or simulation path.
2. Use the [User Guide](USER_GUIDE.md) to understand every feature and its
   normal, failure and recovery behaviour.
3. Use [Configuration](CONFIGURATION.md) when editing the live `config.yaml`
   and referenced measurement files beneath `config.d/`.
4. Use [Operations](OPERATIONS.md) for normal incident/update handling and
   [Troubleshooting](TROUBLESHOOTING.md) when state or delivery is unexpected.

## Existing operator

- [User Guide](USER_GUIDE.md): commands, dashboards, alarms, SMS, outputs,
  simulation, diagnostics, backups and limitations.
- [Configuration](CONFIGURATION.md): fields, defaults, constraints and complete
  examples.
- [Installation](INSTALLATION.md): updates, reconstruction and symptom-led
  troubleshooting.
- [Operations](OPERATIONS.md): interpreting state, notification controls, and
  safe update recovery.
- [Troubleshooting](TROUBLESHOOTING.md): service, reading, and delivery problems.
- [Hardware](HARDWARE.md): current interface boundary and placeholders for the
  future photographed build record.
- [Triton publisher](TRITON_PUBLISHER.md): secure Pi MQTT listener and unattended
  Windows control-PC installation.

The installed source bundle is `~/labpulse-live/config.yaml` plus any
measurement files it references beneath `config.d/`. The repository
`config.yaml` and packaged fragments are starter templates. Generated resolved,
fake-runtime, Compose, and Home Assistant files are not independent settings.

## Contributor

1. Read [Architecture](ARCHITECTURE.md) for process boundaries and data flow.
2. Read the nearest package README, starting with
   [`src/labpulse`](../src/labpulse/README.md).
3. Use [Development](DEVELOPMENT.md) for setup, tests, packaging, CI and
   real-Pi acceptance.
4. Use the [roadmap](../ROADMAP.md) for planned work; do not infer features from
   historical or future descriptions.

## Authoritative homes

| Subject | Owner |
|---|---|
| Project summary, safety and maturity | [Root README](../README.md) |
| Research citation metadata | [Citation file](../CITATION.cff) |
| Private vulnerability reporting and supported security boundary | [Security policy](../SECURITY.md) |
| First installation, updates, reconstruction and troubleshooting | [Installation](INSTALLATION.md) |
| Day-to-day incident and update handling | [Operations](OPERATIONS.md) |
| Incident and notification diagnosis | [Troubleshooting](TROUBLESHOOTING.md) |
| Every user-visible feature and its behaviour | [User Guide](USER_GUIDE.md) |
| YAML sections, fields, defaults and examples | [Configuration](CONFIGURATION.md) |
| Cross-process design, ownership and failure boundaries | [Architecture](ARCHITECTURE.md) |
| Development, tests, packaging and release process | [Development](DEVELOPMENT.md) |
| Physical interface status and future build evidence | [Hardware](HARDWARE.md) |
| Triton logfile publication from Windows control PCs | [Triton publisher](TRITON_PUBLISHER.md) |
| One Python package or template tree | Its folder `README.md` |
| Arduino library, examples and serial wire format | [Firmware README](../firmware/README.md) |
| Future work and historical acceptance | [Roadmap](../ROADMAP.md) |

LabPulse is a monitoring aid, not a safety interlock or guaranteed
notification path. Hardware-free tests validate software contracts; wiring,
calibration, modem delivery and attached-equipment behaviour need physical
acceptance.
