# LabPulse Arduino firmware

This directory contains the LabPulse Arduino library. Its examples publish
LabPulse's standard unit-free pipe-delimited serial protocol. The separate
Windows [Triton publishers](../integrations/triton/README.md) live under
`integrations/triton/`.

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
    Sht40Sensor.*
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

Install `DHT sensor library` and `Adafruit SHT4x Library` through Arduino
Library Manager, including their prompted dependencies. Both library
dependencies are also declared in `library.properties`.

If LabPulseFirmware does not appear under **File → Examples**, check the
sketchbook location in Preferences and the folder structure above. The
repository folder and the Arduino sketchbook are different locations. Avoid
an extra `LabPulseFirmware/firmware/` level, keep `library.properties` beside
`src/` and `examples/`, and completely restart the IDE after installing it.
An “Invalid library” message can identify incomplete metadata; use the complete
current library rather than copying only its sketches.

## Choose an example

| Example | Measurements | Interval |
|---|---|---:|
| `pressure_monitor` | `pressure`, `temperature`, `humidity` | 1 second |
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

Emit lowercase measurement names matching the live Pi service configuration.
Renaming a configured measurement key creates a new MQTT and Home Assistant
identity. Changing only the firmware name, beyond case or surrounding
whitespace, stops updates to the old key unless the configuration is changed
to match.

## Retained example calibration

The [hardware guide](../docs/HARDWARE.md#sensor-hub-parts) lists sensor parts,
including GE-1337 thermistors, SEN0217/YF-S201 flow sensors, and the SEN0257
pressure sensor. The [conversion-source notes](../docs/HARDWARE.md#where-the-conversion-values-came-from)
link to the original sketches and thermistor fitting data.

Check the actual sensor and circuit before reusing these settings in another
build. Set pressure ranges, zero values, and divider resistance to match the
components you connect.

For both pump hubs, the retained **450 pulses per litre** agrees with the
[SEN0217 manufacturer specification](https://wiki.dfrobot.com/sen0217).
Check flow accuracy against a measured volume when commissioning a sensor.

### Pressure monitor

- analog input A0;
- 5 V ADC reference and divisor 1023;
- valid ADC range 2 to 1021;
- 0.48 to 4.5 V calibration span;
- 0 to 1.6 MPa full scale;
- output multiplied by 10 to bar;
- Adafruit SHT40 on the Arduino's I2C SDA/SCL pins at fixed address `0x44`;
- SHT40 high-precision, no-heater measurements;
- one-second sampling.

The SEN0257's nominal lower endpoint is 0.5 V. The original
[pressure sketch](../legacy/Arduino/Pressure_Arduino.cpp) identifies the retained
0.48 V as its calibrated output at atmospheric pressure. The original method
measures that voltage with the sensor at ambient pressure and uses it as the
lower endpoint. Repeat that check for a replacement sensor instead of assuming
0.48 V applies to it.
[Manufacturer specification](https://wiki.dfrobot.com/sen0257).

On an Arduino Uno, connect the Adafruit SHT40 breakout `VIN` to `5V`, `GND` to
`GND`, `SDA` to `SDA`/A4, and `SCL` to `SCL`/A5. The breakout handles 5 V logic.
The pressure transducer remains on A0. A failed SHT40 read emits `null` for
temperature and humidity without suppressing the pressure measurement.

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

The original sketch attributes these coefficients to Python curve fitting.
The [retained fitting script](../legacy/Arduino%20code%20Water%20Temperature%20Sensor%20calibration.py)
fits five resistance/temperature points labelled as datasheet data, although
it does not identify the datasheet or revision. Check the actual thermistor and
divider circuit when reusing the values. The older standalone temperature
example used 2.2 kΩ; the combined sketch and current examples use 4.7 kΩ.

## Reusable sensor components

### Follow an Arduino sample

The example `.ino` files delegate Arduino's `setup()` and `loop()` to the
implementation beside them. Start with
[`pump_room.cpp`](examples/pump_room/pump_room.cpp): `setup()` starts serial and
registers the flow interrupts; `loop()` measures elapsed time and calls
`emitSample()`. Its header holds pin/name records and conversion settings.

An **interrupt** briefly pauses normal execution when an input edge arrives.
`countFlow1Pulse()` and `countFlow2Pulse()` only increment their counters.
[`samplePairAndReset()`](src/PulseFlowSensor.cpp) briefly disables interrupts
to copy and reset both counters together, then calculates flow after enabling
them again. Call it from the ordinary loop with interrupts enabled, using the
actual elapsed milliseconds. Its two `Reading &` arguments receive the results.
`volatile` makes counter reads/writes visible to the compiler; it does not make
a multi-byte copy indivisible.

Other sensors return `Reading` objects directly. `emitSample()` passes each
reading and configured name to [`PipeSampleWriter.value()`](src/PipeSampleWriter.cpp),
then calls `end()` to finish the line. Each sample uses a new writer. Invalid
channels become `null` while valid neighbours continue; the
[serial driver](../src/labpulse/hardware/drivers/README.md#follow-registration-and-a-serial-read)
then parses the line on the Pi. Software cannot distinguish a stopped flow from
a disconnected pulse source when both produce zero pulses.

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

Each physical line is one UTF-8/ASCII sample. Fields are separated by `|` and
each field is `name: value`. Names must match configured measurement keys;
values are finite numbers or `null`. Firmware should emit unique lowercase
names. The Pi parser strips surrounding whitespace and lowercases names; if a
name occurs more than once, its last valid finite value wins. A later `null` or
malformed value does not erase an earlier valid value. Unknown names are ignored
by the publisher, and malformed or unavailable fields do not prevent other
valid fields on that line from being published. The Pi-side contract and parser
ownership are documented in the [driver package guide](../src/labpulse/hardware/drivers/README.md).

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

### `Sht40Sensor`

The wrapper initializes the fixed-address I2C sensor in high-precision,
no-heater mode and validates temperature and humidity independently. It retries
initialization after a failed transaction so a reconnected sensor can recover.

## Build, upload, and verify

1. Select the correct board and connected port.
2. Verify/compile the selected example.
3. Reconfirm the physical board identity.
4. Stop the LabPulse container that normally owns the serial port and close
   any serial monitor before uploading.
5. Upload and wait for completion.
6. Open a serial monitor at the configured baud rate, normally 9600.
7. Confirm one complete protocol sample per line.
8. Close the serial monitor before restarting LabPulse.

Example:

```text
pressure: 1.23 | temperature: 21.40 | humidity: 48.20
```

Then assign or confirm the stable Pi path:

```bash
labpulse usb
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
