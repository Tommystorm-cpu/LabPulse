# Setup and Troubleshooting

This is the operator guide for the Docker refactor: install it on a Raspberry
Pi, configure real or simulated sensors, start the stack, maintain the Home
Assistant dashboard safely, test SMS, and diagnose failures in data-flow order.

## The rule that prevents config confusion

Install the LabPulse command with pipx, then run its bootstrap. After bootstrap,
operate the system from the generated live directory:

```text
Setup command:      labpulse setup
Control command:    labpulse
Live installation:  ~/labpulse-live/
Live config:         ~/labpulse-live/config.yaml
```

The packaged `config.yaml` is a starter copied only when the live config does
not exist. Updating the package does not replace an already installed Pi's live
configuration.

## Prerequisites

The Pi needs:

- Docker Engine with the Compose plugin
- Python 3 with virtual-environment support (`python3-full` on Raspberry Pi OS)
- pipx
- stable Arduino serial paths for real hardware, or fake-USB mode

Real SMS delivery additionally needs a working ModemManager/modem on the host.

## First installation

### Real hardware

From a repository checkout, until LabPulse is published:

```bash
cd ~/LabPulse
pipx install .
labpulse setup
```

After publication, install with `pipx install labpulse` instead. The
`labpulse setup` command creates or refreshes `~/labpulse-live`, copies the
installed Python package and generators, preserves existing live config,
generates Compose and Home Assistant files, and seeds the dashboard. It also creates the private
`~/labpulse-live/.venv` environment and installs the bounded dependencies in
`requirements-host.txt`. The generator, editor, USB setup, and simulator
commands select that interpreter automatically. Do not use `sudo pip`,
`--break-system-packages`, or manually install Pydantic into system Python.

The package installs a single control command for normal operation:

```bash
labpulse up                       # start all containers
labpulse up --build               # rebuild local images and start
labpulse down                     # stop without deleting persistent data
labpulse restart                  # restart all stack containers
labpulse restart homeassistant    # restart one service
labpulse ps                       # show container status
labpulse ps --all                 # include stopped containers
labpulse logs                     # show logs from all services
labpulse logs -f homeassistant    # follow one service
labpulse edit                     # edit, validate, regenerate, and apply config
labpulse open                     # open http://localhost:8123 in a browser
labpulse firmware                 # show firmware source and download links
labpulse help                     # show general command help
labpulse help restart             # explain one command
```

The equivalent standalone aliases are `labpulse-up`, `labpulse-down`, `labpulse-restart`,
`labpulse-ps`, `labpulse-logs`, `labpulse-edit`, and `labpulse-open`. Commands target
`~/labpulse-live` from any working directory. Set `LABPULSE_LIVE_DIR` or pass
`--live-dir DIR` for an alternate installation. The older `labpulse-setup`
entry point remains available temporarily, but new workflows use
`labpulse setup`.

### Simulated hardware

```bash
cd ~/LabPulse
pipx install .
labpulse setup --fake-usb
```

Fake mode derives `~/labpulse-live/config.fake.yaml` without altering the
real-hardware settings in `config.yaml`. It changes configured serial paths to
pseudo-terminal links, moves the room-environment DHT11 to simulated serial,
and converts the enabled `power_detection` service from X1200/I2C to the
`ups_monitor` pseudo-serial endpoint. Service names, measurements, display metadata,
power timings, and Home Assistant identities remain unchanged.

If `config.yaml` has no active power service—as with the commented starter
example—fake mode adds a complete enabled `ups_monitor` block to
`config.fake.yaml` using documented simulator values.

The generated fake Compose file mounts `config.fake.yaml` as
`/app/config.yaml`. After editing the real source config, rerun
`labpulse setup --fake-usb` to refresh the derived file. See
[Simulator workflow](#simulator-workflow).

### Alternate live directory

```bash
labpulse --live-dir /path/to/labpulse-live setup
```

### Setup backups

`--backup` makes timestamped copies before setup replaces generated/copied
files:

```bash
labpulse setup --backup
```

It is not required for the live config: setup always preserves an existing
`config.yaml`.

## Generated live layout

```text
~/labpulse-live/
  config.yaml                         edit this
  compose.yaml                        generated
  edit_config.sh                      guarded edit, validate, and refresh workflow
  generate_compose.sh
  generate_homeassistant_config.sh
  simulate_serial.py
  setup_usb_devices.py
  requirements-host.txt                bounded host tooling dependencies
  .venv/                               setup-managed; do not edit or activate

  labpulse-python/
    Dockerfile
    requirements.txt
    labpulse/
      common/
      hardware/
      homeassistant/
      sms/

  homeassistant/config/
    configuration.yaml                generated
    automations.yaml                  UI-owned; created only if absent
    scripts.yaml                      UI-owned; created only if absent
    scenes.yaml                       UI-owned; created only if absent
    labpulse-dashboard.yaml           generated YAML-mode dashboard
    packages/labpulse_generated.yaml  generated alarm package
  mosquitto/config/
  mosquitto/data/
  mosquitto/log/
  logs/
```

## Configure the live system

```bash
cd ~/labpulse-live
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
  test_recipients:
    - "+447700900001"

service_health:
  fault_confirm_seconds: 10
  recovery_confirm_seconds: 15

setups:
  compressed_air:
    label: "Compressed Air"
    icon: "mdi:gauge"
    order: 10

services:
  pressure_monitor:
    enabled: true
    driver:
      type: labpulse.serial_pipe
      options:
        port: "/dev/serial/by-id/usb-Arduino_..."
        baud_rate: 9600
    device_name: "Air Pressure Sensor Hub"
    measurements:
      - name: pressure
        label: Pressure
        setups: [compressed_air]
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
| `service_health.fault_confirm_seconds` | Continuous whole-service failure required before one hub alert; default 10 |
| `service_health.recovery_confirm_seconds` | Continuous absence of a whole-service failure required before one recovery; default 15 |
| service key | Stable machine ID used in containers, MQTT, and HA entities |
| `enabled` | Whether Compose and HA generation include the service |
| `driver.type` | Stable registered ID: `labpulse.serial_pipe`, `labpulse.dht11`, or `labpulse.x1200` |
| `driver.options` | Driver-owned settings validated for the selected type |
| `driver.options.port`, `baud_rate` | Serial endpoint and baud rate; use a stable real path or the configured fake path |
| `driver.options.pin` | DHT11 Blinka board name such as `D4` |
| `device_name` | User-facing HA device label |
| `setups` | Logical experimental setups and their presentation metadata |
| `measurements[].name` | Stable key; must match the serial or hardware-driver output |
| `measurements[].label` | User-facing label |
| `measurements[].setups` | Required non-empty setup-ID list for ordinary measurements; omit it for dedicated `power_detection` telemetry |
| `measurements[].subcategory` | Optional presentation subgroup within a setup section |
| `measurements[].unit` | Exact unit published to Home Assistant; LabPulse does not convert it |
| `measurements[].device_class` | Internal measurement meaning and default-icon selection; not sent to Home Assistant |
| `measurements[].icon` | Optional validated `mdi:` override for the derived Home Assistant entity icon |
| `measurements[].state_class` | MQTT statistics metadata; defaults to `measurement` |
| `reconnect_interval_seconds` | Delay between serial, GPIO, or I2C reinitialization attempts |
| `read_interval_seconds` | Minimum interval for GPIO or I2C reads |
| `maximum_measurement_age_seconds` | Seconds without an MQTT sample before an ordinary measurement becomes unavailable; default 300 |
| X1200 `driver.options` | I2C `bus`, verified `address: 0x36`, `gpio_chip`, `gpio_line`, and mains polarity |
| `power_detection` | Home Assistant outage and recovery confirmation timings |

Default icons are derived from common device classes such as `temperature`,
`pressure`, `humidity`, `volume_flow_rate`, `voltage`, and `battery`. Unknown
classes use `mdi:chart-line`. Set `icon: "mdi:..."` on a measurement when a
different visual is clearer. `state_class` defaults to `measurement`; set it
to `null` to omit it. Alarm
thresholds, modes, mute state, and timing are restart-persistent Home Assistant
helpers, not hardware config fields. From the dashboard's Alarm Setup landing
page, open the required setup, press **Configure** on its measurement row, then set that
measurement's alarm mode, Min, Max, and Deadband. Observation window, required
danger percentage, and required recovery duration also belong to that measurement.
Use **Close** to collapse the editor and the subview back button to return to
Alarm Setup. In **Group Alarm Settings**, first choose a target, then switch on
only the common values or compatible recovery-deadband families that should change.
Its value input appears only after the matching **Change** switch is turned on.
Review the exact list before confirming Apply; unchecked values are never written.

On a fresh installation, ordinary-measurement alarm modes begin Disabled and the
global notification mute is switched on automatically. Set and test all alarm
controls before switching off the global mute. Home Assistant then restores
those helper values on later restarts. Dedicated UPS power detection remains in
`config.yaml`.

Each measurement receives safe timing values once when its helpers are first
created: 70% required danger, a 120-second observation window, and a
120-second recovery period. Later edits survive restarts and regeneration.
The bulk editor uses the same values as its initial scratch inputs.

Power outage and restoration confirmation periods are static settings in
`power_detection`. The defaults are three seconds absent and five seconds
present. `maximum_measurement_age_seconds` controls MQTT expiry for the raw GPIO
and battery measurements. Voltage and percentage remain dashboard telemetry only.
See [POWER_MONITOR_TEST_PI.md](POWER_MONITOR_TEST_PI.md) for the complete safe
acceptance run.

Hardware containers publish `offline` through a retained MQTT Last Will when
their process or broker connection disappears. Home Assistant also treats
`disconnected`, `reconnecting`, `error`, `unknown`, and `unavailable` as
whole-service failures. During a confirmed service fault, individual measurements
may display unavailable but do not each send stale-measurement messages. An
isolated stale measurement still alerts normally while its service is healthy.
Before planned maintenance, use the global notification mute if a container is
expected to remain stopped longer than the service-health confirmation period.

Physical services follow their order under `services` in `config.yaml`, and
`device_name` supplies the hub heading. There is no separate service `display`
block. Setup membership and measurement subcategories describe the logical Monitor
layout independently of the physical hub used for Diagnostics.

At the top of Monitor's first column, **Active Problems** lists confirmed hub
faults, persistent measurement `Danger`/`Sensor Fault` states, and power `On
Battery`/`Sensor Fault` states. It deliberately ignores instantaneous threshold
zone changes, is hidden while healthy, and cannot add or remove a masonry
column. Individually muted measurements and measurements owned by a muted setup are
omitted; the global mute does not hide problems. A shared measurement appears only
once and is hidden if any owning setup is muted, matching its single alert.

The Alarm Setup landing page puts setup configuration first, followed by global
delivery controls and a group editor that stays collapsed until opened. Each non-empty setup row
shows its measurement count, an explicit **Mute notifications** or **Unmute
notifications** action, and a labelled Configure action. Raw helper states are
hidden because an `off` muted flag means notifications are active. The mute is
repeated inside the setup subview.
Dedicated power monitoring has its own link. Inside a setup, native screen
conditions choose a single-row desktop summary or deliberately wrapped mobile
summary for each measurement. The closed rows have no grey section background;
Configure/Close stays at the right on desktop and becomes full-width on mobile.
Measurement icons come from each MQTT entity's device class. Each collapsed row
shows and controls that measurement's notification state; recovery deadband
remains available inside Configure. The inline editor
uses side-by-side behaviour and timing cards on desktop, stacked cards on mobile,
and a compact live-status block. Physical Diagnostics uses Sections with one
compact section per hub: connection, side-by-side health indicators,
latest raw measurements, and dedicated power lifecycle information where applicable.
**Service Health** follows the immediate connection-derived problem signal;
**Confirmed service fault** appears only after the configured fault delay and
remains active until the configured recovery delay has completed.

**Mute all
notifications** suppresses Home Assistant notifications and SMS without
changing any setup, per-measurement, or power mute helper. Turning it off therefore
leaves those independent choices unchanged. Each non-empty setup section has a
**Mute setup notifications** control. It suppresses ordinary measurement alerts for
that setup without changing the measurements' individual mute controls. Physical
sensor-hub health and dedicated power alerts are not controlled by setup mutes.

A measurement shared by several setups still produces one physical alert. That
alert remains enabled while any owning setup is unmuted and is suppressed only
when every owning setup is muted. Before enabling a mute on a setup containing
shared measurements, the dashboard names the affected measurements and warns
that they will remain unmuted while another setup using them is unmuted. The
warning requires confirmation only while muting; unmuting is immediate.

**Test mode** prefixes notification titles
with `[TEST]` and routes SMS requests only to `sms.test_recipients`; alarm state
calculation and thresholds are unchanged. Test mode initializes to **on** after
every Home Assistant start. An operator must deliberately turn it off before
normal recipients can receive alerts.

**Send phone book notification** opens a confirmation prompt before publishing
the standard phone-book notice. It uses the same safe routing as every other
SMS: Test mode sends only to `sms.test_recipients`, normal mode sends to
`sms.recipients`, and numbers that have sent `UNSUBSCRIBE` are excluded in
either mode. The action sends nothing while **Mute all notifications** is on.

Assign the same `measurements[].subcategory` to related measurements. Subcategories
preserve the order in which their names first appear. Use operational context
such as `Cooling Water` or `Room Conditions`; `device_class` separately
describes measurement type. Subcategorization is presentation only: measurements
retain their service health, MQTT identity, setup membership, and alarm
configuration.

### Stable names

Changing labels is safe. Changing a service key or `measurements[].name` creates a
new identity, affecting MQTT topics, Home Assistant entities, generated
helpers, dashboard references, and history.

### Real serial paths

Use the interactive helper instead of guessing which Arduino owns each Linux
device name. Start with every serial USB device plugged in and stop the Compose
stack if it is already running:

```bash
cd ~/labpulse-live
docker compose stop
./setup_usb_devices.py --config config.yaml
```

For every enabled `driver.type: labpulse.serial_pipe` service, the helper asks you to unplug its
device, detects the one `/dev/serial/by-id/...` entry that disappeared, then
asks you to replug it and verifies that the same stable path returned. It
aborts rather than guessing if zero or multiple devices disappear. After all
devices are identified it shows the complete mapping and asks before changing
anything.

The write is surgical: only assigned `driver.options.port` lines change. Other manual
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
  driver:
    type: labpulse.dht11
    options:
      pin: "D4"
  device_name: "Room Environment Sensor"
  measurements:
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
  maximum_measurement_age_seconds: 300
```

Run real-hardware rather than fake-USB Compose mode so the container has the
required `/dev` and privileged GPIO access.

The DHT worker uses `use_pulseio=True`, as verified on the live Raspberry Pi.
Only that worker should open the GPIO chip. If `fuser -v /dev/gpiochip0` lists
serial or I2C LabPulse workers, rebuild those images from current source; the
driver factory lazy-loads hardware modules so unrelated workers cannot claim
GPIO resources.

Individual DHT timing misses are expected and do not immediately change service
health. If no valid sample arrives for `maximum_measurement_age_seconds`, the
service status changes to `error` and MQTT expiry makes both measurements
unavailable. A later valid sample restores `online` automatically. Unexpected
GPIO/library failures are classified by the driver; the central hardware runner
releases the device and retries initialization every
`reconnect_interval_seconds`. It also limits routine missing-sensor warnings to
one per minute so a disconnected sensor cannot flood persistent logs.

## Generate and start

After editing live config:

```bash
cd ~/labpulse-live
./generate_compose.sh
./generate_homeassistant_config.sh
docker compose config
docker compose up -d --build
```

`generate_compose.sh` replaces `compose.yaml`. The Home Assistant generator
replaces its generated YAML, including `labpulse-dashboard.yaml`.

If Home Assistant was already running and generated package behavior changed,
restart it so it reloads YAML:

```bash
docker compose restart homeassistant
```

After Home Assistant is ready, refresh the LabPulse dashboard in the browser.
If a card is blank or reports an unknown type or feature after a Home Assistant
upgrade, check the browser console and Home Assistant logs, then compare the
generated card's `type` and `features` with the current official dashboard
documentation. The generated file should contain no `custom:` type or Lovelace
resource registration; a failure therefore indicates a renamed or unsupported
native feature rather than a missing HACS package.

Check the stack:

```bash
labpulse ps
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

LabPulse treats each measurement's configured `unit` as part of its data
contract. MQTT discovery publishes that exact unit and an explicit icon, but
does not publish Home Assistant's convertible sensor `device_class`; values
such as Celsius, Fahrenheit, bar, and psi therefore remain exactly as the
hardware service reports them. The configured `device_class` remains available
inside LabPulse for alarm grouping and supplies the default icon. Add an
optional measurement-level `icon: "mdi:..."` to override that default.

Hardware services publish discovery for service health immediately and for a
measurement after its first valid sample. On a fresh startup there is no registry
to resolve yet. Use the normal generator defaults, start the services, and wait
for discovery.

## Normal maintenance workflows

### Live config changed

```bash
labpulse edit
```

The editor works on a temporary copy beside the live config so validation
failures cannot replace the source of truth. Set `VISUAL` or `EDITOR` to choose
an editor; otherwise it uses `nano`. After a valid change it keeps one rolling
`config.yaml.edit-backup`, exercises both generators, runs Home Assistant's own
configuration check, and recreates the Compose services with `sudo docker`.
Its final message reminds the operator to review the conditional **Global Mute
Applied** and **Test Mode Applied** banners on Monitor before changing either
notification safeguard.

### Installed package or development source changed

Upgrade or reinstall the pipx package, rerun bootstrap to copy that package
state into the live directory, then rebuild:

```bash
cd ~/LabPulse
pipx install --editable . --force
labpulse setup
labpulse up --build
```

Existing live config and the Home Assistant config directory are preserved.
Setup regenerates and registers `labpulse-dashboard.yaml`.

### Stop without deleting persistent data

```bash
labpulse down
```

Mounted config, Mosquitto data, and logs remain.

## Dashboard safety and commands

`homeassistant/config/labpulse-dashboard.yaml` is a generated file. Every
normal generation replaces it from validated `config.yaml`, the canonical
measurement catalog, and repository dashboard rules. Edit setups,
`subcategory`, labels, and measurement metadata in `config.yaml`; make permanent
layout changes in `src/labpulse/homeassistant/dashboard/` or its templates.
Home Assistant UI edits are not the source of truth for this YAML-mode
dashboard.

| Intent | Command |
| --- | --- |
| Regenerate configuration and the LabPulse dashboard | `./generate_homeassistant_config.sh` |

Normal generation requires neither a running Home Assistant instance nor a
token. Restart Home Assistant after regenerating package or registration YAML:

```bash
docker compose restart homeassistant
```

LabPulse does not mutate, back up, restore, or synchronize Home Assistant's
private dashboard state. Back up the complete Home Assistant config directory
using the deployment's normal backup policy when account, integration, helper,
and recorder recovery is required.

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
cd ~/labpulse-live
./simulate_serial.py start
docker compose up -d --build
```

Check it:

```bash
./simulate_serial.py status
```

### Test the USB assignment helper with fake devices

Run the helper in one terminal:

```bash
cd ~/labpulse-live
./setup_usb_devices.py --config config.fake.yaml --fake-usb --dry-run
```

It first asks for all devices to be connected. In a second terminal, simulate
each requested unplug and replug using the service name printed by the helper:

```bash
./simulate_serial.py disconnect pressure_monitor
./simulate_serial.py connect pressure_monitor

./simulate_serial.py disconnect pump_room
./simulate_serial.py connect pump_room
```

The same commands work for `turbo_pump`, `room_environment`, and `ups_monitor`.
`disconnect` closes that device's PTY and removes only its stable fake link;
the simulator and every other endpoint keep running. `connect` creates a new
PTY at the same stable public path. Use `status` at any point to see connected
and disconnected endpoints.

Remove `--dry-run` to exercise the confirmation and surgical config write.
Because `config.fake.yaml` is derived, rerunning `labpulse setup --fake-usb`
will recreate its deterministic fake paths later.

Change one measurement without recreating its pseudo-terminal:

```bash
./simulate_serial.py set pump_room.flow1 danger-low
./simulate_serial.py set pump_room.flow1 recover
./simulate_serial.py set pump_room.flow1 normal
./simulate_serial.py set pump_room.flow1 stale
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
./simulate_serial.py clear pump_room.flow1
./simulate_serial.py reset
./simulate_serial.py disconnect pump_room
./simulate_serial.py connect pump_room
./simulate_serial.py status
./simulate_serial.py stop
```

You can start with initial scenarios:

```bash
./simulate_serial.py start \
  --scenario pump_room.flow1=danger-low \
  --scenario room_environment.temperature=danger-high
```

Scenario changes affect sensor facts only. Home Assistant still applies its
configured observation window, required percentage, MQTT expiry, and recovery
timer. `stale` keeps the link and peer measurements active but stops publishing the
selected measurement. Wait for that service's `maximum_measurement_age_seconds` before
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
  -m '{"request_id":"manual-test-001","event":"test","service":"manual","measurement":"sms","state":"Test","title":"[TEST] LabPulse SMS test","message":"Manual test from LabPulse","test_mode":true}'
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
cd ~/labpulse-live
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
labpulse ps
labpulse logs -f
labpulse logs -f homeassistant
labpulse logs -f mosquitto
labpulse logs -f labpulse-sms
labpulse logs -f labpulse-pressure-monitor
```

Python services also write persistent logs under `~/labpulse-live/logs/`, for
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

### The managed Python environment is missing or invalid

Rerun `labpulse setup`. It safely preserves the live config and recreates or
refreshes `~/labpulse-live/.venv`. If environment creation itself fails,
install `python3-full` through `apt` and rerun setup.
Do not work around the error with a global `pip` installation.

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
./simulate_serial.py status
ls -l /tmp/labpulse-fake-serial/
```

Then inspect the specific service log. If the host path exists but the
container cannot see it, verify Compose was generated in the correct real/fake
mode and recreate that container.

### 3. The driver connects but there are no measurements

Use the hardware CLI inside a suitable Python environment with `--print`, or
inspect service logs. Compare raw serial output to
[ARDUINO_AND_CPP.md](ARDUINO_AND_CPP.md).

Parser keys must exactly match `measurements[].name`. Unconfigured keys are
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

Confirm the MQTT integration uses `127.0.0.1:1883`. Measurement discovery is not
published until the first valid measurement. Inspect MQTT discovery traffic and
the Entities page in Home Assistant.

### 6. A dashboard card has the wrong entity

Compare the card ID in `labpulse-dashboard.yaml` with the entity shown in Home
Assistant Developer Tools. LabPulse entity IDs are generated infrastructure and
must not be renamed through Home Assistant. If a
conflicting entity acquired a numeric suffix, remove the stale conflicting
registry entry and let MQTT discovery recreate the deterministic ID. Permanent
layout changes belong in `src/labpulse/homeassistant/dashboard/` or
`templates/dashboard/cards.yaml`; regeneration overwrites the expanded YAML.

### 7. Alarm behavior is wrong

Check, in order:

1. current measurement is numeric and fresh
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
~/labpulse-live/labpulse-python/labpulse/common/sms_templates.yaml
```

Alert entries contain Home Assistant Jinja expressions, so preserve their
quoting, `[[ ... ]]` generator placeholders, and the `{current_measurement}` worker
placeholder present in every alert body. After editing the file, regenerate
and validate Home Assistant YAML, then rebuild only the SMS worker:

```bash
cd ~/labpulse-live
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
sudo chown -R "$(id -u):$(id -g)" ~/labpulse-live
```

Run normal setup as the intended user rather than with `sudo`.

## Repository tests

From the repository root on a development machine:

```powershell
python .\testing\test_serial_parser.py
python .\testing\test_hardware_factory.py
python .\testing\test_dht11_driver.py
python .\testing\test_simulate_serial.py
python .\testing\test_serial_driver.py
python .\testing\test_homeassistant_publisher.py
python .\testing\test_homeassistant_entities.py
python .\testing\test_homeassistant_generator.py
python .\testing\test_setup_grouping.py
python .\testing\test_yaml_dashboard.py
python .\testing\test_notification_context.py
python .\testing\test_sms_container.py
python .\testing\test_common_contracts.py
python .\testing\test_deployment_generation.py
```

Run tests nearest a small change. For shared IDs, topics, config, or generated
contracts, run every consumer test.

## Destructive recovery

Deleting `homeassistant/config` removes accounts, tokens, integrations,
dashboard state, helpers, and local Home Assistant state—not only generated
LabPulse files. Prefer normal regeneration first.

For an intentionally fresh Home Assistant installation only:

```bash
cd ~/labpulse-live
docker compose stop homeassistant
rm -rf ~/labpulse-live/homeassistant/config
mkdir -p ~/labpulse-live/homeassistant/config
./generate_homeassistant_config.sh
docker compose up -d homeassistant
```

You must create the Home Assistant user and MQTT integration again.
