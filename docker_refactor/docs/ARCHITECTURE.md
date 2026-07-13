# LabPulse Docker Architecture

The Docker refactor separates LabPulse into small services with clear ownership.
The goal is that hardware reading, operator display, alarm decisions, and SMS
delivery can each change without becoming tangled together.

## Runtime Components

The generated Raspberry Pi project lives at:

```text
~/labpulse-ha/
```

It contains one Docker Compose project:

```text
homeassistant
  Home Assistant web UI, helpers, alarms, dashboard, history, logbook

mosquitto
  MQTT broker used by all LabPulse services

labpulse-sms
  Shared SMS worker that subscribes to LabPulse SMS MQTT topics

labpulse-<service>
  One Python container per enabled sensor hub
```

Each sensor container runs the hardware package entry point with a different
service key:

```bash
python -m labpulse_hardware --service pressure_monitor
python -m labpulse_hardware --service pump_room
python -m labpulse_hardware --service turbo_pump
```

The service key selects one entry under `services:` in `config.yaml`.

## Main Data Flow

```text
Arduino USB serial device
  -> labpulse-<service> container
  -> SerialDriver
  -> SerialParser
  -> HomeAssistantMqttPublisher
  -> Mosquitto
  -> Home Assistant MQTT discovery/entities
  -> Home Assistant generated alarm logic
  -> mqtt.publish labpulse/sms/send
  -> labpulse-sms container
  -> log backend or mmcli modem backend
```

The Python sensor service publishes facts:

- current reading values
- service connection status
- Home Assistant MQTT discovery metadata

Home Assistant decides what those facts mean:

- threshold values
- alarm state
- alert delay
- recovery delay
- persistent notifications
- SMS automation payloads
- dashboard layout

That split is deliberate. Do not add threshold decision-making to the Python
sensor services unless the whole design is intentionally changing.

## Generated Setup Flow

The bootstrap script is:

```text
docker_refactor/setup_container_fs.sh
```

It creates or refreshes:

```text
~/labpulse-ha/
  config.yaml
  compose.yaml
  generate_compose.sh
  generate_homeassistant_config.sh
  labpulse-python/
    labpulse_common/
    labpulse_hardware/
    labpulse_sms/
  labpulse_homeassistant/
  homeassistant/config/
  mosquitto/
  logs/
```

It copies the Python packages and generator scripts into the live folder so the
Pi can run from `~/labpulse-ha` without needing Docker build context outside
that folder.

The live update loop is:

```bash
cd ~/labpulse-ha
nano config.yaml
./generate_compose.sh
./generate_homeassistant_config.sh
docker compose up -d --build
```

## Compose Generation

`generate_compose.sh` reads `~/labpulse-ha/config.yaml` and writes:

```text
~/labpulse-ha/compose.yaml
```

It creates:

- `homeassistant`
- `mosquitto`
- `labpulse-sms`
- one `labpulse-<service>` container for each enabled service

If a service has:

```yaml
services:
  pump_room:
    enabled: false
```

then no `labpulse-pump-room` container is generated.

The Compose file is generated output. If a service, mount, command, or container
name is wrong, change `config.yaml` or `generate_compose.sh`, then regenerate.

## Home Assistant Generation

`generate_homeassistant_config.sh` reads `~/labpulse-ha/config.yaml` and writes:

```text
~/labpulse-ha/homeassistant/config/configuration.yaml
~/labpulse-ha/homeassistant/config/packages/labpulse_generated.yaml
~/labpulse-ha/homeassistant/config/labpulse_entity_map.yaml
```

It creates these UI-managed files only if missing:

```text
automations.yaml
scripts.yaml
scenes.yaml
```

It writes the editable dashboard storage file only when explicitly requested:

```bash
./generate_homeassistant_config.sh --reset-dashboard
```

Normal generation preserves:

```text
homeassistant/config/.storage/lovelace
```

This is what lets users keep editing the dashboard in the Home Assistant UI.

## MQTT Network Names

Inside LabPulse Python containers, the broker is the Compose service name:

```yaml
mqtt:
  broker: "mosquitto"
  port: 1883
```

Inside Home Assistant, the MQTT integration should use:

```text
Broker: 127.0.0.1
Port: 1883
```

This is because Home Assistant runs with `network_mode: host`, while the Python
containers run on the Compose network.

## Stable Entity Identity

LabPulse uses stable machine IDs so generated dashboards and automations can
predict Home Assistant entity names.

For service `pressure_monitor` and reading `pressure`:

```text
MQTT unique_id:       labpulse_pressure_monitor_pressure
MQTT object_id:       labpulse_pressure_monitor_pressure
default entity_id:    sensor.labpulse_pressure_monitor_pressure
alarm state:          input_select.labpulse_pressure_monitor_pressure_alarm_state
alarm mode:           input_select.labpulse_pressure_monitor_pressure_alarm_mode
alarm muted:          input_boolean.labpulse_pressure_monitor_pressure_alarm_muted
minimum threshold:    input_number.labpulse_pressure_monitor_pressure_minimum_threshold
maximum threshold:    input_number.labpulse_pressure_monitor_pressure_maximum_threshold
recovery deadband:    input_number.labpulse_pressure_monitor_pressure_recovery_deadband
danger zone:          binary_sensor.labpulse_pressure_monitor_pressure_danger_zone
recovery zone:        binary_sensor.labpulse_pressure_monitor_pressure_recovery_zone
sensor fault zone:    binary_sensor.labpulse_pressure_monitor_pressure_sensor_fault_zone
danger ratio:         sensor.labpulse_pressure_monitor_pressure_danger_ratio
```

Labels are safe to change. Stable service keys and reading names are more
expensive to change because they affect entity IDs, dashboard references, and
historical continuity.

## Ownership Boundaries

Use this table when deciding where a change belongs:

| Change | Edit here |
| --- | --- |
| Enable/disable a hub | `~/labpulse-ha/config.yaml` |
| Change USB serial path | `~/labpulse-ha/config.yaml` |
| Change displayed hub/reading label | `~/labpulse-ha/config.yaml` |
| Change section order or icon | `~/labpulse-ha/config.yaml` |
| Add a container mount or command rule | `generate_compose.sh` |
| Change shared config validation | `labpulse_common/config.py` |
| Change shared identity rules | `labpulse_common/identity.py` |
| Change shared MQTT topics/contracts | `labpulse_common/mqtt_contracts.py` |
| Change a hardware driver | `labpulse_hardware/drivers/` |
| Change temporary serial parsing | `labpulse_hardware/legacy_parsing/serial_parser.py` |
| Change MQTT discovery publishing | `labpulse_hardware/homeassistant_publisher.py` |
| Change Home Assistant entity modelling | `labpulse_homeassistant/data_models.py` |
| Change live dashboard arrangement | Home Assistant UI |
| Change reset dashboard starter layout | `labpulse_homeassistant/templates/dashboard/dashboard_seed.yaml` |
| Change generated alarm helpers/automations | `labpulse_homeassistant/templates/alarm/alarm_logic.yaml` |
| Change SMS delivery backend behavior | `labpulse_sms/sender.py` |
| Change SMS MQTT parsing | `labpulse_sms/sms_subscriber.py` |

## Safety Rules

Do not hand-edit generated files for lasting changes:

```text
~/labpulse-ha/compose.yaml
~/labpulse-ha/homeassistant/config/packages/labpulse_generated.yaml
~/labpulse-ha/homeassistant/config/labpulse_entity_map.yaml
```

Do hand-edit:

```text
~/labpulse-ha/config.yaml
```

Do use the Home Assistant UI for:

- live dashboard layout
- helper values such as thresholds and delays
- user accounts
- integration setup

Use repository templates when changing what a fresh or reset system generates.
