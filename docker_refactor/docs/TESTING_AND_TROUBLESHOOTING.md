# Testing And Troubleshooting

Use this guide to verify changes and isolate failures by layer.

## Test Files

Tests live in:

```text
docker_refactor/testing/
```

Useful reading order:

```text
test_legacy_serial_parser.py
  temporary Arduino serial compatibility formats and output keys

test_hardware_factory.py
  how config selects drivers

test_serial_driver.py
  serial setup, read, reconnect, and status behavior

test_dht11_driver.py
  DHT11 GPIO setup, throttling, and read behavior without Pi hardware

test_simulate_serial.py
  simulated serial paths, scenario controls, and room environment output

test_homeassistant_publisher.py
  exact MQTT discovery topics, payloads, and entity IDs

test_common_contracts.py
  shared identity, sensor topic, and SMS payload contracts

test_homeassistant_entities.py
  model/entity ID assumptions

test_homeassistant_generator.py
  generated Home Assistant files and dashboard behavior

test_sms_container.py
  SMS subscription, payload parsing, and sender backends

test_deployment_generation.py
  fake-USB Compose output and setup refresh/preservation contracts
```

## Run Tests

From the repository root:

```powershell
python .\docker_refactor\testing\test_legacy_serial_parser.py
python .\docker_refactor\testing\test_hardware_factory.py
python .\docker_refactor\testing\test_dht11_driver.py
python .\docker_refactor\testing\test_simulate_serial.py
python .\docker_refactor\testing\test_serial_driver.py
python .\docker_refactor\testing\test_homeassistant_publisher.py
python .\docker_refactor\testing\test_homeassistant_entities.py
python .\docker_refactor\testing\test_homeassistant_generator.py
python .\docker_refactor\testing\test_sms_container.py
python .\docker_refactor\testing\test_common_contracts.py
python .\docker_refactor\testing\test_deployment_generation.py
```

From inside `docker_refactor/`:

```bash
python testing/test_legacy_serial_parser.py
python testing/test_hardware_factory.py
python testing/test_dht11_driver.py
python testing/test_simulate_serial.py
python testing/test_serial_driver.py
python testing/test_homeassistant_publisher.py
python testing/test_homeassistant_entities.py
python testing/test_homeassistant_generator.py
python testing/test_sms_container.py
python testing/test_common_contracts.py
python testing/test_deployment_generation.py
```

## What To Test After Each Change

| Change | Tests |
| --- | --- |
| Legacy parser behavior | `test_legacy_serial_parser.py` |
| Driver setup/reconnect | `test_serial_driver.py` |
| DHT11 GPIO behavior | `test_dht11_driver.py`, `test_hardware_factory.py` |
| Simulated room input | `test_simulate_serial.py`, `test_legacy_serial_parser.py` |
| Config schema | `test_hardware_factory.py` plus direct startup |
| MQTT topics or IDs | `test_common_contracts.py`, `test_homeassistant_publisher.py`, `test_homeassistant_entities.py` |
| Dashboard seed or alarm template | `test_homeassistant_generator.py` |
| SMS payload or delivery | `test_sms_container.py` |
| Compose/setup generation | `test_deployment_generation.py`, then `docker compose config` on the Pi |

## Layered Debugging

Follow the data path.

### 1. Container Missing

Check:

```bash
cd ~/labpulse-ha
docker compose ps
docker compose config
```

If a service container is missing, check:

```yaml
services:
  service_name:
    enabled: true
```

Then regenerate:

```bash
./generate_compose.sh
docker compose up -d --build
```

### 2. Serial Device Missing

Real USB:

```bash
ls -l /dev/serial/by-id/
```

Fake USB:

```bash
ls -l /tmp/labpulse-fake-serial/
```

Check service logs:

```bash
docker compose logs -f labpulse-pressure-monitor
```

If the host path exists but the container cannot read it, regenerate Compose
and recreate the container.

### 3. Parser Not Producing Readings

Run or inspect parser tests:

```bash
python testing/test_legacy_serial_parser.py
```

Check the serial line format against:

```text
HARDWARE_AND_SERIAL.md
```

If the parser returns keys not listed in `config.yaml`, MQTT publishing ignores
them.

### 4. MQTT Not Receiving Readings

Subscribe to all MQTT traffic:

```bash
docker run --rm -it --network host eclipse-mosquitto:2 \
  mosquitto_sub -h 127.0.0.1 -p 1883 -t '#' -v
```

Check Python config:

```yaml
mqtt:
  broker: "mosquitto"
  port: 1883
```

Inside Python containers, `localhost` is wrong for Mosquitto.

### 5. Home Assistant Has No Entity

Check the MQTT integration:

```text
Settings -> Devices & services -> MQTT
Broker: 127.0.0.1
Port: 1883
```

Check entity map:

```text
~/labpulse-ha/homeassistant/config/labpulse_entity_map.yaml
```

Check discovery traffic:

```bash
docker run --rm -it --network host eclipse-mosquitto:2 \
  mosquitto_sub -h 127.0.0.1 -p 1883 -t 'homeassistant/#' -v
```

### 6. Dashboard Card Wrong

Compare the card entity with:

```text
~/labpulse-ha/homeassistant/config/labpulse_entity_map.yaml
```

If the live dashboard has old card IDs, edit the dashboard in Home Assistant.

If the reset dashboard seed is wrong, edit:

```text
labpulse_homeassistant/templates/dashboard/dashboard_seed.yaml
```

Then run:

```bash
./generate_homeassistant_config.sh --backup-dashboard --reset-dashboard
docker compose restart homeassistant
```

### 7. Alarm Logic Wrong

Inspect generated package:

```text
~/labpulse-ha/homeassistant/config/packages/labpulse_generated.yaml
```

Change source behavior in:

```text
labpulse_homeassistant/templates/alarm/alarm_logic.yaml
```

Change default threshold values in:

```text
labpulse_homeassistant/data_models.py
```

Tune live thresholds in the dashboard helpers.

### 8. SMS Not Working

Manual test:

```bash
docker compose exec mosquitto mosquitto_pub \
  -h mosquitto \
  -t labpulse/sms/send \
  -m '{"title":"LabPulse SMS test","message":"Manual test","service":"manual","reading":"sms"}'
```

Logs:

```bash
docker compose logs -f labpulse-sms
```

For real modem mode:

```bash
mmcli -L
docker compose exec labpulse-sms mmcli -L
```

## Useful Searches

```bash
rg "stable_id" docker_refactor
rg "default_entity_id" docker_refactor
rg "labpulse/sms" docker_refactor
rg "dashboard_seed" docker_refactor
rg "alarm_logic" docker_refactor
```

## Health Commands On The Pi

```bash
docker compose ps
docker stats
free -h
df -h
docker system df
```

Port checks:

```bash
sudo ss -ltnp | grep 8123
sudo ss -ltnp | grep 1883
```

## When In Doubt

Use the ownership boundary:

```text
No container:
  setup_container_fs.sh, generate_compose.sh, config.yaml

No serial:
  USB path, Compose mounts, SerialDriver

No parsed reading:
  legacy_parsing/serial_parser.py, Arduino serial format, readings[].name

No MQTT:
  broker name, Mosquitto logs, HomeAssistantMqttPublisher

No Home Assistant entity:
  MQTT integration, discovery payloads, entity_map

Wrong dashboard:
  Home Assistant UI or dashboard_seed.yaml

Wrong alarm behavior:
  alarm_logic.yaml, generated package, helper values

No SMS:
  Home Assistant automation payload, MQTT topic, labpulse-sms logs, sender backend
```
