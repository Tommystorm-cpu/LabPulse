# Arduino and C++ notes

This is the serial-interface reference for Arduino devices used by the Docker
refactor. The standard sketches live under `docker_refactor/firmware/`; the
repository-root `Arduino/` directory contains the older source retained for
comparison and migration.

## Standard interface

Every new sketch uses 9600 baud and emits one complete pipe-delimited sample
per line:

```text
key: value | key: value | key: value
```

Examples:

```text
pressure: 1.03
flow1: 2.45 | flow2: 3.10 | temp0: 20.11 | temp1: 20.22
```

Keys are lower-case config measurement names. Values are finite numbers in the
final configured unit, without unit text. A channel that fails firmware safety
validation is `null`; the generic pipe parser omits it. All serial Arduino
services therefore use:

```yaml
driver: serial
parser: pipe
baud_rate: 9600
```

There is no JSON envelope or LabPulse Arduino library. This keeps lab-specific
sketches self-contained: expose another sensor by calculating its final value
and appending ` | newkey: value` to the line.

## Standard sketches

| Sketch | Measurements |
| --- | --- |
| `firmware/pressure_monitor/pressure_monitor.ino` | `pressure` in bar |
| `firmware/pump_room/pump_room.ino` | `flow1`, `flow2`, `temp0`-`temp3`, `roomtemp`, `roomhum`, `press1`, `press2` |
| `firmware/turbo_pump/turbo_pump.ino` | `flow1`, `flow2`, `temp0`-`temp3` |

Pins, calibration constants, equations, intervals, and output precision are
copied from the corresponding old sketches. The only unit conversion moved
from Python is standalone pressure: the Arduino now emits bar. It preserves the
old four-decimal MPa serial quantisation before converting, so the downstream
two-decimal reading remains compatible.

Flow pulse counters are integer, `volatile`, and atomically snapshotted. Sensor
range checks and `null` output are retained safety improvements. Note that zero
pulses are a valid zero-flow sample and cannot prove electrical continuity.

See [the firmware README](../firmware/README.md) for exact pin/calibration
details, build commands, and flashing precautions.

## Old deployed formats during migration

The compatibility parser still understands the older sketches while boards are
being upgraded:

| Old sketch | Legacy parser | Old output |
| --- | --- | --- |
| `Arduino/Pressure_Arduino.cpp` | `pressure` | bare MPa number, converted to bar in Python |
| `Arduino/Pump_Room_Arduino.cpp` | `pump_room` | labelled values split over three lines with units |
| `Arduino/full_water_sensor_code.cpp` | `water` | labelled flow and temperature values, including its missing separator |

The old named parsers are migration compatibility only. New or reflashed
boards should use the standard pipe output and `parser: pipe`; do not add new
device-specific parser branches or Python-side unit conversions.

## Simulator equivalence

`simulate_serial.py` emits the same pipe contract for the pressure, pump-room,
and turbo-pump pseudo-serial devices. Room environment also uses the generic
pipe format. UPS retains its own labelled simulator format because it models a
non-Arduino driver.

The simulator's control socket still uses JSON internally. That is a host-side
command transport and is not part of the Arduino-to-Python serial interface.
