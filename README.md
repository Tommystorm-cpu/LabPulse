# LabPulse

LabPulse monitors laboratory infrastructure with a Raspberry Pi, Arduino
sensor hubs, and supported direct or network inputs. It publishes measurements
and service health over MQTT, builds Home Assistant dashboards and alarms, can
send SMS notifications, and provides explicitly configured manual GPIO
outputs.

LabPulse is pre-1.0 software. It is not a safety-rated interlock or a guaranteed
notification channel; independent safeguards remain necessary for critical
equipment.

## Start here

- **Install LabPulse:** [Installation](docs/INSTALLATION.md), including a
  hardware-free simulated setup and troubleshooting.
- **Use every feature:** [User guide](docs/USER_GUIDE.md).
- **Configure a lab:** [Configuration reference](docs/CONFIGURATION.md).
- **Understand the hardware boundary:** [Hardware](docs/HARDWARE.md).
- **Understand or change the system:** [Architecture](docs/ARCHITECTURE.md) and
  [Development](docs/DEVELOPMENT.md).
- **Browse all documentation:** [Documentation index](docs/README.md).

## How it fits together

```text
Arduino serial / Pi sensors / named MQTT input
                    |
            one worker per service
                    |
                Mosquitto
                    |
              Home Assistant
       dashboards, history, alarm decisions
           |                       |
       SMS requests          manual output command
           |                       |
       SMS worker           one worker per output
```

An installed Pi is managed with `labpulse setup`, `labpulse update`,
`labpulse config`, `labpulse up`, and `labpulse doctor`. Its operator-owned
source of truth is `~/labpulse-live/config.yaml`; the repository
[config.yaml](config.yaml) is only the new-install starter. Generated Compose
and Home Assistant files must be regenerated rather than maintained
independently.

Code ownership and local contracts are documented beside the implementation,
starting with [the Python package](src/labpulse/README.md),
[deployment scripts](deployment/README.md), [firmware](firmware/README.md), and
[tests](testing/README.md).

## Contribute

Read [CONTRIBUTING.md](CONTRIBUTING.md) and the README in the folder you intend
to change. The [roadmap](ROADMAP.md) records planned work and historical
acceptance; it is not the current behavior reference.

## Licence

See the [MIT License](LICENSE). Preserve third-party credits associated with
individual hardware assets.
