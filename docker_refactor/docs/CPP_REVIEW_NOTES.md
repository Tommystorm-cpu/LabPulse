# Arduino Compatibility Notes

These notes record sketch/parser compatibility issues to keep in mind when
changing Arduino code or Python parsing.

The main hardware guide is [HARDWARE_AND_SERIAL.md](HARDWARE_AND_SERIAL.md).

## Combined Flow And Temperature Output

`Arduino/full_water_sensor_code.cpp` can print `Flow2` and `Temp0` without a
newline between them:

```text
Flow1: 2.45 L/min | Flow2: 3.10 L/minTemp0: 20.11C
```

The Docker refactor parser is designed to tolerate this shape. A cleaner future
sketch change would print a newline after the flow section.

## Invalid Temperature Values

Thermistor calculations can produce invalid values when a sensor is disconnected
or the voltage is near the edge of the expected range.

Sketch-side hardening should reject invalid voltage before calculating or
printing temperature. Parser-side hardening should ignore non-finite numbers.

## DHT Read Failures

DHT sensors can return invalid readings. If the sketch prints `nan`, the parser
should avoid publishing that value.

## Pressure Arduino

`Arduino/Pressure_Arduino.cpp` matches the Docker refactor pressure parser: one
MPa value per line, converted to bar in Python.

## Refactor Implication

Pump room and turbo pump are best treated as configured instances of serial
water/flow style monitors rather than hard-coded one-off Python programs. The
current `services:` model supports that by using service-specific config with a
shared driver/parser pattern.
