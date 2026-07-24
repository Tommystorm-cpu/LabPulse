# LabPulse documentation

This documentation describes the current implementation. Files under
`legacy/` describe superseded prototypes and are not installation guidance.

## I want to operate LabPulse

1. [Install LabPulse](INSTALLATION.md)
2. [Understand the product scope and safety boundary](PRODUCT_SCOPE.md)
3. [Check supported environments and pre-1.0 boundaries](SUPPORT.md)
4. [Configure sensors and services](CONFIGURATION.md)
5. [Start, stop, inspect, and update the system](OPERATIONS.md)
6. [Use the Home Assistant dashboard and alarms](HOME_ASSISTANT.md)
7. [Configure SMS notifications](SMS.md)
8. [Troubleshoot a problem](TROUBLESHOOTING.md)

## I want to develop LabPulse

1. [Understand the architecture](ARCHITECTURE.md)
2. [Set up a development environment and run tests](DEVELOPMENT.md)
3. [Add a sensor or hardware driver](DRIVER_DEVELOPMENT.md)
4. [Implement the standard serial protocol](SERIAL_PROTOCOL.md)
5. [Build or adapt Arduino firmware](../firmware/README.md)
6. [Understand the project direction](../ROADMAP.md)

## Project information

- [Contributing](../CONTRIBUTING.md)
- [Changelog](../CHANGELOG.md)
- [Product scope and safety boundary](PRODUCT_SCOPE.md)
- [Supported environments](SUPPORT.md)

## Sources of truth

| Subject | Source of truth |
|---|---|
| Installed sensors and services | `~/labpulse-live/config.yaml` |
| New-install defaults | repository `config.yaml` |
| Python configuration rules | `src/labpulse/common/config.py` |
| Driver contract | `src/labpulse/hardware/api.py` |
| Driver discovery | `src/labpulse/hardware/registry.py` |
| Serial parsing | `src/labpulse/hardware/serial_parser.py` |
| Compose generation | `deployment/generate_compose.sh` |
| Home Assistant generation | `src/labpulse/homeassistant/` |
| SMS payloads and topics | `src/labpulse/common/mqtt_contracts.py` |
| Operator command behavior | `src/labpulse/control.py` |
| Product scope and safety boundary | `docs/PRODUCT_SCOPE.md` |
| Supported platforms and compatibility | `docs/SUPPORT.md` |
| Current project direction | `ROADMAP.md` |

Generated Compose and Home Assistant YAML are outputs. Do not document or edit
them as independent sources of truth.
