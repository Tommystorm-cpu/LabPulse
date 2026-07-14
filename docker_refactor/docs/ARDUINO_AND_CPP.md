# Arduino and C++ Notes

This document is the single reference for Arduino output consumed by the
Docker refactor. It separates three things that were previously mixed together:

1. what each current sketch actually prints;
2. how the Python compatibility parser handles it now;
3. firmware improvements that are recommendations, not implemented behavior.

For host-side parsing details, see the Legacy serial parser section of
[CODE_INTERNALS.md](CODE_INTERNALS.md).

## Current contract

All active serial sketches use 9600 baud. Python reads one newline-terminated
line at a time and returns a `dict[str, float]`. Parsed keys are lowercased
Arduino labels and must appear as `readings[].name` in the live config.

```text
Arduino text
  -> SerialParser
  -> {reading_name: numeric_value}
  -> config allow-list
  -> MQTT
```

Units written in the serial text are ignored by the labelled parser. Units and
Home Assistant device classes come from config.

## Sketch and service map

| Sketch | Intended service/parser | Current role |
| --- | --- | --- |
| `Arduino/Pressure_Arduino.cpp` | `pressure_monitor`, `parser: pressure` | Main compressed-air input |
| `Arduino/Pump_Room_Arduino.cpp` | `pump_room`, `parser: pump_room` | Flow, water temperatures, room DHT, and two pressures |
| `Arduino/full_water_sensor_code.cpp` | `turbo_pump`, `parser: water` | Two flow and four water-temperature readings |
| `Arduino/Water flow meter code/Temporary flow reader.cpp` | labelled parser such as `water` if adopted | Development sketch, not a main configured link |

Files named as Arduino instructions, calibration programs, older Python
publishers, and standalone sensor examples are supporting/historical material;
they are not the Docker runtime contract.

## Pressure Arduino

Source:

```text
Arduino/Pressure_Arduino.cpp
```

It reads analog pin 0, maps calibrated voltage to a 0–1.6 MPa range, and prints
one bare number per second:

```text
0.1034
```

The Python `pressure` parser interprets that value as MPa and publishes bar:

```text
0.1034 MPa * 10 = 1.034 bar
```

The configured key is therefore always:

```python
{"pressure": 1.034}
```

### Known limitations

- The sketch assumes a 5 V ADC reference and fixed calibration values
  `Start_V = 0.48`, `End_V = 4.5`.
- Values below the start voltage can produce a negative pressure.
- There is no explicit check for disconnected, saturated, or impossible ADC
  input.
- The device does not identify itself on startup, so the operator must map its
  `/dev/serial/by-id/...` path manually.

## Pump-room Arduino

Source:

```text
Arduino/Pump_Room_Arduino.cpp
```

Every five seconds it prints three lines.

Flow:

```text
Flow1: 2.45 L/min | Flow2: 3.10 L/min
```

Four thermistors:

```text
Temp0: 20.11C  Temp1: 20.22C  Temp2: 20.33C  Temp3: 20.44C
```

DHT11 and two analog pressure sensors:

```text
RoomTemp: 21.2C | RoomHum: 45.0% | Press1: 1.23 bar | Press2: 1.45 bar
```

The current starter config publishes all ten pump-room readings:

```text
flow1, flow2, temp0, temp1, temp2, temp3,
roomtemp, roomhum, press1, press2
```

The parser returns the lower-case keys above, and the matching live-config
entries allow the MQTT publisher to expose every channel.

### Calculation details

- Hall sensors increment floating `flowCount_1` and `flowCount_2` from
  interrupt handlers.
- `printResults()` detaches both interrupts, divides accumulated litres by the
  elapsed interval in minutes, resets counters, and reattaches interrupts.
- Four thermistors use one set of Steinhart–Hart coefficients and a 4.7 kΩ
  divider resistor.
- DHT11 temperature and humidity are printed directly.
- Analog pressure voltage is converted from a nominal 0.5–4.5 V sensor output
  to MPa and then bar; negative noise is clamped to zero.

### Known limitations

- DHT library calls may return `NaN`; the sketch prints it without an explicit
  validity check. Python ignores it because it cannot extract a finite number.
- Thermistor voltage at or close to the supply rail makes
  `5.0 - voltage` zero or tiny, producing invalid resistance/temperature.
- A disconnected thermistor can result in implausible values, including values
  near absolute zero.
- Variables modified by interrupt handlers are not declared `volatile`.
  Interrupts are detached while results are calculated, which reduces races,
  but ISR-shared state should still be reviewed for compiler and atomicity
  correctness on the target Arduino.
- ADC scaling is not fully consistent: thermistors use `5.0/1023.0`, while
  pressure inputs use `5.0/1024.0`.
- The output is human-readable but does not carry a device ID, firmware
  version, schema version, or per-message validity indicator.

## Full water/turbo-pump Arduino

Source:

```text
Arduino/full_water_sensor_code.cpp
```

It measures two flow channels and four thermistors every five seconds. The
current output joins the flow and temperature sections without a newline after
Flow2:

```text
Flow1: 2.45 L/min | Flow2: 3.10 L/minTemp0: 20.11C  Temp1: 20.22C  Temp2: 20.33C  Temp3: 20.44C
```

That `L/minTemp0` boundary is real. The Python labelled parser intentionally
finds recognized labels rather than relying on pipes/newlines, so it still
returns:

```python
{
    "flow1": 2.45,
    "flow2": 3.10,
    "temp0": 20.11,
    "temp1": 20.22,
    "temp2": 20.33,
    "temp3": 20.44,
}
```

The flow/thermistor calculations and ISR concerns are similar to the pump-room
sketch. There is no DHT or pressure section.

The smallest safe firmware cleanup would be a newline after Flow2. Python can
continue accepting both forms during the transition.

## Temporary flow reader

Source:

```text
Arduino/Water flow meter code/Temporary flow reader.cpp
```

Every five seconds it prints:

```text
FlowRate:1.234,TotalLitres:0.567
```

`pulseCount` is correctly declared `volatile`, and interrupts are detached
while the interval is calculated. The sketch is not represented by a default
service or simulator device. If adopted with the current parser, use a labelled
parser type such as `water` and config reading names `flowrate` and
`totallitres`.

The comment says 7.5 pulses/second/L/min is usual while the code uses
`calibrationFactor = 4.5`; the physical sensor’s datasheet/calibration must
decide which is correct before deployment.

## Python compatibility behavior

The parser recognizes these labelled families:

```text
FlowRate
TotalLitres
RoomTemp
RoomHum
Flow<number>
Temp<number>
Press<number>
```

For labelled formats, it takes the first finite signed number between one
recognized label and the next. This means:

- spaces, `|`, unit text, and the missing `L/minTemp0` separator are tolerated;
- `nan` and labels without a numeric value are skipped;
- one bad value does not discard other valid labels on the line;
- unexpected labels are not parsed into surprise keys.

The final MQTT filter is stricter still: a parsed key must exactly match a
configured `readings[].name`.

## Simulator equivalence

`simulate_serial.py` creates four pseudo-serial devices:

```text
pressure
pump_room
turbo_pump
room_environment
```

It emits text shaped like the corresponding real formats so tests exercise the
same serial driver and parser. Room environment uses the generic pipe format:

```text
temperature:21.2|humidity:45.0
```

The simulator is a host-side test device, not firmware, and does not change the
real Arduino contracts.

## Recommended firmware contract

The following is a recommendation, not something the current Python runtime
expects yet.

New firmware should emit one machine-readable record with an explicit device
and schema identity, for example:

```json
{"device":"pump_room","schema":1,"flow1":2.45,"flow2":3.10,"temp0":20.11}
```

Benefits:

- automatic mapping from an Arduino to its service role;
- no unit text or label-boundary parsing;
- schema/version checks during upgrades;
- explicit omission or error reporting for invalid channels;
- one parser shared by new firmware;
- easier fixture generation and serial tests.

Before changing the wire format, update together:

1. the Arduino sketch;
2. `labpulse_hardware/legacy_parsing/serial_parser.py` or its replacement;
3. parser tests;
4. simulator payloads and tests;
5. this document;
6. any configured reading names affected by the schema.

## Recommended sketch hardening

These are review actions, not claims about current behavior:

- reject ADC endpoints before divider/`log()` calculations;
- validate all calculated values with `isfinite()` and physical bounds;
- print explicit channel error state rather than a plausible sentinel value;
- validate DHT values before printing;
- declare ISR-shared state correctly and make main-loop access atomic;
- use consistent ADC divisor/reference assumptions;
- document and verify flow calibration factors against the actual sensor;
- add `DEVICE:<role>` and firmware/schema version output at minimum;
- keep one complete record per line;
- include a startup self-test or channel-presence report where practical.

Until a standardized firmware contract is deployed, the isolated legacy parser
is the deliberate compatibility boundary. Do not spread Arduino-format quirks
into drivers, MQTT publishing, or Home Assistant templates.
