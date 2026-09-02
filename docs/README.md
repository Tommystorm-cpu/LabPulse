# LabPulse documentation

These guides describe the current LabPulse package, generated deployment, and
supported workflows.

## Operator path

Read in this order for a new installation:

1. [Product scope and safety boundary](PRODUCT_SCOPE.md)
2. [Supported environments](SUPPORT.md)
3. [Installation](INSTALLATION.md)
4. [Configuration reference](CONFIGURATION.md)
5. [Operations](OPERATIONS.md)
6. [Home Assistant and alarms](HOME_ASSISTANT.md)
7. [SMS notifications](SMS.md)
8. [Troubleshooting](TROUBLESHOOTING.md)

The normal operator surface is the unified `labpulse` command. The installed
configuration source is always `~/labpulse-live/config.yaml`.

## Contributor path

1. [Architecture](ARCHITECTURE.md)
2. [Development](DEVELOPMENT.md)
3. [Driver development](DRIVER_DEVELOPMENT.md)
4. [Standard serial protocol](SERIAL_PROTOCOL.md)
5. [Firmware](../firmware/README.md)
6. [Contributing](../CONTRIBUTING.md)
7. [Roadmap](../ROADMAP.md)

## Sources of truth

| Subject | Current source of truth |
|---|---|
| Installed sensor configuration | `~/labpulse-live/config.yaml` |
| New-install template | repository `config.yaml` |
| Global config, cross-references, and loading | `src/labpulse/common/config.py` |
| Physical and calculated measurement config | `src/labpulse/common/measurement_config.py` |
| Driver, service, and power config | `src/labpulse/common/service_config.py` |
| Controlled-output config | `src/labpulse/common/output_config.py` |
| Fake runtime derivation | `src/labpulse/common/fake_config.py` |
| Stable IDs | `src/labpulse/common/identity.py` |
| MQTT and SMS request contracts | `src/labpulse/common/mqtt_contracts.py` |
| Operator commands | `src/labpulse/control.py` |
| Backup archive behavior | `src/labpulse/backup.py` |
| Diagnostics | `src/labpulse/doctor.py` |
| Compose rendering | `src/labpulse/deployment/compose.py` |
| Atomic deployment installation | `src/labpulse/deployment/generate.py` |
| Driver contract | `src/labpulse/hardware/driver.py` |
| Driver discovery | `src/labpulse/hardware/registry.py` |
| Hardware lifecycle | `src/labpulse/hardware/runner.py` |
| Serial parsing | `src/labpulse/hardware/drivers/serial_pipe.py` |
| MQTT discovery/state publication | `src/labpulse/hardware/homeassistant_publisher.py` |
| Controlled-output MQTT lifecycle | `src/labpulse/output/service.py` |
| Home Assistant command and file generation | `src/labpulse/homeassistant/generator.py` |
| Alarm/render context | `src/labpulse/homeassistant/alarm.py` |
| Dashboard and alarm behavior | `src/labpulse/homeassistant/templates/` |
| SMS process composition | `src/labpulse/sms/__main__.py` |
| SMS intake and deduplication | `src/labpulse/sms/subscriber.py` |
| SMS delivery | `src/labpulse/sms/sender.py` |
| SMS subscription commands | `src/labpulse/sms/sender.py` |

`compose.yaml`, `config.fake.yaml`, and generated Home Assistant YAML are
outputs. Change their owning source and regenerate rather than editing them as
independent configuration.

## Where changes belong

| Change | Documentation owner |
|---|---|
| Host prerequisites or first installation | `INSTALLATION.md` |
| YAML field or built-in driver option | `CONFIGURATION.md` |
| Operator command or maintenance workflow | `OPERATIONS.md` |
| Home Assistant entity, dashboard, or alarm behavior | `HOME_ASSISTANT.md` |
| SMS routing, delivery, or subscription behavior | `SMS.md` |
| Cross-process ownership or contract | `ARCHITECTURE.md` |
| Contributor workflow or package structure | `DEVELOPMENT.md` |
| Hardware extension contract | `DRIVER_DEVELOPMENT.md` |
| Serial wire format | `SERIAL_PROTOCOL.md` |
| Symptom and recovery action | `TROUBLESHOOTING.md` |
| Work not implemented in current code | `ROADMAP.md` |
