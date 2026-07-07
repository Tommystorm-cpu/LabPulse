# Arduino C++ Review Notes

These notes summarize issues found while comparing the Arduino sketches with the current Python serial parsers.

No production code has been changed as part of these notes.

The developed python in this folder will be resisiliant to some of the c++ weirdness, so I shouldn't have to change it yet.

## Summary

The deployed LabPulse system appears to use three Arduino serial paths:

```text
pressure Arduino
  -> pressurepub.py
  -> Air Pressure

pump room Arduino
  -> pumproompub.py
  -> Pump Room

water temperature/flow Arduino
  -> turbo_pump_monitor.py
  -> Cryogenics Room / Turbo Pump Hub
```

There does not appear to be a dedicated turbo pump Arduino sketch. The turbo pump monitor seems to reuse the water temperature/flow Arduino format and distinguishes the station in Python with the `turbo_` prefix.

## Main Issue: Combined Flow And Temperature Line

File:

```text
Arduino/full_water_sensor_code.cpp
```

The sketch prints `Flow1` and `Flow2`, then immediately prints `Temp0` without a newline between them.

Current output shape:

```text
Flow1: 2.45 L/min | Flow2: 3.10 L/minTemp0: 20.11C  Temp1: 20.22C  Temp2: 20.33C  Temp3: 20.44C
```

This is awkward for:

```text
pi_scripts/turbo_pump_monitor.py
```

because that Python parser expects either a clean `Flow1:` line or a clean `Temp0:` line.

Recommended future fix:

```cpp
Serial.println(" L/min");
```

instead of:

```cpp
Serial.print(" L/min");
```

after printing `Flow2`.

Desired output:

```text
Flow1: 2.45 L/min | Flow2: 3.10 L/min
Temp0: 20.11C  Temp1: 20.22C  Temp2: 20.33C  Temp3: 20.44C
```

## Temperature Edge Cases

Files:

```text
Arduino/Pump_Room_Arduino.cpp
Arduino/full_water_sensor_code.cpp
```

Both sketches calculate thermistor temperature from analog voltage using a Steinhart-Hart equation.

If a sensor is disconnected or the analog voltage is near `0V` or `5V`, the calculation can produce invalid or physically impossible values.

This likely explains dashboard readings such as:

```text
-273.15 C
```

Recommended future fix:

```cpp
if (voltage <= 0.01 || voltage >= 4.99) {
  return NAN;
}
```

Then the Python parser should ignore `nan` or invalid temperature values.

## DHT Read Failures

File:

```text
Arduino/Pump_Room_Arduino.cpp
```

The DHT11 room temperature and humidity reads are not checked for `NaN`.

DHT sensors can occasionally fail a read, so this may produce invalid serial output:

```text
RoomTemp: nanC | RoomHum: nan%
```

Recommended future fix:

```cpp
if (isnan(roomTemp) || isnan(roomHum)) {
  // skip or print a clear invalid marker
}
```

## Pressure Arduino

File:

```text
Arduino/Pressure_Arduino.cpp
```

This sketch currently matches the Python pressure parser well.

It prints one MPa value per line:

```text
0.1034
```

The Python service converts this to bar by multiplying by `10.0`.

## Refactor Implication

The Python refactor should probably treat pump room and turbo/cryogenics as two configured instances of the same water temperature/flow monitor pattern.

Example future shape:

```yaml
water_monitors:
  pump_room:
    serial_port: ...
    sensor_prefix: "pump_"
    device_name: "Pump Room Sensor Hub"

  turbo_pump:
    serial_port: ...
    sensor_prefix: "turbo_"
    device_name: "Turbo Pump Hub"
```

That matches the hardware better than treating turbo pump as a unique Arduino type.
