# Arduino Serial Formats

This file documents the serial text formats emitted by the Arduino sketches in this repository.

The Docker refactor simulator, `simulate_arduinos.sh`, should follow these formats so Python services can be tested without physical Arduinos connected.

## Pressure Arduino

Source:

```text
Arduino/Pressure_Arduino.cpp
```

The pressure Arduino prints one numeric value per line:

```text
0.1034
```

Format:

```text
<pressure_mpa_with_4_decimal_places>
```

Example lines:

```text
0.0950
0.1034
0.1100
```

The current Python pressure service treats this as MPa and converts it to bar:

```text
bar = raw_value * 10.0
```

## Pump Room Arduino

Source:

```text
Arduino/Pump_Room_Arduino.cpp
```

The pump room Arduino emits three serial lines per reporting cycle.

Flow line:

```text
Flow1: 2.45 L/min | Flow2: 3.10 L/min
```

Water temperature line:

```text
Temp0: 20.11C  Temp1: 20.22C  Temp2: 20.33C  Temp3: 20.44C  
```

Room and pressure line:

```text
RoomTemp: 21.2C | RoomHum: 45.0% | Press1: 1.23 bar | Press2: 1.45 bar
```

Formats:

```text
Flow1: <l_min_2dp> L/min | Flow2: <l_min_2dp> L/min
Temp0: <c_2dp>C  Temp1: <c_2dp>C  Temp2: <c_2dp>C  Temp3: <c_2dp>C  
RoomTemp: <c_1dp>C | RoomHum: <percent_1dp>% | Press1: <bar_2dp> bar | Press2: <bar_2dp> bar
```

Current parser note:

```text
pi_scripts/pumproompub.py
```

currently parses only lines beginning with:

```text
Temp0:
```

It does not yet parse the pump room `Flow1:`, `RoomTemp:`, `RoomHum:`, `Press1:`, or `Press2:` lines.

## Full Water Sensor Arduino

Source:

```text
Arduino/full_water_sensor_code.cpp
```

This sketch emits flow and temperature data in a single combined serial line.

Because the sketch prints the flow section without a newline and then prints the temperature section, the output shape is:

```text
Flow1: 2.45 L/min | Flow2: 3.10 L/minTemp0: 20.11C  Temp1: 20.22C  Temp2: 20.33C  Temp3: 20.44C  
```

Notice that there is no separator between:

```text
L/min
```

and:

```text
Temp0:
```

That is the format produced by the current sketch.

Current parser note:

```text
pi_scripts/turbo_pump_monitor.py
```

currently accepts input in the same general shape as the old generic water sensor publisher. It looks for lines starting with:

```text
Temp0:
Flow1:
```

However, the current implementation chooses how to split the line by checking whether the line contains `Temp` anywhere:

```python
line.split("  ") if "Temp" in line else line.split("|")
```

That means it works best if the Arduino sends flow and temperature as separate lines:

```text
Flow1: 2.45 L/min | Flow2: 3.10 L/min
Temp0: 20.11C  Temp1: 20.22C  Temp2: 20.33C  Temp3: 20.44C  
```

The current full-water Arduino output is a combined line:

```text
Flow1: 2.45 L/min | Flow2: 3.10 L/minTemp0: 20.11C  Temp1: 20.22C  Temp2: 20.33C  Temp3: 20.44C  
```

Because that line contains both `Flow1:` and `Temp0:`, the current turbo parser is likely to fail to extract clean values from it. This is a parser/sketch mismatch that should be fixed before relying on the turbo pump service.

A robust fix would be either:

```text
change the Arduino sketch to print flow and temperature on separate lines
```

or:

```text
make the Python parser handle combined Flow/Temp lines explicitly
```

## Temporary Flow Reader

Source:

```text
Arduino/Water flow meter code/Temporary flow reader.cpp
```

This sketch emits:

```text
FlowRate:1.234,TotalLitres:0.567
```

Format:

```text
FlowRate:<l_min_3dp>,TotalLitres:<litres_3dp>
```

This is not currently one of the three main simulated Arduino links in `simulate_arduinos.sh`.

## Simulator Output

The simulator creates:

```text
/tmp/labpulse-fake-serial/pressure
/tmp/labpulse-fake-serial/pump_room
/tmp/labpulse-fake-serial/turbo_pump
```

The simulated `pressure` link follows `Arduino/Pressure_Arduino.cpp`.

The simulated `pump_room` link follows `Arduino/Pump_Room_Arduino.cpp`.

The simulated `turbo_pump` link follows `Arduino/full_water_sensor_code.cpp`, because there is no separate turbo-specific Arduino sketch in the repository at the time of writing.

If a Python service does not parse one of these simulated lines, treat that as a useful parser test rather than a simulator failure.
