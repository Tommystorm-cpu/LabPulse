# Sensor implementation reference

This directory contains the reusable sensor code used by the LabPulse Arduino
examples. Device-specific pins, measurement names, calibration values, and
sample intervals are defined in the `.h` files under `examples/`.

The repository does not currently identify the manufacturer and model of the
flow meters, thermistors, or pressure transducers. The values below document
the retained LabPulse calibration, not universal specifications for every
sensor with similar wiring. Record the exact part number and datasheet before
replacing a sensor or reusing these values in another lab.

## Readings, zero, and `null`

Every sensor returns a `Reading` containing:

```cpp
struct Reading {
  float value;
  bool valid;
};
```

`PipeSampleWriter` emits the numeric value only when `valid` is true and the
value is finite. Otherwise it emits `null`:

```text
flow1: 0.00 | temp0: null | press1: 0.00
```

Zero and `null` are not interchangeable:

| Sensor | What numeric zero means | When it becomes `null` |
| --- | --- | --- |
| Flow | No pulses were detected during a valid sample interval | The interval or calibration is invalid, or the result is not finite |
| Thermistor | A calculated temperature of 0 degrees Celsius | The ADC, resistance, equation, or calculated temperature fails validation |
| DHT11 temperature | The library returned a valid 0 degrees Celsius | The library read fails or the value is outside the configured range |
| DHT11 humidity | The library returned a valid 0 percent relative humidity | The library read fails or the value is outside the configured range |
| Pressure | The calculated pressure is zero, or a permitted negative value is clamped to zero | The ADC, calibration, or calculated pressure fails validation |

An in-range number is not proof that the sensor is healthy. For example, a
disconnected flow sensor produces no pulses and is therefore indistinguishable
from genuinely stopped flow. Similarly, some wiring faults can leave an analog
input at a plausible in-range voltage. LabPulse uses range checks to reject
obvious faults, but cannot diagnose every electrical failure from one reading.

## Pin and measurement names

`PinMeasurement.h` defines the mapping used by both sensor construction and
serial output:

```cpp
struct PinMeasurement {
  uint8_t pin;
  const char *name;
};
```

A device header declares records in `{pin, name}` order:

```cpp
constexpr LabPulse::PinMeasurement FLOW1 = {3, "flow1"};
```

The sensor config uses `FLOW1.pin`, while `PipeSampleWriter` uses `FLOW1.name`.
Changing this record therefore changes the physical input and emitted name in
one place. A DHT11 mapping stores one pin with two names because one transaction
returns both temperature and humidity.

## Pulse flow sensor

Files: `PulseFlowSensor.h` and `PulseFlowSensor.cpp`.

The flow sensor generates pulses on an interrupt-capable digital input. The
interrupt handler increments a volatile counter. At each sample, the firmware
atomically copies and resets the counter, then calculates:

```text
litres per minute = pulses x 60000 / (pulses per litre x elapsed milliseconds)
```

`samplePairAndReset()` samples two counters while interrupts are disabled so
both flow rates use exactly the same time window.

### `PulseFlowConfig`

| Field | Meaning |
| --- | --- |
| `pin` | Interrupt-capable digital input |
| `pulsesPerLitre` | Sensor calibration in pulses per litre |
| `pinMode` | Arduino input mode, currently `INPUT_PULLUP` |
| `interruptMode` | Edge that records a pulse, currently `FALLING` |

All current flow channels use `450.0` pulses per litre. The pump room maps
`flow1` to D3 and `flow2` to D2; the turbo pump maps `flow1` to D2 and `flow2`
to D3. Both devices sample every 5000 ms.

A positive elapsed interval with zero pulses returns valid `0 L/min`. This can
mean no flow, a stopped pulse output, disconnected wiring, or a failed sensor.
The reading is `null` only when:

- `elapsedMilliseconds` is zero;
- `pulsesPerLitre` is zero or negative; or
- the calculated result is not finite.

## Thermistor sensor

Files: `ThermistorSensor.h` and `ThermistorSensor.cpp`.

The current circuit is calculated as a voltage divider. For ADC reading `N`:

```text
voltage = N x ADC reference / ADC divisor
fixed-resistor voltage = ADC reference - voltage
sensor resistance = voltage / fixed-resistor voltage x fixed resistance
```

The four-coefficient Steinhart-Hart equation then converts resistance to
temperature:

```text
lnR = natural logarithm of sensor resistance in ohms
1 / T = A + B(lnR) + C(lnR)^2 + D(lnR)^3
temperature in degrees Celsius = T - 273.15
```

### `ThermistorConfig`

| Field | Meaning |
| --- | --- |
| `pin` | Analog input pin |
| `adcReferenceVolts` | Voltage represented by the top of the ADC scale |
| `adcDivisor` | ADC count divisor used in the voltage calculation |
| `minimumValidAdc` / `maximumValidAdc` | Inclusive accepted raw ADC range |
| `fixedResistanceOhms` | Known voltage-divider resistor |
| `steinhartA` to `steinhartD` | Four fitted Steinhart-Hart coefficients |
| `minimumValidCelsius` / `maximumValidCelsius` | Inclusive accepted output range |

All current thermistor channels use:

| Parameter | Current value |
| --- | ---: |
| ADC reference | 5.0 V |
| ADC divisor | 1023 |
| Valid ADC range | 2 to 1021 inclusive |
| Fixed resistor | 4700 ohms |
| A | 0.0014948 |
| B | 0.00021902 |
| C | 0.0000016239 |
| D | 0.000000034445 |
| Valid temperature range | -100 to 200 degrees Celsius inclusive |

The pump-room and turbo-pump examples map four thermistors to A0 through A3.
The coefficients are specific calibration data retained from the current
LabPulse firmware; another thermistor model or divider resistor requires new
values derived from its datasheet or calibration.

The reading is `null` when:

- the raw ADC is outside 2 to 1021;
- the voltage across the fixed resistor is zero or negative;
- the calculated sensor resistance is non-finite or not positive;
- the Steinhart-Hart denominator is non-finite or not positive; or
- the calculated temperature is non-finite or outside -100 to 200 degrees
  Celsius.

A numeric zero is a valid calculated temperature of `0 degrees Celsius`. ADC
rail values are rejected as likely open- or short-circuit conditions, but an
electrical fault that produces an in-range ADC value can still look plausible.

## DHT11 temperature and humidity sensor

Files: `Dht11Sensor.h` and `Dht11Sensor.cpp`.

This wrapper uses **DHT sensor library by Adafruit**. The dependency is declared
without a fixed version, so Arduino uses the version installed through Library
Manager. `begin()` initializes the library. A single `read()` obtains
temperature and humidity, then validates the two results independently. One
can therefore be numeric while the other is `null`.

### `Dht11Config`

| Field | Meaning |
| --- | --- |
| `pin` | Digital data pin |
| `dhtType` | Adafruit library sensor type, currently `DHT11` |
| `minimumValidTemperature` / `maximumValidTemperature` | Inclusive software temperature limits |
| `minimumValidHumidity` / `maximumValidHumidity` | Inclusive software humidity limits |

The current pump-room configuration uses D4 and accepts -40 to 80 degrees
Celsius and 0 to 100 percent relative humidity. These are LabPulse software
validation limits, not the physical DHT11 limits. Adafruit documents the
DHT11 for 0 to 50 degrees Celsius at +/-2 degrees accuracy, 20 to 80 percent
relative humidity at 5 percent accuracy, and at most one sample per second.
The current 5000 ms LabPulse interval respects that sample rate, but its
software acceptance ranges are deliberately wider than the documented DHT11
ranges. See the
[Adafruit DHT11 guide](https://learn.adafruit.com/dht?view=all#dht11-vs-dht22-1707995).

Adafruit's library returns a non-finite value when communication fails. A DHT
channel is `null` when its value is non-finite or outside its configured range.
Numeric `0` remains valid under the current limits: it means 0 degrees Celsius
for temperature or 0 percent relative humidity for humidity. Zero humidity is
outside Adafruit's documented DHT11 range but is not currently rejected by the
LabPulse configuration.

## Linear pressure sensor

Files: `LinearPressureSensor.h` and `LinearPressureSensor.cpp`.

The pressure wrapper reads an analog voltage and applies a linear two-point
calibration:

```text
voltage = ADC x ADC reference / ADC divisor
base pressure =
    (voltage - minimum calibration voltage)
    / (maximum calibration voltage - minimum calibration voltage)
    x full-scale pressure
output = base pressure x output multiplier
```

Optional quantisation rounds the base pressure before applying the output
multiplier:

```text
rounded base = round(base x quantisation scale) / quantisation scale
```

A quantisation scale of zero disables this step.

### `LinearPressureConfig`

| Field | Meaning |
| --- | --- |
| `pin` | Analog input pin |
| `adcReferenceVolts` | Voltage represented by the ADC scale |
| `adcDivisor` | ADC divisor used in the voltage calculation |
| `minimumValidAdc` / `maximumValidAdc` | Inclusive accepted raw ADC range |
| `minimumCalibrationVolts` | Sensor voltage representing zero base pressure |
| `maximumCalibrationVolts` | Sensor voltage representing full-scale pressure |
| `fullScalePressure` | Base pressure at the maximum calibration voltage |
| `outputMultiplier` | Conversion applied to the base pressure |
| `preConversionQuantizationScale` | Optional rounding scale; zero disables it |
| `minimumValidOutput` / `maximumValidOutput` | Inclusive accepted final range |
| `clampNegativeToZero` | Whether a valid negative result is reported as zero |

### Current pressure configurations

| Parameter | Pressure monitor | Pump room `press1` and `press2` |
| --- | ---: | ---: |
| Pins | A0 | A5 and A4 |
| ADC reference | 5.0 V | 5.0 V |
| ADC divisor | 1023 | 1024 |
| Valid ADC range | 2 to 1021 | 2 to 1021 |
| Calibration voltage range | 0.48 to 4.5 V | 0.5 to 4.5 V |
| Full-scale base pressure | 1.6 MPa | 1.6 MPa |
| Output multiplier | 10.0 | 10.0 |
| Output unit | bar | bar |
| Quantisation scale | 10000 | disabled |
| Valid output range | -0.25 to 16.5 bar | -0.25 to 16.5 bar |
| Clamp valid negative values to zero | no | yes |

The reading is `null` when:

- the raw ADC is outside 2 to 1021;
- the calibration voltage span is zero or negative;
- the ADC divisor is zero or negative; or
- the final output is non-finite or outside -0.25 to 16.5 bar.

For the pressure monitor, `0 bar` corresponds to 0.48 V. Small valid negative
readings are preserved down to -0.25 bar. For the pump room, `0 bar`
corresponds to 0.5 V, and any otherwise-valid negative result is clamped to
zero. Pump-room zero can therefore mean exactly zero pressure or a voltage
slightly below the calibrated zero point. A severely out-of-range value is
`null`, not zero.

## Pipe sample writer

Files: `PipeSampleWriter.h` and `PipeSampleWriter.cpp`.

The writer produces one unit-free, pipe-delimited record per line:

```text
name1: 1.23 | name2: null | name3: 0.00
```

`value()` writes the configured number of decimal places. It writes `null` if
the `Reading` is invalid or its value is non-finite. `end()` adds the newline
that marks the sample as complete. Units and measurement metadata belong in
the Raspberry Pi LabPulse configuration, not in the Arduino output.
