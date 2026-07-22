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

Example of one complete sample line:

```text
flow1: 2.45 | flow2: 3.10 | temp0: 20.11 | temp1: 20.22
```

Keys are lower-case config measurement names. Values are finite numbers in the
final configured unit, without unit text. A channel that fails firmware safety
validation is `null`; the serial parser omits it. All serial Arduino services
therefore use:

```yaml
driver: serial
baud_rate: 9600
```

There is no JSON envelope. The `LabPulseFirmware` Arduino library provides the
standard pipe writer plus reusable pulse-flow,
thermistor, linear-pressure, and DHT11 components. Lab-specific device headers
retain pins and calibration values, and device composition sources choose
which sensors to publish. The combined library declares the external Arduino
DHT dependency; unused DHT code is removed from firmware that does not create
that sensor.

Each target contains:

```text
device.h      pins, calibration, intervals, precision
device.cpp    sensor construction, sampling, output order
device.ino    minimal Arduino setup()/loop() wrapper
```

Arduino IDE compiles those files and the imported sensor modules into one
flashable image. See [the firmware README](../firmware/README.md) for the
installation and flashing workflow.

## Standard sketches

| Sketch | Measurements |
| --- | --- |
| `firmware/examples/pressure_monitor/pressure_monitor.ino` | `pressure` in bar |
| `firmware/examples/pump_room/pump_room.ino` | `flow1`, `flow2`, `temp0`-`temp3`, `roomtemp`, `roomhum`, `press1`, `press2` |
| `firmware/examples/turbo_pump/turbo_pump.ino` | `flow1`, `flow2`, `temp0`-`temp3` |

Pins, calibration constants, equations, intervals, and output precision remain
copied from the corresponding old sketches. The only unit conversion moved
from Python is standalone pressure: the Arduino now emits bar. It preserves the
old four-decimal MPa serial quantisation before converting, so the downstream
two-decimal reading remains compatible.

Flow pulse counters are integer, `volatile`, and atomically snapshotted. Sensor
range checks and `null` output are retained safety improvements. Note that zero
pulses are a valid zero-flow sample and cannot prove electrical continuity.

See [the firmware README](../firmware/README.md) for exact pin/calibration
details and flashing precautions.

## Writing a new device firmware

A device firmware is a small composition of reusable sensor classes. Keep
device-specific settings in its `.h`, runtime sampling and output in its
`.cpp`, and the Arduino entry points in its `.ino`.

### 1. Copy and rename an example

Copy the closest directory under `firmware/examples/`. The directory and three
main files must share the same base name:

```text
examples/cold_room/
  cold_room.ino
  cold_room.h
  cold_room.cpp
```

Arduino IDE automatically compiles the `.ino` and every `.cpp` beside it. A
custom sensor implementation used only by this device can therefore be added
as another `.h/.cpp` pair in the same directory.

### 2. Write the `.ino` entry point

Keep the `.ino` minimal. It delegates Arduino's required global functions to a
named namespace implemented in the device `.cpp`:

```cpp
#include "cold_room.h"

void setup() {
  ColdRoomFirmware::setup();
}

void loop() {
  ColdRoomFirmware::loop();
}
```

### 3. Put configuration in the `.h`

Include only the sensor types the device uses. Define the sample interval,
serial baud rate, output precision, pins, calibration, and valid ranges in the
device namespace:

```cpp
#ifndef LABPULSE_COLD_ROOM_FIRMWARE_H
#define LABPULSE_COLD_ROOM_FIRMWARE_H

#include <Arduino.h>
#include <Dht11Sensor.h>
#include <LinearPressureSensor.h>
#include <PinMeasurement.h>

namespace ColdRoomFirmware {

constexpr unsigned long SAMPLE_INTERVAL_MS = 5000UL;
constexpr uint16_t SERIAL_BAUD_RATE = 9600;
constexpr uint8_t ENVIRONMENT_DECIMAL_PLACES = 1;
constexpr uint8_t PRESSURE_DECIMAL_PLACES = 2;

// Authoritative pin-to-name records. Their field order is {pin, name}.
constexpr LabPulse::PinMeasurement PRESSURE = {A0, "pressure"};

// A DHT11 has one pin and two outputs, so keep all three values together.
struct Dht11Measurements {
  uint8_t pin;
  const char *temperatureName;
  const char *humidityName;
};
constexpr Dht11Measurements ROOM_DHT11 = {4, "roomtemp", "roomhum"};

constexpr LabPulse::Dht11Config ENVIRONMENT_CONFIG = {
    ROOM_DHT11.pin, DHT11, -40.0F, 80.0F, 0.0F, 100.0F};

constexpr LabPulse::LinearPressureConfig PRESSURE_CONFIG = {
    PRESSURE.pin,
    5.0F,     // ADC reference volts
    1023,     // ADC divisor
    2,        // minimum valid ADC
    1021,     // maximum valid ADC
    0.48F,    // voltage at zero pressure
    4.5F,     // voltage at full scale
    1.6F,     // full-scale pressure before conversion
    10.0F,    // output multiplier: MPa to bar
    10000.0F, // optional pre-conversion quantisation; 0 disables it
    -0.25F,   // minimum valid output
    16.5F,    // maximum valid output
    false};   // clamp a valid negative output to zero

void setup();
void loop();

}  // namespace ColdRoomFirmware

#endif
```

Give every physical input a mapping record and put the pin first, followed by
the serial measurement name. Both the sensor configuration and the `.cpp`
output must read from that record. This makes the header the single place to
change either value. If one input produces multiple measurements, as a DHT11
does, keep its pin and all of its names together.

The supplied configuration structures use positional fields. Their order is:

| Structure | Fields in order |
| --- | --- |
| `Dht11Config` | pin, DHT type, minimum/maximum temperature, minimum/maximum humidity |
| `PulseFlowConfig` | interrupt-capable pin, pulses per litre, pin mode, interrupt mode |
| `ThermistorConfig` | pin, ADC reference, ADC divisor, valid ADC minimum/maximum, fixed resistance, Steinhart-Hart A/B/C/D, valid temperature minimum/maximum |
| `LinearPressureConfig` | pin, ADC reference, ADC divisor, valid ADC minimum/maximum, calibration minimum/maximum voltage, full-scale pressure, output multiplier, quantisation scale, valid output minimum/maximum, negative clamp |

Use the sensor datasheet and a verified calibration. Do not copy a calibration
from another transducer merely because its voltage range appears similar.

### 4. Compose the sensors in the `.cpp`

Construct sensors once, initialize sensors that require setup, read them at the
configured interval, and pass their `Reading` values to `PipeSampleWriter`:

```cpp
#include "cold_room.h"

#include <PipeSampleWriter.h>

namespace ColdRoomFirmware {
namespace {

LabPulse::Dht11Sensor environment(ENVIRONMENT_CONFIG);
LabPulse::LinearPressureSensor pressure(PRESSURE_CONFIG);
unsigned long lastSampleMilliseconds = 0;

void emitSample() {
  const LabPulse::Dht11Reading environmentReading = environment.read();

  LabPulse::PipeSampleWriter sample(Serial);
  sample.value(
      ROOM_DHT11.temperatureName,
      environmentReading.temperature,
      ENVIRONMENT_DECIMAL_PLACES);
  sample.value(
      ROOM_DHT11.humidityName,
      environmentReading.humidity,
      ENVIRONMENT_DECIMAL_PLACES);
  sample.value(
      PRESSURE.name,
      pressure.read(),
      PRESSURE_DECIMAL_PLACES);
  sample.end();
}

}  // namespace

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  environment.begin();
}

void loop() {
  const unsigned long now = millis();
  const unsigned long elapsedMilliseconds = now - lastSampleMilliseconds;
  if (elapsedMilliseconds < SAMPLE_INTERVAL_MS) {
    return;
  }
  lastSampleMilliseconds = now;
  emitSample();
}

}  // namespace ColdRoomFirmware
```

Unsigned subtraction keeps the interval check safe when `millis()` wraps. Do
not use a long blocking delay in a mixed sensor device because it can interfere
with other timing-sensitive work.

### 5. Add pulse-flow sensors correctly

Pulse counting requires an interrupt callback with no arguments. The callback
must only record the pulse:

```cpp
LabPulse::PulseFlowSensor flow(FLOW_CONFIG);

void countFlowPulse() {
  flow.recordPulse();
}

void setup() {
  Serial.begin(SERIAL_BAUD_RATE);
  flow.begin(countFlowPulse);
}
```

For one flow channel, read and reset it using the same elapsed interval used by
the main loop:

```cpp
const LabPulse::Reading flowReading =
    flow.sampleAndReset(elapsedMilliseconds);
```

For two channels, snapshot both counters together:

```cpp
LabPulse::Reading flow1Reading;
LabPulse::Reading flow2Reading;
LabPulse::PulseFlowSensor::samplePairAndReset(
    flow1,
    flow2,
    elapsedMilliseconds,
    flow1Reading,
    flow2Reading);
```

Do not perform floating-point calculations, serial output, delays, or sensor
reads inside an interrupt callback.

### 6. Follow the output contract

`PipeSampleWriter` adds separators, prints finite valid values, converts an
invalid reading to `null`, and finishes the sample with a newline.

For every output value:

- use a lower-case stable name such as `temperature` or `flow1`;
- pass names through `F("name")` to conserve Arduino RAM;
- emit the final configured unit rather than raw ADC counts;
- choose an appropriate decimal precision;
- call `sample.end()` exactly once after the final value;
- define the same name under `measurements` in the Pi's live config.

Do not print headings, debug messages, units, or extra lines on the production
serial connection. A complete sample must look like:

```text
temperature: 21.4 | humidity: 45.0 | pressure: 1.03
```

The corresponding Pi service continues to use the generic configuration:

```yaml
driver: serial
baud_rate: 9600
```

### 7. Add a genuinely new sensor type

If none of the supplied sensor classes fits the hardware, create a focused
`.h/.cpp` pair. Give it a configuration structure, keep hardware-specific
calculation inside the class, and return `LabPulse::Reading` in the final unit:

```cpp
LabPulse::Reading NewSensor::read() const {
  const float value = readAndConvertHardware();
  const bool valid = isfinite(value) && value >= minimum_ && value <= maximum_;
  return {value, valid};
}
```

The device `.cpp` should not need to know the sensor's ADC equation or error
sentinel. Do not add a device-specific Python parser; keep the standard pipe
contract and normal `dict[str, float]` hardware path.

### 8. Verify before installation

Before uploading to a live board:

1. use Arduino IDE's **Verify** command;
2. confirm the selected board, port, pins, and calibration;
3. upload to one identified Arduino;
4. inspect several complete samples at 9600 baud;
5. exercise invalid/disconnected sensors and confirm they produce `null`;
6. confirm every emitted key exists in `~/labpulse-ha/config.yaml`;
7. verify the readings in Home Assistant before leaving the service running.

## Unsupported old formats

Legacy bare values, multi-line output, embedded units, malformed separators,
and JSON records are not supported. Every serial device must emit the standard
pipe format. Do not add device-specific parser branches or Python-side unit
conversions.

## Simulator equivalence

`simulate_serial.py` emits the same pipe contract for every pseudo-serial
device, including pressure, pump room, turbo pump, room environment, and UPS.

The simulator's control socket still uses JSON internally. That is a host-side
command transport and is not part of the Arduino-to-Python serial interface.
