# Hardware And Serial

This guide documents Arduino serial formats, DHT11 GPIO setup, parser
expectations, fake USB testing, and the stable USB path strategy for real
hardware.

## Serial Path Rule

For real deployments, prefer:

```text
/dev/serial/by-id/usb-Arduino__...
```

Avoid relying on:

```text
/dev/ttyACM0
/dev/ttyUSB0
```

The `ttyACM` and `ttyUSB` names are assigned by discovery order. They can change
after reboot, unplug/replug, or moving USB ports.

## Where Serial Paths Are Configured

Edit:

```text
~/labpulse-ha/config.yaml
```

Example:

```yaml
services:
  pressure_monitor:
    serial_port: "/dev/serial/by-id/usb-Arduino__..."
```

Then regenerate:

```bash
cd ~/labpulse-ha
./generate_compose.sh
docker compose up -d --build
```

Real USB mode mounts `/dev` into the Python containers.

## DHT11 GPIO Sensor

The DHT11 driver is configured as a normal service in:

```text
~/labpulse-ha/config.yaml
```

Example:

```yaml
services:
  room_environment:
    enabled: true
    driver: gpio
    gpio_sensor: dht11
    gpio_pin: "D4"
    device_name: "Room Environment Sensor"
    readings:
      - name: "temperature"
        label: "Temperature"
        unit: "\u00b0C"
        device_class: "temperature"
      - name: "humidity"
        label: "Humidity"
        unit: "%"
        device_class: "humidity"
    read_interval_seconds: 2
```

`gpio_pin` is the Adafruit Blinka board pin name. The old DHT setup used `D4`,
which maps to Raspberry Pi GPIO4.

After enabling the service:

```bash
cd ~/labpulse-ha
./generate_compose.sh
./generate_homeassistant_config.sh
docker compose up -d --build
```

Run without `-fake_usb` for real DHT11 testing, because the container needs
privileged `/dev` access for GPIO.

### Simulated Room Environment Input

On a test Pi without the DHT11 connected, use:

```yaml
services:
  room_environment:
    enabled: true
    driver: serial
    parser: pipe
    serial_port: "/tmp/labpulse-fake-serial/room_environment"
    baud_rate: 9600
```

`setup_container_fs.sh -fake_usb` applies this substitution automatically. The
room sensor then uses the normal serial driver and pipe parser. Change its
values through the running simulator service:

```bash
python3 simulate_serial.py set room_environment.temperature danger-high
python3 simulate_serial.py set room_environment.humidity danger-low
python3 simulate_serial.py set room_environment.temperature stale
```

## Fake USB Serial Testing

The simulator is:

```text
docker_refactor/simulate_serial.py
```

Run:

```bash
cd ~/LabPulse/docker_refactor
./setup_container_fs.sh -fake_usb
cd ~/labpulse-ha
python3 simulate_serial.py start
```

In another terminal:

```bash
cd ~/labpulse-ha
docker compose up -d --build
```

Fake serial paths:

```text
/tmp/labpulse-fake-serial/pressure
/tmp/labpulse-fake-serial/pump_room
/tmp/labpulse-fake-serial/turbo_pump
/tmp/labpulse-fake-serial/room_environment
```

To push a specific reading into an alarm test condition, issue a command to the
running simulator:

```bash
python3 simulate_serial.py set pressure_monitor.pressure danger-low
python3 simulate_serial.py set pump_room.flow1 danger-low
python3 simulate_serial.py set pump_room.temp0 danger-high
python3 simulate_serial.py set room_environment.temperature danger-high
python3 simulate_serial.py set pump_room.flow1 stale
```

The service keeps scenarios in memory and listens on a local Unix control
socket. Useful management commands are:

```bash
python3 simulate_serial.py status
python3 simulate_serial.py clear pump_room.flow1
python3 simulate_serial.py reset
python3 simulate_serial.py stop
```

Supported scenario states are `normal`, `recover`, `danger-low`, `danger-high`,
and `stale`. Active scenarios emit changing values that stay inside the chosen
zone, so Home Assistant does not mistake an alarm test for stale data. The
`stale` scenario emits one valid constant value, which keeps the fake serial
link alive while letting Home Assistant's `last_updated` age past the stale
timeout.

These only change the simulated sensor values; Home Assistant still uses its
editable alarm mode, observation window, maximum reading age, and required recovery time.

`generate_compose.sh` enables fake USB mounts if fake mode is requested or if
an enabled service's `serial_port` starts with `/tmp/labpulse-fake-serial`.

## Parser Rule

Arduino serial text must parse into keys that match `config.yaml`:

```text
serial text -> legacy_parsing/serial_parser.py -> {"reading_name": value}
```

The output key must exist in:

```yaml
readings:
  - name: "reading_name"
```

Unconfigured keys are ignored by MQTT publishing. This parser is an isolated
compatibility layer; new Arduino firmware should move toward one consistent,
machine-readable output contract so it can eventually be removed.

## Pressure Arduino

Source sketch:

```text
Arduino/Pressure_Arduino.cpp
```

Output:

```text
0.1034
```

Format:

```text
<pressure_mpa_with_4_decimal_places>
```

The Python pressure parser treats the value as MPa and converts to bar:

```text
bar = raw_value * 10.0
```

Configured reading:

```yaml
readings:
  - name: "pressure"
    label: "Pressure"
    unit: "bar"
    device_class: "pressure"
```

## Pump Room Arduino

Source sketch:

```text
Arduino/Pump_Room_Arduino.cpp
```

Typical output cycle:

```text
Flow1: 2.45 L/min | Flow2: 3.10 L/min
Temp0: 20.11C  Temp1: 20.22C  Temp2: 20.33C  Temp3: 20.44C
RoomTemp: 21.2C | RoomHum: 45.0% | Press1: 1.23 bar | Press2: 1.45 bar
```

The current config includes:

```text
flow1
flow2
temp0
temp1
temp2
temp3
```

If you want `roomtemp`, `roomhum`, `press1`, or `press2` published, add matching
`readings:` entries and tests for the parser behavior.

## Full Water Sensor / Turbo Pump Format

Source sketch:

```text
Arduino/full_water_sensor_code.cpp
```

The current sketch can emit flow and temperature in one combined line:

```text
Flow1: 2.45 L/min | Flow2: 3.10 L/minTemp0: 20.11C  Temp1: 20.22C  Temp2: 20.33C  Temp3: 20.44C
```

Notice there is no separator between:

```text
L/min
```

and:

```text
Temp0:
```

The Docker refactor parser is intentionally more tolerant of this than the old
Pi scripts. If the Arduino sketch is updated later, a cleaner format would be:

```text
Flow1: 2.45 L/min | Flow2: 3.10 L/min
Temp0: 20.11C  Temp1: 20.22C  Temp2: 20.33C  Temp3: 20.44C
```

## Temporary Flow Reader

Source sketch:

```text
Arduino/Water flow meter code/Temporary flow reader.cpp
```

Output:

```text
FlowRate:1.234,TotalLitres:0.567
```

This is not currently one of the main simulated LabPulse serial links.

## Arduino Edge Cases To Watch

Thermistor calculations can produce invalid values if a sensor is disconnected
or the analog voltage is near the edge of the ADC range. A symptom can be:

```text
-273.15 C
```

Future sketch-side hardening should reject impossible voltage readings before
printing them.

DHT sensors can occasionally return `NaN`. If the sketch prints:

```text
RoomTemp: nanC | RoomHum: nan%
```

the parser should ignore non-finite values rather than publishing them.

## Debugging Real USB

List stable paths:

```bash
ls -l /dev/serial/by-id/
```

Check kernel messages:

```bash
dmesg | tail -50
```

Check container logs:

```bash
cd ~/labpulse-ha
docker compose logs -f labpulse-pressure-monitor
```

If the host path exists but the container cannot read it:

1. Confirm Compose was regenerated in real USB mode.
2. Confirm `/dev:/dev` is mounted in `compose.yaml`.
3. Confirm the service container was recreated.
4. Confirm the configured serial path matches the host path exactly.

## Future USB Detection

Stable USB paths identify boards, not the physical sensor role. The long-term
plan is to add Arduino identity messages and a detection helper.

See [FUTURE_HARDWARE_USB_SETUP.md](FUTURE_HARDWARE_USB_SETUP.md).
