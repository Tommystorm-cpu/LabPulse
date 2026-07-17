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
Alarm defaults:      ~/labpulse-ha/alarm_defaults.json
```

The repository `docker_refactor/config.yaml` and `alarm_defaults.json` files
are starters copied only when their live counterparts do not exist. Editing a
repository starter does not change an already installed Pi.

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
packages and generators, preserves existing live config and alarm defaults,
generates Compose and Home Assistant files, and seeds the dashboard.

### Simulated hardware

```bash
cd ~/LabPulse/docker_refactor
chmod +x setup_container_fs.sh
./setup_container_fs.sh -fake_usb
```

Fake mode derives `~/labpulse-ha/config.fake.yaml` without altering the
real-hardware settings in `config.yaml`. It changes configured serial paths to
pseudo-terminal links, moves the room-environment DHT11 to simulated serial,
and converts the enabled `power_detection` service from MAX17043/I2C to the
`ups_monitor` pseudo-serial parser. Service names, readings, display metadata,
power timings, and Home Assistant identities remain unchanged.

If `config.yaml` has no active power service—as with the commented starter
example—fake mode adds a complete enabled `ups_monitor` block to
`config.fake.yaml` using documented simulator values.

The generated fake Compose file mounts `config.fake.yaml` as
`/app/config.yaml`. After editing the real source config, rerun
`setup_container_fs.sh -fake_usb` to refresh the derived file. See
[Simulator workflow](#simulator-workflow).

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
  alarm_defaults.json                 edit per-reading Min/Max/Deadband here
  compose.yaml                        generated
  generate_compose.sh
  generate_homeassistant_config.sh
  characterize_ups.sh                 interactive live UPS transition measurement
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
    .storage/lovelace*                editable dashboard stores

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
nano alarm_defaults.json
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
  test_recipients:
    - "+447700900001"

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
| `sms.test_recipients` | Separate international numbers used only while the Alarm Setup test-mode toggle is on |
| service key | Stable machine ID used in containers, MQTT, and HA entities |
| `enabled` | Whether Compose and HA generation include the service |
| `driver` | Implemented: `serial`, `gpio` with DHT11, or `i2c` with MAX17043-compatible UPS gauge |
| `parser` | Serial format selector: `pressure`, `pump_room`, `water`, `ups_simulator`, or generic pipe fallback |
| `serial_port` | Real stable path or fake path |
| `gpio_sensor` | Currently only `dht11` |
| `gpio_pin` | Blinka board name such as `D4` |
| `device_name` | User-facing HA device label |
| `display.section` | Reset-dashboard location heading; services with the same value share one Monitor section |
| `display.icon` | Reset-dashboard heading icon |
| `display.order` | Service order; lower numbers render first |
| `readings[].name` | Stable key; must match driver/parser output |
| `readings[].label` | User-facing label |
| `readings[].group` | Optional reset-dashboard subgroup; first appearance controls group order |
| `unit`, `device_class`, `state_class` | MQTT discovery metadata |
| `reconnect_interval_seconds` | Delay between serial, GPIO, or I2C reinitialization attempts |
| `read_interval_seconds` | Minimum interval for GPIO or I2C reads |
| `maximum_reading_age_seconds` | Seconds without an MQTT sample before an ordinary reading becomes unavailable; default 300 |
| `i2c_sensor`, `i2c_bus`, `i2c_address` | `max17043_ups`, bus 1, and the verified address `0x36` |
| `power_detection` | Characterized voltage drop/rise inference, absolute fallback, rebound lockout, optional charge recovery, and freshness timings |

`state_class` defaults to `measurement`; set it to `null` to omit it. Alarm
thresholds, modes, mute state, and timing are restart-persistent Home Assistant
helpers, not hardware config fields. Put one Min, Max, and Deadband entry in
`alarm_defaults.json` for every enabled ordinary reading:

```json
{
  "services": {
    "pump_room": {
      "roomtemp": {
        "minimum": 5.0,
        "maximum": 35.0,
        "deadband": 1.0
      }
    }
  }
}
```

Service and reading keys must match `config.yaml`. The generator rejects
missing enabled readings, unknown keys, `minimum >= maximum`, or an impossible
deadband. Dedicated UPS power detection stays in `config.yaml` and must not be
listed here.

These numbers seed the editable controls in **LabPulse Alarm Setup**. The
generator gives each reading's initializer a version derived from its JSON
entry. Dashboard edits therefore survive restarts and ordinary regeneration;
changing that JSON entry and regenerating applies the new three values once.

Power outage and recovery timings in `power_detection` seed Home Assistant
controls when that power service is first created. After initialization, those
two confirmation timings are edited in **LabPulse Alarm Setup** and persist
across restarts and automation reloads. Drop/rise thresholds, rolling windows,
rebound lockout, optional charge-rise threshold, absolute fallback, and maximum
evidence age remain live-config settings. The installed system's characterized
values are 0.050 V drop, 0.062 V rise, five-second window, and 17-second lockout.
Maximum UPS evidence age configures MQTT `expire_after` directly. See
[POWER_MONITOR_TEST_PI.md](POWER_MONITOR_TEST_PI.md) for the complete safe
acceptance run.

To measure the installed UPS rather than guessing transition thresholds, run
the interactive characterization helper from the live directory:

```bash
cd ~/labpulse-ha
./characterize_ups.sh
```

It uses `sudo docker`, verifies live MQTT voltage and charge telemetry, then
prompts for three controlled mains-off/on trials. Raw timestamped readings and
event markers are retained under `ups-characterisation/`. The final report
prints candidate drop, rise, lockout, and charge-trend settings only when the
trials separate them from normal noise and unplugged battery rebound. A final
five-minute mains-on observation captures delayed charger-settling steps that
the short pre-test baselines can miss. Use
`./characterize_ups.sh --quick` for a one-trial exploratory run; do not treat a
single trial as production calibration.

To group independent devices by physical location, give their services the
same `display.section`. The Monitor view renders one location heading and a
labelled subgroup for each service, while MQTT identities, service health, and
Alarm Setup sections remain independent. The first service in display order
provides the shared section icon.

The first Alarm Setup section contains two global delivery controls. **Mute all
notifications** suppresses Home Assistant notifications and SMS without
changing any per-reading or power mute helper. Turning it off therefore leaves
individually muted readings muted. **Test mode** prefixes notification titles
with `[TEST]` and routes SMS requests only to `sms.test_recipients`; alarm state
calculation and thresholds are unchanged. Test mode initializes to **on** after
every Home Assistant start. An operator must deliberately turn it off before
normal recipients can receive alerts.

Within a multi-purpose service, assign the same `readings[].group` to related
readings. Monitor renders one compact, untitled sensor card per group,
preserving the order in which group names first appear. The surrounding section
and service subheading identify the physical room and owning hub without adding
large titles to every card. Reading rows use the short configured label and do
not override the Home Assistant icon. Room-environment labels use `Room` as a
prefix to distinguish them from equipment temperatures and humidity. Grouping
is presentation only: readings retain their service health, MQTT identity, and
alarm configuration.

### Stable names

Changing labels is safe. Changing a service key or `readings[].name` creates a
new identity, affecting MQTT topics, Home Assistant entities, generated
helpers, dashboard references, and history.

### Real serial paths

Use the interactive helper instead of guessing which Arduino owns each Linux
device name. Start with every serial USB device plugged in and stop the Compose
stack if it is already running:

```bash
cd ~/labpulse-ha
docker compose stop
./setup_usb_devices.py --config config.yaml
```

For every enabled `driver: serial` service, the helper asks you to unplug its
device, detects the one `/dev/serial/by-id/...` entry that disappeared, then
asks you to replug it and verifies that the same stable path returned. It
aborts rather than guessing if zero or multiple devices disappear. After all
devices are identified it shows the complete mapping and asks before changing
anything.

The write is surgical: only assigned `serial_port` lines change. Other manual
config text and comments are preserved. The previous file is retained as the
single non-proliferating `config.yaml.usb-setup-backup`. After accepting:

```bash
./generate_compose.sh --config config.yaml
docker compose config
docker compose up -d --build
```

Avoid `/dev/ttyACM0` and `/dev/ttyUSB0`; discovery order can change them after
reboot or reconnect. If `/dev/serial/by-id` is absent or exposes fewer devices
than enabled serial services, correct the USB connection or permissions before
rerunning the helper.

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
  reconnect_interval_seconds: 5
  maximum_reading_age_seconds: 300
```

Run real-hardware rather than fake-USB Compose mode so the container has the
required `/dev` and privileged GPIO access.

The DHT worker uses `use_pulseio=True`, as verified on the live Raspberry Pi.
Only that worker should open the GPIO chip. If `fuser -v /dev/gpiochip0` lists
serial or I2C LabPulse workers, rebuild those images from current source; the
driver factory lazy-loads hardware modules so unrelated workers cannot claim
GPIO resources.

Individual DHT timing misses are expected and do not immediately change service
health. If no valid sample arrives for `maximum_reading_age_seconds`, the
service status changes to `error` and MQTT expiry makes both readings
unavailable. A later valid sample restores `online` automatically. Unexpected
GPIO/library failures release the device and retry initialization every
`reconnect_interval_seconds`; routine missing-sensor warnings are limited to
one per minute so a disconnected sensor cannot flood persistent logs.

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
replaces generated YAML but preserves the resolved Overview store without an explicit
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

The live Overview dashboard is resolved through
`homeassistant/config/.storage/lovelace_dashboards`. On older installations it
is `homeassistant/config/.storage/lovelace`; on current Home Assistant releases
it can be a named store such as `.storage/lovelace.lovelace`. Normal generation
preserves the resolved dashboard.

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

Home Assistant may create a newly registered Overview store as `root`. If a
reset reports that it cannot create or write the resolved dashboard, keep Home
Assistant stopped and apply the exact one-file `touch`/`chown` remedy printed by
the generator. Do not recursively change ownership of `.storage`.

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

### Test the USB assignment helper with fake devices

Run the helper in one terminal:

```bash
cd ~/labpulse-ha
./setup_usb_devices.py --config config.fake.yaml --fake-usb --dry-run
```

It first asks for all devices to be connected. In a second terminal, simulate
each requested unplug and replug using the service name printed by the helper:

```bash
python3 simulate_serial.py disconnect pressure_monitor
python3 simulate_serial.py connect pressure_monitor

python3 simulate_serial.py disconnect pump_room
python3 simulate_serial.py connect pump_room
```

The same commands work for `turbo_pump`, `room_environment`, and `ups_monitor`.
`disconnect` closes that device's PTY and removes only its stable fake link;
the simulator and every other endpoint keep running. `connect` creates a new
PTY at the same stable public path. Use `status` at any point to see connected
and disconnected endpoints.

Remove `--dry-run` to exercise the confirmation and surgical config write.
Because `config.fake.yaml` is derived, rerunning `setup_container_fs.sh
-fake_usb` will recreate its deterministic fake paths later.

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
pump_room.roomtemp
pump_room.roomhum
pump_room.press1
pump_room.press2
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
python3 simulate_serial.py disconnect pump_room
python3 simulate_serial.py connect pump_room
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
configured observation window, required percentage, MQTT expiry, and recovery
timer. `stale` keeps the link and peer readings active but stops publishing the
selected reading. Wait for that service's `maximum_reading_age_seconds` before
expecting Sensor Fault. Repeated identical samples remain healthy.

## SMS setup and testing

### Dry-run mode

Keep this during development:

```yaml
sms:
  dry_run: true
  recipients:
    - "+447700900000"
  test_recipients:
    - "+447700900001"
```

The SMS worker validates and queues requests but logs a masked recipient instead
of using a modem.

Inbound `SUBSCRIBE` and `UNSUBSCRIBE` commands are unavailable in dry-run mode
because that container deliberately has no modem access.

Publish a manual test with a new request ID each time:

```bash
docker compose exec mosquitto mosquitto_pub \
  -h mosquitto -q 1 -t labpulse/sms/send \
  -m '{"request_id":"manual-test-001","event":"test","service":"manual","reading":"sms","state":"Test","title":"[TEST] LabPulse SMS test","message":"Manual test from LabPulse","test_mode":true}'
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

Set `sms.dry_run: false` and real international normal/test recipients in the live config,
then regenerate Compose so the worker receives D-Bus/device access:

```bash
cd ~/labpulse-ha
./generate_compose.sh
docker compose up -d --build
docker compose exec labpulse-sms mmcli -L
```

In real modem mode, the SMS worker polls complete received SMS objects. A
number must exactly match an entry in either `sms.recipients` or
`sms.test_recipients` before it can issue a command:

- `UNSUBSCRIBE` suppresses all future LabPulse alerts to that number, in both
  normal and test mode, and sends a confirmation.
- `SUBSCRIBE` restores delivery in both modes and sends a confirmation.
- Matching is case-insensitive and ignores surrounding whitespace.
- Unknown numbers and unrecognized messages receive no reply.

Subscription choices persist in `logs/sms_subscriptions.json`. Processed
received SMS objects are removed from modem storage. Every warning SMS ends
with the opt-out/resubscribe instructions; recovery and sensor-fault messages
do not repeat the footer. After changing either configured recipient list,
restart `labpulse-sms` so both outbound routing and the inbound allow-list are
reloaded.

Verify the feature with one configured test number while Home Assistant Test
mode is on:

1. Send `UNSUBSCRIBE` to the modem number and wait for the confirmation.
2. Trigger a warning and confirm that number receives nothing.
3. Send `SUBSCRIBE` and wait for the confirmation.
4. Trigger a new warning and confirm delivery resumes.
5. Repeat after switching Test mode off to prove the choice spans both lists.

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

### Edit SMS wording

Every SMS title, body, formatting line, footer, and subscription confirmation
is stored in one live file:

```text
~/labpulse-ha/labpulse-python/labpulse_common/sms_templates.yaml
```

Alert entries contain Home Assistant Jinja expressions, so preserve their
quoting, `[[ ... ]]` generator placeholders, and the `{current_reading}` worker
placeholder present in every alert body. After editing the file, regenerate
Home Assistant YAML without a dashboard reset, validate it, then rebuild only
the SMS worker:

```bash
cd ~/labpulse-ha
./generate_homeassistant_config.sh
docker compose exec homeassistant python -m homeassistant --script check_config --config /config
docker compose up -d --build --force-recreate labpulse-sms
```

Restart Home Assistant, or reload its automations, to activate changed alert
templates. The generation command above preserves the current dashboard.

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
