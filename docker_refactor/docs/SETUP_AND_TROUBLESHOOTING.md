# Setup and Troubleshooting

This is the operator guide for the Docker refactor: install it on a Raspberry
Pi, configure real or simulated sensors, start the stack, maintain the Home
Assistant dashboard safely, test SMS, and diagnose failures in data-flow order.

## The rule that prevents config confusion

Run the bootstrap script from the repository. After bootstrap, operate the
system from the generated live directory:

```text
Repository source:  ~/LabPulse/docker_refactor/   example checkout location
Live installation:  ~/labpulse-ha/
Live config:         ~/labpulse-ha/config.yaml
```

The repository `docker_refactor/config.yaml` is only a starter copied when the
live config does not exist. Editing it does not change an already installed Pi.

## Prerequisites

The Pi needs:

- Docker Engine with the Compose plugin
- Python 3
- host PyYAML (`sudo apt install python3-yaml`) for Compose generation
- the repository checkout
- stable Arduino serial paths for real hardware, or fake-USB mode

Entity-registry resolution additionally needs `python3-websocket`. Real SMS
delivery additionally needs a working ModemManager/modem on the host.

## First installation

### Real hardware

From the checkout:

```bash
cd ~/LabPulse/docker_refactor
chmod +x setup_container_fs.sh
./setup_container_fs.sh
```

The setup script creates/refreshes `~/labpulse-ha`, copies the current Python
packages and generators, preserves an existing live config, generates Compose
and Home Assistant files, and seeds the dashboard.

### Simulated hardware

```bash
cd ~/LabPulse/docker_refactor
chmod +x setup_container_fs.sh
./setup_container_fs.sh -fake_usb
```

Fake mode changes the starter serial paths to pseudo-terminal links and changes
the room-environment service from GPIO DHT11 to the same simulated serial
pipeline. See [Simulator workflow](#simulator-workflow).

### Alternate live directory

```bash
LABPULSE_CONTAINER_DIR=/path/to/labpulse-ha ./setup_container_fs.sh
```

### Setup backups

`--backup` makes timestamped copies before setup replaces generated/copied
files:

```bash
./setup_container_fs.sh --backup
```

It is not required for the live config: setup always preserves an existing
`config.yaml`.

## Generated live layout

```text
~/labpulse-ha/
  config.yaml                         edit this
  compose.yaml                        generated
  generate_compose.sh
  generate_homeassistant_config.sh
  simulate_serial.py

  labpulse-python/
    Dockerfile
    requirements.txt
    labpulse_common/
    labpulse_hardware/
    labpulse_sms/

  labpulse_homeassistant/             host-side HA generator

  homeassistant/config/
    configuration.yaml                generated
    automations.yaml                  UI-owned; created only if absent
    scripts.yaml                      UI-owned; created only if absent
    scenes.yaml                       UI-owned; created only if absent
    labpulse_entity_map.yaml          generated diagnostic map
    packages/labpulse_generated.yaml  generated alarm package
    .storage/lovelace                 editable dashboard

  homeassistant_backups/              dashboard-only snapshots
  mosquitto/config/
  mosquitto/data/
  mosquitto/log/
  logs/
```

## Configure the live system

```bash
cd ~/labpulse-ha
nano config.yaml
```

Typical shape:

```yaml
mqtt:
  broker: "mosquitto"
  port: 1883

sms:
  dry_run: true
  recipients:
    - "+447700900000"

services:
  pressure_monitor:
    enabled: true
    driver: serial
    parser: pressure
    serial_port: "/dev/serial/by-id/usb-Arduino_..."
    baud_rate: 9600
    device_name: "Air Pressure Sensor Hub"
    display:
      section: "Air Pressure"
      icon: "mdi:gauge"
      order: 40
    readings:
      - name: pressure
        label: Pressure
        unit: bar
        device_class: pressure
    reconnect_interval_seconds: 5
```

### Field reference

| Field | Meaning |
| --- | --- |
| `mqtt.broker` | Use `mosquitto` inside this Compose deployment |
| `sms.dry_run` | Log safely when true; use `mmcli` when false |
| `sms.recipients` | Unique international numbers; keep real values only in the live config |
| service key | Stable machine ID used in containers, MQTT, and HA entities |
| `enabled` | Whether Compose and HA generation include the service |
| `driver` | Implemented: `serial`, or `gpio` with DHT11; `i2c` is not implemented |
| `parser` | Serial format selector: `pressure`, `pump_room`, `water`, or generic pipe fallback |
| `serial_port` | Real stable path or fake path |
| `gpio_sensor` | Currently only `dht11` |
| `gpio_pin` | Blinka board name such as `D4` |
| `device_name` | User-facing HA device label |
| `display.section` | Reset-dashboard section heading |
| `display.icon` | Reset-dashboard heading icon |
| `display.order` | Service order; lower numbers render first |
| `readings[].name` | Stable key; must match driver/parser output |
| `readings[].label` | User-facing label |
| `unit`, `device_class`, `state_class` | MQTT discovery metadata |
| `reconnect_interval_seconds` | Serial reopen delay |
| `read_interval_seconds` | Minimum interval for GPIO reads |

`state_class` defaults to `measurement`; set it to `null` to omit it. Alarm
thresholds, modes, mute state, and timing are Home Assistant helpers, not live
config fields.

### Stable names

Changing labels is safe. Changing a service key or `readings[].name` creates a
new identity, affecting MQTT topics, Home Assistant entities, generated
helpers, dashboard references, and history.

### Real serial paths

List stable paths:

```bash
ls -l /dev/serial/by-id/
```

Use those paths in config. Avoid `/dev/ttyACM0` and `/dev/ttyUSB0`; discovery
order can change them after reboot or reconnect.

### Real DHT11

```yaml
room_environment:
  enabled: true
  driver: gpio
  gpio_sensor: dht11
  gpio_pin: "D4"
  device_name: "Room Environment Sensor"
  readings:
    - name: temperature
      label: Temperature
      unit: "°C"
      device_class: temperature
    - name: humidity
      label: Humidity
      unit: "%"
      device_class: humidity
  read_interval_seconds: 2
```

Run real-hardware rather than fake-USB Compose mode so the container has the
required `/dev` and privileged GPIO access.

## Generate and start

After editing live config:

```bash
cd ~/labpulse-ha
./generate_compose.sh
./generate_homeassistant_config.sh
docker compose config
docker compose up -d --build
```

`generate_compose.sh` replaces `compose.yaml`. The Home Assistant generator
replaces generated YAML but preserves `.storage/lovelace` without an explicit
dashboard flag.

If Home Assistant was already running and generated package behavior changed,
restart it so it reloads YAML:

```bash
docker compose restart homeassistant
```

Check the stack:

```bash
docker compose ps
```

Expected fixed containers are `labpulse-homeassistant`, `labpulse-mqtt`, and
`labpulse-sms`. Each enabled service adds `labpulse-<service-slug>`.

## First Home Assistant startup

Open:

```text
http://<pi-ip>:8123
```

Create the initial account, then add the MQTT integration:

```text
Settings -> Devices & services -> Add integration -> MQTT
Broker: 127.0.0.1
Port: 1883
```

Home Assistant uses host networking. LabPulse Python containers use
`mosquitto:1883` on the Compose network; those addresses are intentionally
different.

Hardware services publish discovery for service health immediately and for a
reading after its first valid sample. On a fresh startup there is no registry
to resolve yet. Use the normal generator defaults, start the services, and wait
for discovery.

## Normal maintenance workflows

### Live config changed

```bash
cd ~/labpulse-ha
./generate_compose.sh
./generate_homeassistant_config.sh
docker compose up -d --build
docker compose restart homeassistant
```

### Repository Python/template/script source changed

Rerun bootstrap to copy the new repository state into the live directory, then
rebuild:

```bash
cd ~/LabPulse/docker_refactor
./setup_container_fs.sh
cd ~/labpulse-ha
docker compose up -d --build
```

Existing live config and the Home Assistant config directory are preserved,
although setup deliberately resets the starter dashboard because it invokes
the HA generator with `--reset-dashboard`. Back up a dashboard you care about
before using setup during layout development.

### Stop without deleting persistent data

```bash
cd ~/labpulse-ha
docker compose down
```

Mounted config, Mosquitto data, logs, and backups remain.

## Dashboard safety and commands

The live dashboard is `homeassistant/config/.storage/lovelace`. Normal
generation preserves it.

| Intent | Command |
| --- | --- |
| Regenerate YAML, preserve layout | `./generate_homeassistant_config.sh` |
| Save current layout | `./generate_homeassistant_config.sh --backup-dashboard` |
| Restore latest saved layout | `./generate_homeassistant_config.sh --load-dashboard` |
| Replace layout from the seed | `./generate_homeassistant_config.sh --reset-dashboard` |
| Save then test a new seed | `./generate_homeassistant_config.sh --backup-dashboard --reset-dashboard` |

Restart Home Assistant after restore/reset:

```bash
docker compose restart homeassistant
```

Dashboard backups contain only Lovelace layout:

```text
homeassistant_backups/dashboard-YYYYMMDD-HHMMSS/lovelace
homeassistant_backups/dashboard-latest/lovelace
```

They do not contain accounts, tokens, integrations, recorder history, or all
of `.storage`.

The shell wrapper rejects ambiguous combinations, including reset+load,
backup+load, reset+sync, and load+sync. A dashboard entity sync automatically
takes a backup.

## Optional entity-registry validation

Most installations never need this. Deterministic IDs work unless someone has
renamed MQTT entities in Home Assistant.

After all services have published discovery:

1. Install the WebSocket client:

   ```bash
   sudo apt install python3-websocket
   ```

2. Create a Home Assistant long-lived access token and expose it only for this
   shell:

   ```bash
   export LABPULSE_HA_TOKEN="<token>"
   ```

3. Validate registry identities:

   ```bash
   ./generate_homeassistant_config.sh --resolve-entities
   ```

If every actual ID equals its default, no dashboard change is needed. If an ID
was renamed, either rebuild the seed using current IDs:

```bash
./generate_homeassistant_config.sh --resolve-entities --reset-dashboard
```

or preserve layout and replace exact stale IDs:

```bash
./generate_homeassistant_config.sh \
  --resolve-entities --sync-dashboard-entities
```

Use `--ha-url` or `LABPULSE_HA_URL` if Home Assistant is not at
`http://127.0.0.1:8123`.

## Simulator workflow

Fake-USB bootstrap creates these stable links:

```text
/tmp/labpulse-fake-serial/pressure
/tmp/labpulse-fake-serial/pump_room
/tmp/labpulse-fake-serial/turbo_pump
/tmp/labpulse-fake-serial/room_environment
```

Start the background simulator before or alongside the containers:

```bash
cd ~/labpulse-ha
python3 simulate_serial.py start
docker compose up -d --build
```

Check it:

```bash
python3 simulate_serial.py status
```

Change one reading without recreating its pseudo-terminal:

```bash
python3 simulate_serial.py set pump_room.flow1 danger-low
python3 simulate_serial.py set pump_room.flow1 recover
python3 simulate_serial.py set pump_room.flow1 normal
python3 simulate_serial.py set pump_room.flow1 stale
```

Available states are:

```text
normal, recover, danger-low, danger-high, stale
```

Targets are:

```text
pressure_monitor.pressure
pump_room.flow1
pump_room.flow2
pump_room.temp0
pump_room.temp1
pump_room.temp2
pump_room.temp3
turbo_pump.flow1
turbo_pump.flow2
turbo_pump.temp0
turbo_pump.temp1
turbo_pump.temp2
turbo_pump.temp3
room_environment.temperature
room_environment.humidity
```

Management commands:

```bash
python3 simulate_serial.py clear pump_room.flow1
python3 simulate_serial.py reset
python3 simulate_serial.py status
python3 simulate_serial.py stop
```

You can start with initial scenarios:

```bash
python3 simulate_serial.py start \
  --scenario pump_room.flow1=danger-low \
  --scenario room_environment.temperature=danger-high
```

Scenario changes affect sensor facts only. Home Assistant still applies its
configured observation window, required percentage, stale timeout, and recovery
timer. `stale` keeps the link alive but stops changing that entity’s value, so
wait for Maximum Reading Age before expecting Sensor Fault.

## SMS setup and testing

### Dry-run mode

Keep this during development:

```yaml
sms:
  dry_run: true
  recipients:
    - "+447700900000"
```

The SMS worker validates and queues requests but logs a masked recipient instead
of using a modem.

Publish a manual test with a new request ID each time:

```bash
docker compose exec mosquitto mosquitto_pub \
  -h mosquitto -q 1 -t labpulse/sms/send \
  -m '{"request_id":"manual-test-001","event":"test","service":"manual","reading":"sms","state":"Test","title":"LabPulse SMS test","message":"Manual test from LabPulse"}'
```

Watch results:

```bash
docker compose logs -f labpulse-sms
```

Reusing the same ID is correctly rejected as a duplicate.

### Real modem mode

On the Pi host:

```bash
sudo apt update
sudo apt install -y modemmanager
sudo systemctl enable --now ModemManager
mmcli -L
```

Set `sms.dry_run: false` and real international recipients in the live config,
then regenerate Compose so the worker receives D-Bus/device access:

```bash
cd ~/labpulse-ha
./generate_compose.sh
docker compose up -d --build
docker compose exec labpulse-sms mmcli -L
```

Useful topics:

```text
send:    labpulse/sms/send
status:  labpulse/sms/status
result:  labpulse/sms/result/<request_id>
```

Accepted IDs are persisted for 24 hours in
`logs/sms_processed_requests.json`; a 30-second per-event cooldown reduces
alert floods.

## Logs and inspection commands

```bash
cd ~/labpulse-ha
docker compose ps
docker compose logs -f
docker compose logs -f homeassistant
docker compose logs -f mosquitto
docker compose logs -f labpulse-sms
docker compose logs -f labpulse-pressure-monitor
```

Python services also write persistent logs under `~/labpulse-ha/logs/`, for
example `pressure_monitor.log`, `pump_room.log`, and `sms.log`.

Subscribe to all local MQTT traffic:

```bash
docker run --rm -it --network host eclipse-mosquitto:2 \
  mosquitto_sub -h 127.0.0.1 -p 1883 -t '#' -v
```

Discovery only:

```bash
docker run --rm -it --network host eclipse-mosquitto:2 \
  mosquitto_sub -h 127.0.0.1 -p 1883 -t 'homeassistant/#' -v
```

## Troubleshoot in data-flow order

### 1. A service container is missing

```bash
docker compose ps
docker compose config
```

Confirm its live config has `enabled: true`, then regenerate Compose and
recreate containers.

### 2. Hardware is missing

Real:

```bash
ls -l /dev/serial/by-id/
dmesg | tail -50
```

Fake:

```bash
python3 simulate_serial.py status
ls -l /tmp/labpulse-fake-serial/
```

Then inspect the specific service log. If the host path exists but the
container cannot see it, verify Compose was generated in the correct real/fake
mode and recreate that container.

### 3. The driver connects but there are no readings

Use the hardware CLI inside a suitable Python environment with `--print`, or
inspect service logs. Compare raw serial output to
[ARDUINO_AND_CPP.md](ARDUINO_AND_CPP.md).

Parser keys must exactly match `readings[].name`. Unconfigured keys are
deliberately ignored by the publisher.

### 4. MQTT has no values

Confirm live config uses:

```yaml
mqtt:
  broker: mosquitto
  port: 1883
```

`localhost` inside a sensor container points back to that container. Check
Mosquitto logs and use the MQTT subscription command above.

### 5. Home Assistant has no sensor entity

Confirm the MQTT integration uses `127.0.0.1:1883`. Reading discovery is not
published until the first valid reading. Inspect discovery traffic and:

```text
~/labpulse-ha/homeassistant/config/labpulse_entity_map.yaml
```

### 6. A dashboard card has the wrong entity

Compare its ID with `labpulse_entity_map.yaml`. If an entity was manually
renamed, use registry validation/synchronization. Edit normal live layout in the
Home Assistant UI. Edit `dashboard_seed.yaml` only for the layout produced by
an explicit reset.

### 7. Alarm behavior is wrong

Check, in order:

1. current reading is numeric and fresh
2. service status entity is online
3. Alarm Mode
4. minimum/maximum threshold
5. danger/recovery/fault zone entities
6. Observed Danger percentage
7. Required Danger percentage and Observation Window
8. Required Recovery time and deadband
9. persistent Alarm State

Inspect generated behavior at:

```text
homeassistant/config/packages/labpulse_generated.yaml
```

The editable source is `templates/alarm/alarm_logic.yaml`. Remember that mute
suppresses notifications/SMS only; it does not freeze state.

### 8. SMS does not arrive

Check the alert automation published a valid request, then inspect
`labpulse-sms` logs, `labpulse/sms/status`, and the per-request result topic.
For real delivery, compare `mmcli -L` on the host and inside the container.

### 9. Generated files cannot be written

An earlier `sudo` run may own the live directory:

```bash
sudo chown -R "$(id -u):$(id -g)" ~/labpulse-ha
```

Run normal setup as the intended user rather than with `sudo`.

## Repository tests

From the repository root on a development machine:

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

Run tests nearest a small change. For shared IDs, topics, config, or generated
contracts, run every consumer test.

## Destructive recovery

Deleting `homeassistant/config` removes accounts, tokens, integrations,
dashboard state, helpers, and local Home Assistant state—not only generated
LabPulse files. Prefer dashboard backup/restore or regeneration first.

For an intentionally fresh Home Assistant installation only:

```bash
cd ~/labpulse-ha
docker compose stop homeassistant
rm -rf ~/labpulse-ha/homeassistant/config
mkdir -p ~/labpulse-ha/homeassistant/config
./generate_homeassistant_config.sh --reset-dashboard
docker compose up -d homeassistant
```

You must create the Home Assistant user and MQTT integration again.

