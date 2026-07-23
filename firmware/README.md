# LabPulse Arduino firmware

This directory is an Arduino library containing reusable sensor components and
three example device firmwares. The examples publish LabPulse's standard
unit-free pipe-delimited serial protocol.

## Contents

```text
firmware/
  library.properties
  src/
    Reading.h
    PinMeasurement.h
    PipeSampleWriter.*
    PulseFlowSensor.*
    ThermistorSensor.*
    Dht11Sensor.*
    LinearPressureSensor.*
  examples/
    pressure_monitor/
    pump_room/
    turbo_pump/
```

The complete `firmware` folder is the `LabPulseFirmware` Arduino library. Do not
copy or open only an example `.ino`; the example depends on headers under
`src/`.

## Install the library

Use an Arduino IDE or Arduino CLI installation that supports the target board.
For Arduino IDE:

1. Find the sketchbook directory in Preferences.
2. Create its `libraries` directory if necessary.
3. Copy the complete repository `firmware` directory into it.
4. Rename the copied directory `LabPulseFirmware`.
5. Restart the IDE.

The installed structure must be:

```text
<sketchbook>/
  libraries/
    LabPulseFirmware/
      library.properties
      src/
      examples/
```

Install `DHT sensor library` by Adafruit and its prompted dependencies. The
library dependency is also declared in `library.properties`.

## Choose an example

| Example | Measurements | Interval |
|---|---|---:|
| `pressure_monitor` | `pressure` | 1 second |
| `pump_room` | `flow1`, `flow2`, `temp0`–`temp3`, `roomtemp`, `roomhum`, `press1`, `press2` | 5 seconds |
| `turbo_pump` | `flow1`, `flow2`, `temp0`–`temp3` | 5 seconds |

Open the example through the installed library's Examples menu so the toolchain
can resolve the library headers.

Before uploading, identify the physical Arduino, existing firmware, wiring,
calibration, USB port, and stable Raspberry Pi `/dev/serial/by-id/...` path.
Flash one identified board at a time.

## Device configuration

Pins, measurement names, calibration, sample intervals, and baud rate live in
the header beside each example:

```text
examples/pressure_monitor/pressure_monitor.h
examples/pump_room/pump_room.h
examples/turbo_pump/turbo_pump.h
```

A pin/name record is:

```cpp
constexpr LabPulse::PinMeasurement FLOW1 = {3, "flow1"};
```

The sensor object uses `FLOW1.pin` and serial output uses `FLOW1.name`.
Changing the record therefore changes the physical input or emitted identity in
one place.

Measurement names must exactly match the live Pi service configuration. A name
change creates a new MQTT and Home Assistant identity.

## Retained example calibration

The repository does not currently identify every sensor manufacturer and model.
These values preserve existing LabPulse behavior and are not universal
specifications. Record part numbers and datasheets before reusing or replacing
hardware.

### Pressure monitor

- analog input A0;
- 5 V ADC reference and divisor 1023;
- valid ADC range 2 to 1021;
- 0.48 to 4.5 V calibration span;
- 0 to 1.6 MPa full scale;
- output multiplied by 10 to bar;
- one-second sampling.

### Pump room

- flow inputs D3 and D2;
- 450 pulses per litre;
- thermistors on A0 through A3;
- DHT11 on D4;
- pressure inputs A5 and A4;
- pressure calibration span 0.5 to 4.5 V;
- five-second sampling.

### Turbo pump

- flow inputs D2 and D3;
- 450 pulses per litre;
- thermistors on A0 through A3;
- five-second sampling.

### Thermistors

The retained examples use:

```text
ADC reference:       5.0 V
ADC divisor:         1023
valid ADC:           2 to 1021
fixed resistor:      4700 Ω
Steinhart-Hart A:    0.0014948
Steinhart-Hart B:    0.00021902
Steinhart-Hart C:    0.0000016239
Steinhart-Hart D:    0.000000034445
accepted output:     -100 to 200 °C
```

These coefficients require verification against the actual thermistor and
divider circuit before another lab uses them.

## Reusable sensor components

### `Reading`

Every sensor returns:

```cpp
struct Reading {
  float value;
  bool valid;
};
```

Numeric zero and invalid are different. Zero can be a valid stopped-flow,
zero-pressure, zero-temperature, or zero-humidity result. Invalid becomes
`null` in the serial stream.

### `PipeSampleWriter`

```cpp
LabPulse::PipeSampleWriter sample(Serial);
sample.value(F("temperature"), reading, 2);
sample.end();
```

The writer emits finite valid values and writes `null` otherwise:

```text
temperature: 18.42 | pressure: null
```

See [Serial protocol](../docs/SERIAL_PROTOCOL.md).

### `PulseFlowSensor`

An interrupt handler calls `recordPulse()`. Sampling atomically copies and
resets the counter:

```text
litres/minute =
  pulses × 60000 / (pulses-per-litre × elapsed-milliseconds)
```

Zero pulses over a valid interval produces numeric zero. It cannot by itself
distinguish no flow from a failed/disconnected pulse source.

### `ThermistorSensor`

The component converts the ADC divider voltage to resistance and applies a
four-coefficient Steinhart-Hart equation. ADC rail values, invalid resistance,
invalid equation results, and out-of-range temperatures produce an invalid
reading.

### `Dht11Sensor`

The wrapper reads temperature and humidity together through Adafruit's DHT
library and validates the channels independently. One may be numeric while the
other is `null`.

### `LinearPressureSensor`

The component applies a two-point voltage calibration, full-scale pressure, and
output multiplier. It can optionally preserve pre-conversion quantization and
clamp negative outputs.

## Build, upload, and verify

1. Select the correct board and connected port.
2. Verify/compile the selected example.
3. Reconfirm the physical board identity.
4. Upload and wait for completion.
5. Stop the LabPulse container that normally owns the serial port.
6. Open a serial monitor at the configured baud rate, normally 9600.
7. Confirm one complete protocol sample per line.
8. Close the serial monitor before restarting LabPulse.

Example:

```text
flow1: 2.45 | flow2: 3.10 | temp0: 20.11 | temp1: 20.22
```

Then assign or confirm the stable Pi path:

```bash
cd ~/labpulse-live
./setup_usb_devices.py --config config.yaml
labpulse config
```

## Adapt firmware for another sensor

1. Copy the closest example to a new example directory.
2. Define stable pin/name mappings and calibration in its header.
3. Reuse an existing sensor class or add a focused class under `src/`.
4. Return `Reading` rather than sentinel numbers.
5. Emit one standard sample with `PipeSampleWriter`.
6. Match all names and units in live `config.yaml`.
7. Add parser/simulator or firmware-layout tests.
8. Record part number, wiring, calibration source, and real-board verification.

If a controller can emit the standard protocol, a new Python driver is normally
unnecessary.

## Limitations and safety

Software range checks catch obvious faults, not every electrical failure. A
disconnected flow sensor can look like valid zero flow, and a wiring fault can
leave an analog input at a plausible voltage. Safety-critical monitoring needs
appropriate physical fault detection and independent safeguards.
