# Hardware And Serial

This guide documents Arduino serial formats, parser expectations, fake USB
testing, and the stable USB path strategy for real hardware.

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

## Fake USB Serial Testing

The simulator is:

```text
docker_refactor/simulate_arduinos.sh
```

Run:

```bash
cd ~/LabPulse/docker_refactor
./setup_container_fs.sh -fake_usb
./simulate_arduinos.sh
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
```

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
