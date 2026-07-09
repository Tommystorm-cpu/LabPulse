# Arduino Serial Formats

The canonical hardware and parser guide is now:

```text
HARDWARE_AND_SERIAL.md
```

This file is kept as a direct reference for serial line formats.

## Pressure Arduino

Source:

```text
Arduino/Pressure_Arduino.cpp
```

Output:

```text
0.1034
```

Meaning:

```text
pressure in MPa
```

Python converts MPa to bar by multiplying by `10.0`.

## Pump Room Arduino

Source:

```text
Arduino/Pump_Room_Arduino.cpp
```

Output cycle:

```text
Flow1: 2.45 L/min | Flow2: 3.10 L/min
Temp0: 20.11C  Temp1: 20.22C  Temp2: 20.33C  Temp3: 20.44C
RoomTemp: 21.2C | RoomHum: 45.0% | Press1: 1.23 bar | Press2: 1.45 bar
```

Configured Docker refactor readings currently focus on flow and water
temperature:

```text
flow1
flow2
temp0
temp1
temp2
temp3
```

Add `readings:` entries before publishing additional parsed values.

## Full Water Sensor / Turbo Pump

Source:

```text
Arduino/full_water_sensor_code.cpp
```

Current combined output shape:

```text
Flow1: 2.45 L/min | Flow2: 3.10 L/minTemp0: 20.11C  Temp1: 20.22C  Temp2: 20.33C  Temp3: 20.44C
```

A cleaner future sketch format would put flow and temperature on separate
lines.

## Temporary Flow Reader

Source:

```text
Arduino/Water flow meter code/Temporary flow reader.cpp
```

Output:

```text
FlowRate:1.234,TotalLitres:0.567
```

This is not currently one of the three main simulated LabPulse links.

## Simulator

`simulate_arduinos.sh` creates:

```text
/tmp/labpulse-fake-serial/pressure
/tmp/labpulse-fake-serial/pump_room
/tmp/labpulse-fake-serial/turbo_pump
```

The simulator should match the formats above closely enough that parser tests
and fake USB runs exercise the same assumptions as real Arduino serial output.
