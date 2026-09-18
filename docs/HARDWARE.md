# Hardware

LabPulse's reference installation has a Raspberry Pi main unit and three
Arduino sensor hubs. The Pi runs the dashboard and talks to the hubs over USB.
The hubs sit near the equipment and read its sensors.

This guide covers sensor parts, firmware pin assignments, and connections.
For the Pi, UPS, modem, USB hub, and touchscreen enclosure, go to
[The Raspberry Pi main unit](MAIN_UNIT.md).
You can also [try LabPulse in simulation](FIRST_STEPS.md) without assembling any
of this hardware.

## Choose a starting point

| What you want to do | What's available here | What you still need |
|---|---|---|
| Try the dashboard without sensors | [Installation](INSTALLATION.md) and a [guided first session](FIRST_STEPS.md) | A prepared Pi and a browser; no sensor wiring |
| Connect an Arduino which already produces readings | Firmware examples, a serial format, and a [first-sensor walkthrough](FIRST_SENSOR.md) | Verified wiring and calibration for that board and its sensors |
| Build an Arduino sensor hub from parts | [Recorded parts](#sensor-hub-parts) and [firmware pin assignments](#which-sensor-goes-on-which-hub) | A checked circuit, connector wiring, and calibration for the actual sensors |
| Connect SHT40, DHT11, or X1200 directly to the Pi | Drivers, [configuration examples](CONFIGURATION.md#built-in-drivers), and [main-unit connections](MAIN_UNIT.md#how-the-connections-fit-together) | Check the fitted board revision, wiring, and real readings |
| Read a GPIO signal | [GPIO input settings](CONFIGURATION.md#generic-gpio-input) | A suitable electrical interface between the equipment and the Pi |
| Read a Triton control PC | A [Windows publisher and installation guide](TRITON_PUBLISHER.md) | Access to the control PC and a network plan suited to your lab; the guide describes a particular two-fridge arrangement |
| Operate a relay, valve, or other output | Manual dashboard switches and a [GPIO output driver](CONFIGURATION.md#generic-gpio-output) | A designed and checked switching circuit for the actual load |

If you're starting from loose sensors rather than an existing board, identify
the exact parts and check their datasheets before wiring. The firmware examples
provide pin assignments and conversion settings for adapting a sensor hub.

## Parts and references

Use [LabPulse Purchasing.xlsx](LabPulse%20Purchasing.xlsx) for the parts list,
supplier links, quantities, historical prices, and accessories. Original
purchase records are preserved under
[`legacy/Documentation/purchasing-2026-09-18/`](../legacy/Documentation/purchasing-2026-09-18/README.md).

The [firmware examples](../firmware/README.md#device-configuration) define the
Arduino connections and serial output. The [main-unit guide](MAIN_UNIT.md)
covers the Pi, UPS, display, and enclosure.

## Sensor hub parts

The reference sensor-hub parts include:

| Part | Use |
|---|---|
| Arduino Uno Rev3 | Controller for each of the three serial sensor hubs. |
| Amphenol GE-1337 water-temperature sensor | Thermistors used by the pump-room and turbo-pump examples. |
| DFRobot SEN0217 / YF-S201 1/2-inch water-flow sensor | Pulse-counting flow input for the pump hubs. |
| DFRobot SEN0257 pressure sensor | Compressed-air pressure input. |
| DHT11 | Temperature and humidity input in the pump-room firmware. |
| Adafruit SHT40 STEMMA QT/Qwiic breakout | I2C temperature and humidity input supported by the Pi driver and pressure-monitor firmware. |
| USB-A to USB-B leads | Connect the Uno hubs to the Pi or USB hub. Label both ends with the hub name. |

The original purchases also include 1/2-inch pipe fittings, tees, elbows,
washers, hose tails, and 22 mm compression couplers (rows 17–23). These are
installation-specific plumbing, not enough information to reproduce a checked
pressure or water circuit. Keep the thread type, sealing method, pressure
rating, and sensor position with the eventual circuit drawing.

## Which sensor goes on which hub?

The table below describes the **current example firmware**. The pin names are
Arduino labels. Each hub sends its readings at 9600 baud using the
[standard serial format](../firmware/README.md#pipesamplewriter).

| Hub and source | Arduino connection | Serial measurement names |
|---|---|---|
| [Pressure monitor](../firmware/examples/pressure_monitor/pressure_monitor.h) | Pressure on A0; SHT40 on I2C (Uno SDA/A4 and SCL/A5) | `pressure`, `temperature`, `humidity` |
| [Pump room](../firmware/examples/pump_room/pump_room.h) | Flow on D3 and D2, respectively | `flow1`, `flow2` |
| Pump room | Thermistors on A0–A3 | `temp0`–`temp3` |
| Pump room | DHT11 data on D4 | `roomtemp`, `roomhum` |
| Pump room | Pressure on A5 and A4, respectively | `press1`, `press2` |
| [Turbo pump](../firmware/examples/turbo_pump/turbo_pump.h) | Flow on D2 and D3, respectively | `flow1`, `flow2` |
| Turbo pump | Thermistors on A0–A3 | `temp0`–`temp3` |

Notice that the two flow pins are reversed between the pump-room and
turbo-pump examples. Also, A4 and A5 are already pressure inputs on the
pump-room Uno: don't copy the pressure-monitor SHT40 wiring onto that board
without redesigning those assignments.

The pressure-monitor example samples every second; the other two sample every
five seconds. The [firmware guide](../firmware/README.md#retained-example-calibration)
explains the retained conversion values, including 450 pulses per litre for
flow and the thermistor coefficients. Treat those as existing software
settings until they've been checked against the actual sensor and circuit.

### Where the conversion values came from

The firmware retains conversion settings from the original sensor code. The
source files below show the pressure zero adjustment and thermistor fitting
method. Check the sensor and circuit before reusing a conversion in another
build.

The flow-sensor [purchase link](https://thepihut.com/products/gravity-water-flow-sensor-1-2-for-arduino)
identifies SEN0217/YF-S201. DFRobot specifies **450 pulses per litre**, matching
both pump-hub examples. This confirms agreement with the nominal specification,
not the accuracy of the assembled plumbing and sensors.
[DFRobot SEN0217 specification](https://wiki.dfrobot.com/sen0217).

For the compressed-air SEN0257, DFRobot specifies **0.5–4.5 V for 0–1.6 MPa**.
The original [pressure sketch](../legacy/Arduino/Pressure_Arduino.cpp) explicitly
labels **0.48 V** as the calibrated start voltage at atmospheric pressure and
4.5 V as the manual's maximum output. Its accompanying
[calibration notes](../legacy/Arduino/Compressed%20Air%20sensor/Calibration%20code%20for%20CA%20sensor.cpp)
explain measuring the sensor's voltage at ambient pressure and using that as
the lower endpoint. This documents the reason for the retained 0.48 V value;
it is specific to the original sensor, not a universal setting.
[DFRobot SEN0257 specification](https://wiki.dfrobot.com/sen0257).

The original [water-sensor sketch](../legacy/Arduino/full_water_sensor_code.cpp)
says its thermistor coefficients came from Python curve fitting. The retained
[fitting script](../legacy/Arduino%20code%20Water%20Temperature%20Sensor%20calibration.py)
contains five resistance/temperature pairs and labels them “Datasheet Data”:

| Temperature (°C) | Resistance (Ω) |
|---:|---:|
| -40 | 101770 |
| 25 | 2820 |
| 50 | 988.1 |
| 100 | 179.6 |
| 125 | 88.11 |

The script fits the four-coefficient equation used by the current firmware.
When adapting the firmware, fit coefficients to the selected thermistor's
datasheet and check readings against a reference thermometer.

Use the actual divider resistance in the thermistor conversion. The older
standalone temperature sketch uses 2.2 kΩ; the combined water-sensor sketch
and current firmware use 4.7 kΩ. Set each pressure channel's conversion to
match its transducer's specified range and measured zero.

Once a hub produces trustworthy serial readings, follow
[Connect your first sensor](FIRST_SENSOR.md) to bring it into LabPulse.

## Before connecting a sensor

Keep a short record for each device:

- its manufacturer, model, and board revision;
- its supply voltage and signal levels;
- which wire or connector goes to which pin;
- the unit and range of its output, and how you will check its calibration;
- its USB identity, I2C address, or GPIO assignment, as appropriate;
- its service and measurement names in LabPulse.

These notes make it much easier to identify the right device later or replace
a failed sensor. Label the cable and board to match the record.

For the first connection, check one reading at a time against a suitable
reference. A plausible number on the dashboard isn't proof of correct wiring
or conversion. Add alarm limits after the reading itself is trustworthy.

## Supported acquisition paths

LabPulse currently supports:

- Arduino-compatible controllers that emit the standard line-based serial
  sample format;
- Raspberry Pi GPIO input and explicitly configured GPIO output;
- direct DHT11, SHT40, and X1200 UPS monitoring on a Raspberry Pi;
- named JSON measurements received over MQTT, including the Triton logfile
  publisher.

Driver options and examples are in [Configuration](CONFIGURATION.md). Local
implementation and resource requirements are in the
[hardware package guide](../src/labpulse/hardware/README.md) and
[driver guide](../src/labpulse/hardware/drivers/README.md).

## Raspberry Pi GPIO electrical boundary

Raspberry Pi GPIO uses **3.3 V logic**. A GPIO pin must not be connected to a
5 V logic signal, mains voltage, a solenoid, relay coil, or another load that
exceeds the Pi's electrical limits. Grounds, isolation, transient protection,
level shifting, pull resistors, and output drive circuitry must be designed for
the particular attached equipment.

The authoritative general pin and voltage reference is Raspberry Pi's
[GPIO and 40-pin header documentation](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio-and-the-40-pin-header).
Verify the documentation and datasheets for the exact Pi revision and attached
device before wiring.

LabPulse can read or drive a configured GPIO line. It doesn't provide the
circuit needed to connect that line to arbitrary lab equipment. Choose and
check that circuit for the actual signal or load before using GPIO inputs or
outputs.

## Identifiers are not interchangeable

Keep these identities distinct:

- Arduino board pin labels belong to firmware and its wiring;
- BCM GPIO numbers name Pi signals, while physical header pin numbers describe
  positions on the connector;
- GPIO input/output and X1200 configuration select a Linux `gpio_chip` and a
  `gpio_line` offset within that chip; check the mapping on the actual Pi;
- the DHT11 driver uses a Blinka board pin name, such as `D4`;
- I2C bus numbers and device addresses identify bus devices;
- `/dev/serial/by-id/...` identifies a persistent USB serial device;
- measurement and service names identify software entities, not physical pins.

## Existing hardware assets

The [PCB revision index](../hardware/pcbs/README.md) lists the sensor-hub
manufacturing files. Match the board markings and connections to your sensor
and firmware pin assignments before manufacturing a board.

The [enclosure folder](../hardware/enclosure/README.md) contains the touchscreen
case's Fusion assembly archive and STEP export. See
[the CAD files and build status](MAIN_UNIT.md#enclosure-files-and-build-status)
for the main-unit design.

The obsolete STLs and original attribution notes are preserved under
[`legacy/hardware/3d_parts/`](../legacy/hardware/3d_parts/). These are not print
files for the touchscreen case, and `Tall boi With hole!.stl` is only a newline.

> **Photo to add: one verified sensor hub (optional).** Show the main parts,
> connectors, and USB connection. Name the firmware example it uses and any
> differences from its pin assignments.

## What still needs a bench check

When using these examples in another lab, check your sensor's supply, output,
pin assignment, and conversion against its datasheet and a reference reading.
The existing firmware values describe particular sensors; a replacement that
physically fits may produce a different electrical output.

The recorded installation is an example, not a layout every lab must copy.
Straightforward Arduino connections can be described by the pin assignments
and sensor instructions. Add a circuit drawing where custom circuitry needs
explaining; there is no requirement to document every cable or plumbing fitting
to finish the LabPulse guides.

LabPulse is monitoring software, not a safety-rated controller; critical
equipment needs independent protection.
