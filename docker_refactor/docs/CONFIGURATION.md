# LabPulse Configuration

The live configuration file is:

```text
~/labpulse-ha/config.yaml
```

The repository copy is only a starter template:

```text
docker_refactor/config.yaml
```

Edit the live file on the Raspberry Pi. Then regenerate:

```bash
cd ~/labpulse-ha
./generate_compose.sh
./generate_homeassistant_config.sh
docker compose up -d --build
```

## What Belongs In Config

`config.yaml` owns:

- MQTT broker connection for LabPulse Python containers
- SMS backend and recipient numbers
- enabled sensor services
- serial ports and baud rates
- parser selection
- device names
- reading names, labels, units, and Home Assistant metadata
- dashboard display hints such as section, icon, and order

`config.yaml` does not own:

- alarm threshold values
- alert delay values after the helpers exist
- recovery delay values after the helpers exist
- live dashboard arrangement
- Home Assistant user accounts
- MQTT integration setup inside Home Assistant

Those are Home Assistant-owned operator settings.

## Top-Level Shape

```yaml
mqtt:
  broker: "mosquitto"
  port: 1883

sms:
  backend: "log"
  recipients:
    - "+447700900000"

services:
  pressure_monitor:
    enabled: true
    driver: serial
    parser: pressure
    serial_port: "/dev/serial/by-id/..."
    baud_rate: 9600
    device_name: "Air Pressure Sensor Hub"
    display:
      section: "Air Pressure"
      icon: "mdi:gauge"
      order: 40
    readings:
      - name: "pressure"
        label: "Pressure"
        unit: "bar"
        device_class: "pressure"
    reconnect_interval_seconds: 5
```

The Python runtime validates this shape with Pydantic in:

```text
labpulse_common/config.py
```

If a required field is missing or has the wrong type, the container exits with a
readable validation error.

## MQTT Settings

For the Docker setup, use:

```yaml
mqtt:
  broker: "mosquitto"
  port: 1883
```

Inside a Python container, `localhost` means that container, not the Mosquitto
container. `setup_container_fs.sh` converts the starter `localhost` value to
`mosquitto` for the live Docker config.

Home Assistant is different. Its MQTT integration should be configured in the
Home Assistant UI with:

```text
Broker: 127.0.0.1
Port: 1883
```

## SMS Settings

```yaml
sms:
  backend: "log"
  recipients:
    - "+447700900000"
```

`backend: "log"` is safe for development. It receives MQTT SMS requests and
logs what would have been sent.

`backend: "mmcli"` sends real SMS messages through ModemManager. Use it only on
the Pi with the modem installed. After switching to `mmcli`, regenerate Compose
so the SMS container gets `/run/dbus`, `/dev`, and privileged modem access:

```bash
cd ~/labpulse-ha
./generate_compose.sh
docker compose up -d --build
```

## Service Keys

Each key under `services:` is a stable machine identifier:

```yaml
services:
  pressure_monitor:
  pump_room:
  turbo_pump:
```

The key controls:

- generated container name
- MQTT topics
- MQTT discovery IDs
- Home Assistant entity IDs
- generated alarm helper IDs
- dashboard seed placeholders

Change service keys only when you are prepared to update Home Assistant
entities, dashboard references, and history expectations.

## Enable Or Disable A Service

```yaml
services:
  turbo_pump:
    enabled: false
```

Disabled services are skipped by:

- Compose generation
- Home Assistant render model
- generated dashboard seed
- generated alarm helpers and automations

Run both generators after changing `enabled`.

## Driver And Parser

```yaml
driver: serial
parser: pump_room
```

Implemented driver:

```text
serial
```

Reserved but not implemented yet:

```text
gpio
i2c
```

Current parser names include:

```text
pressure
pump_room
water
```

Parser output keys must match `readings[].name`.

Example:

```text
Serial line: Flow1: 2.4 L/min | Flow2: 3.1 L/min
Parser output: {"flow1": 2.4, "flow2": 3.1}
```

Config must contain:

```yaml
readings:
  - name: "flow1"
  - name: "flow2"
```

If the parser returns a key that is not configured, MQTT publishing ignores it
and logs a warning.

## Serial Port

Use stable USB paths for real hardware:

```yaml
serial_port: "/dev/serial/by-id/usb-Arduino__..."
```

Avoid final deployments that rely on:

```text
/dev/ttyACM0
/dev/ttyUSB0
```

Those names can change after a reboot or unplug/replug.

For fake USB testing, the paths are:

```yaml
pressure_monitor:
  serial_port: "/tmp/labpulse-fake-serial/pressure"
pump_room:
  serial_port: "/tmp/labpulse-fake-serial/pump_room"
turbo_pump:
  serial_port: "/tmp/labpulse-fake-serial/turbo_pump"
```

## Device Name

```yaml
device_name: "Pump Room Sensor Hub"
```

This is a user-facing Home Assistant device label. It is safe to edit.

It does not control stable entity IDs.

## Display Hints

```yaml
display:
  section: "Pump Room"
  icon: "mdi:water-pump"
  order: 20
```

These values are used by the Home Assistant generator.

`section` becomes the heading in a reset dashboard.

`icon` is used by heading cards in the reset dashboard.

`order` sorts service sections. Lower numbers appear earlier.

These are hints for the generated starter dashboard. After Home Assistant users
edit the live dashboard, normal generator runs preserve their UI layout.

## Readings

```yaml
readings:
  - name: "temp0"
    label: "Temperature 0"
    unit: "\u00b0C"
    device_class: "temperature"
```

`name` is the stable machine key. It must match parser output.

`label` is the user-facing display label. It is safe to edit.

`unit` becomes the Home Assistant MQTT `unit_of_measurement`.

`device_class` is passed through to Home Assistant MQTT discovery. Common values
include:

```text
temperature
pressure
humidity
```

`state_class` defaults to `measurement`, opting current readings into Home
Assistant long-term statistics. Set it explicitly to another valid Home
Assistant state class when needed, or to `null` to omit it from MQTT discovery.

## Reconnect Interval

```yaml
reconnect_interval_seconds: 5
```

The serial driver uses this when a USB serial device disappears or fails to
open. The service container stays alive and periodically tries to reconnect.

## Adding A New Serial Sensor Hub

1. Add a new service under `services:` in `~/labpulse-ha/config.yaml`.
2. Set `enabled: true`.
3. Use `driver: serial`.
4. Choose an existing parser or add a parser in `labpulse_common/parser.py`.
5. Set `serial_port` to a stable `/dev/serial/by-id/...` path.
6. Add `readings:` entries whose `name` values match parser output keys.
7. Run:

   ```bash
   cd ~/labpulse-ha
   ./generate_compose.sh
   ./generate_homeassistant_config.sh
   docker compose up -d --build
   ```

8. Wait for the service to publish MQTT discovery.
9. Check `homeassistant/config/labpulse_entity_map.yaml` for expected entity IDs.
10. Add or arrange new entities in the Home Assistant UI dashboard.

Use `--reset-dashboard` only if you intentionally want to replace the editable
dashboard with the generated starter layout.
