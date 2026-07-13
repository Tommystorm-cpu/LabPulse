# LabPulse Code Reading Guide

This guide explains the current `docker_refactor/` design after the repository
responsibilities were separated. Start here before changing runtime behaviour.

## Responsibility Map

```text
config.yaml
  -> labpulse_common.config
       one typed configuration model used by every Python service

labpulse_hardware
  -> labpulse_hardware.drivers.factory
  -> labpulse_hardware.drivers.serial_driver
  -> labpulse_hardware.legacy_parsing.serial_parser
  -> labpulse_hardware.homeassistant_publisher

generate_homeassistant_config.sh
  -> labpulse_homeassistant
  -> labpulse_homeassistant.data_models
  -> labpulse_homeassistant.dashboard / alarm / write_yaml
  -> labpulse_homeassistant/templates/

labpulse_sms
  -> labpulse_sms.subscriber
  -> labpulse_sms.sender

Cross-service rules
  -> labpulse_common.identity
  -> labpulse_common.mqtt_contracts
  -> labpulse_common.logging_config
```

The four package boundaries are intentional:

- `labpulse_common` contains only shared infrastructure and contracts.
- `labpulse_hardware` owns acquisition, drivers, temporary parsing, and the
  final hand-off of readings through MQTT discovery/state publishing.
- `labpulse_homeassistant` generates dashboards, helpers, automations, and
  alarm logic; it does not talk to hardware.
- `labpulse_sms` receives alert requests and delivers them.

## Recommended Reading Order

1. `config.yaml`
2. `labpulse_common/config.py`
3. `labpulse_common/identity.py`
4. `labpulse_common/mqtt_contracts.py`
5. `labpulse_hardware/cli.py`
6. `labpulse_hardware/drivers/factory.py`
7. `labpulse_hardware/drivers/base.py`
8. `labpulse_hardware/drivers/serial_driver.py`
9. `labpulse_hardware/legacy_parsing/serial_parser.py`
10. `labpulse_hardware/homeassistant_publisher.py`
11. `labpulse_homeassistant/cli.py`
12. `labpulse_homeassistant/data_models.py`
13. `labpulse_homeassistant/dashboard.py`
14. `labpulse_homeassistant/alarm.py`
15. `labpulse_homeassistant/write_yaml.py`
16. `labpulse_homeassistant/templates/`
17. `labpulse_sms/cli.py`
18. `labpulse_sms/subscriber.py`
19. `labpulse_sms/sender.py`
20. `generate_compose.sh` and `setup_container_fs.sh`
21. `testing/`

## Configuration Boundary

`labpulse_common.config.load_config()` is the only YAML reader used by the
runtime services and the Home Assistant generator. It validates the document
as a `LabPulseConfig`, with typed MQTT, SMS, service, display, and reading
models.

Do not add a second raw-dictionary config reader to another package. Add or
change a typed field in `labpulse_common/config.py`, then consume the typed
model in the owning package.

Service keys and reading names are machine identity. Labels and display hints
are presentation. Changing a service key or reading name changes MQTT and Home
Assistant IDs; changing a label does not.

## Shared Contracts

`labpulse_common/identity.py` owns slugging and stable entity identities. Both
the hardware publisher and Home Assistant model import these helpers, so they
cannot silently invent different entity IDs.

`labpulse_common/mqtt_contracts.py` owns sensor topic construction, Home
Assistant discovery topic construction, the SMS send/subscription topics, and
the fields expected in an SMS alert payload.

Keep this package small. Driver implementations, parser details, dashboard
rendering, and SMS delivery are not common infrastructure.

## Hardware Runtime

Every enabled sensor container starts with:

```bash
python -m labpulse_hardware --service pressure_monitor
```

The runner loads typed config, selects one service, builds its driver, connects
the MQTT publisher, and coordinates the read/publish loop. It should remain an
orchestrator rather than accumulating driver or presentation rules.

`drivers/base.py` defines the driver contract. `drivers/factory.py` maps the
typed `driver` value to an implementation. `drivers/serial_driver.py` owns
serial connection, retry, decoding, status, and delegation to the compatibility
parser.

`legacy_parsing/serial_parser.py` is deliberately isolated. It preserves the
current Arduino text formats while firmware moves toward consistent output.
Do not build new cross-service abstractions around it.

`homeassistant_publisher.py` is part of the hardware pipeline. It is the last
step after a reading has been acquired: it filters readings against config and
publishes retained discovery plus current state. It does not generate dashboard
YAML or decide whether a reading is alarming.

## Home Assistant Generation

`generate_homeassistant_config.sh` makes the live shared package available and
runs `python -m labpulse_homeassistant`.

The generator loads the same typed `LabPulseConfig` as the hardware and SMS
services. `data_models.py` converts it into a render model with predictable
entity IDs. `dashboard.py` and `alarm.py` build template contexts.
`write_yaml.py` writes the core YAML files.

Generated alarm automations own threshold decisions and publish alert requests
to the shared SMS send topic. The SMS payload fields and topic must remain
aligned with `labpulse_common.mqtt_contracts` and `labpulse_sms`.

Normal generation preserves the UI-edited Lovelace dashboard. A dashboard seed
is written only when `--reset-dashboard` is requested.

## SMS Service

The Compose command is:

```bash
python -m labpulse_sms --config /app/config.yaml
```

The entry point loads typed config and builds a sender. The subscriber listens
to the shared SMS subscription topic, parses the shared alert fields, and sends
one formatted message per configured recipient. Dry-run mode is safe for tests;
disabling it uses `mmcli` on the modem Pi.

## Deployment Generation

`setup_container_fs.sh` copies these runtime packages into
`~/labpulse-ha/labpulse-python/`:

```text
labpulse_common/
labpulse_hardware/
labpulse_sms/
```

It copies `labpulse_homeassistant/` beside that build context for host-side
generation. There is no top-level Python compatibility entry point.

`generate_compose.sh` preserves existing service and container names while
using package module entry points. It creates Home Assistant, Mosquitto, one SMS
worker, and one hardware container per enabled service.

## Where Changes Belong

| Change | Owner |
| --- | --- |
| Config fields or validation | `labpulse_common/config.py` |
| Entity identity rules | `labpulse_common/identity.py` |
| Shared MQTT topics or alert schema | `labpulse_common/mqtt_contracts.py` |
| Driver interface or selection | `labpulse_hardware/drivers/` |
| Temporary Arduino text support | `labpulse_hardware/legacy_parsing/serial_parser.py` |
| MQTT discovery/state publishing | `labpulse_hardware/homeassistant_publisher.py` |
| Dashboard or automation model | `labpulse_homeassistant/` |
| Starter dashboard layout | `labpulse_homeassistant/templates/dashboard/dashboard_seed.yaml` |
| Alarm helpers and automations | `labpulse_homeassistant/templates/alarm/alarm_logic.yaml` |
| SMS parsing or delivery | `labpulse_sms/` |
| Containers and mounts | `generate_compose.sh` |
| Live filesystem bootstrap | `setup_container_fs.sh` |

## Tests

Run every script in `testing/` after a cross-package change. The main ownership
map is:

```text
test_common_contracts.py
  shared identity and MQTT contracts

test_legacy_serial_parser.py
  temporary Arduino compatibility formats

test_hardware_factory.py
test_serial_driver.py
  driver selection and behaviour
test_dht11_driver.py
  DHT11 GPIO setup, throttling, and read behavior

test_homeassistant_publisher.py
  hardware-to-MQTT discovery and state hand-off

test_homeassistant_entities.py
test_homeassistant_generator.py
  predictable IDs and generated Home Assistant output

test_sms_container.py
  Compose entry point, subscription, payload parsing, and senders

test_deployment_generation.py
  fake-USB Compose and bootstrap preservation contracts
```

Also generate a temporary live folder, validate `compose.yaml`, and confirm
Home Assistant regeneration preserves an edited dashboard. Use fake serial
paths for integration work; do not touch physical USB paths in automated tests.

## Common Debug Paths

```text
Container missing
  -> config enabled flag -> generate_compose.sh -> compose.yaml

Serial missing
  -> config serial_port -> Compose mounts -> serial_driver.py

Reading missing
  -> serial_parser.py -> readings[].name -> homeassistant_publisher.py

Entity ID wrong
  -> identity.py -> publisher/model contract tests -> entity map

Alarm wrong
  -> Home Assistant helpers -> alarm_logic.yaml -> generated package

SMS missing
  -> alarm payload -> mqtt_contracts.py -> subscriber.py -> sender.py
```
