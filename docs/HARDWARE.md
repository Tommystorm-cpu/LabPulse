# Hardware

LabPulse's reference installation has a Raspberry Pi main unit and three
Arduino sensor hubs. The Pi runs the dashboard and talks to the hubs over USB.
The hubs sit near the equipment and read its sensors.

This guide brings together the parts bought for that installation, the current
firmware, and the later enclosure discussions. For the Pi, UPS, modem, USB hub,
and touchscreen enclosure, go to [The Raspberry Pi main unit](MAIN_UNIT.md).
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

The simulation route is documented from installation to a working dashboard.
The Arduino walkthrough covers the software connection once a sensor board is
working. There isn't yet a complete, verified shopping-and-assembly guide for
a new lab to reproduce the whole physical installation.

If you're starting from loose sensors rather than an existing board, don't
assume that a firmware example is also a complete wiring plan. Start by
identifying the exact parts and checking their datasheets.

## Where the hardware information comes from

Use [LabPulse Purchasing.xlsx](LabPulse%20Purchasing.xlsx) for the consolidated
parts list, supplier links, known quantities, historical prices, and requested
additions. Its **Earlier choices** sheet separates replaced or incompatible
parts. Unknown details remain labelled, and an email request does not establish
that a part has arrived.

The original workbooks are archived unchanged. They describe different stages
of the project; a purchased part isn't necessarily the part still fitted today.

| Record | What it tells us |
|---|---|
| [Internship purchased items](../legacy/Documentation/purchasing-2026-09-18/Internship%20purchased%20items.xlsx), Sheet1 | Original purchases and supplier links. Rows 2–15 cover the main electronics; rows 17–24 include plumbing and the older USB hubs. The note in E12 names the replacement UPS. |
| [Mini Shopping List](../legacy/Documentation/purchasing-2026-09-18/Mini%20Shopping%20List.xlsx), Sheet1, rows 2–6 | Later choices for a powered hub, SHT40, Gravity board, sensor cable, and GPIO ribbon. The sensor cable turned out not to fit; see the [main-unit connection notes](MAIN_UNIT.md#gravity-board-and-room-sensor). |
| [Shopping email and maintainer update, recorded 18 September 2026](MAIN_UNIT.md#additional-parts-requested) | Confirms the X1200 and planned mains-powered USB hub. Lists display accessories and two SHT40 cables; the SHT40 connections are not installed yet. |
| [LabPulse Sensors](../legacy/Documentation/purchasing-2026-09-18/LabPulse%20Sensors.xlsx), Sheet1, rows 2–10 | Sensor counts and locations, plus an undated snapshot of which readings worked. It predates the current SHT40 configuration. |
| [Firmware examples](../firmware/README.md#device-configuration) and [starter configuration](../config.yaml) | What the current source expects. The live installation's configuration and flashed firmware still need to match. |
| [July 2026 acceptance record](../ROADMAP.md#real-hardware-reliability) | What was tested on the Pi, including the faulty USB hub and DHT11 that prompted replacement work. |

The [main-unit guide](MAIN_UNIT.md#enclosure-history) also records the decisions
recovered from the July and August 2026 CAD chats. Those discussions include
prototypes and abandoned suggestions, so they aren't a finished assembly record.

## Sensor hub parts

These are the parts we can identify from the purchase and sensor records.
Quantities describe the recorded installation, not a universal shopping list.
The supplier links in the workbooks are useful for identifying replacements;
their old prices aren't a current quotation.

| Part | Recorded quantity | Where it belongs and what we know |
|---|---:|---|
| Arduino Uno Rev3 | 3 | One controller for each serial sensor hub. Purchase row 3. |
| Amphenol GE-1337 water-temperature sensor | 8 | Four thermistors on the pump-room hub and four on the turbo-pump hub. Purchase row 6; matching connectors are in row 7, RS stock 8011017. |
| DFRobot SEN0217 / YF-S201 1/2-inch water-flow sensor | 4 | Two per pump hub. The supplier link in purchase Sheet1 A5 identifies SEN0217/YF-S201; sensor-inventory A4 and A6 link to the same product. This is identification from the purchase record, not a check of the fitted markings. |
| DFRobot SEN0257 pressure sensor | 1 | The pressure-monitor hub. Purchase row 4 says `SEN057`, but its supplier link and sensor-inventory row 10 both identify **SEN0257**. |
| Pressure sensors recorded as “Triton 1/2 (Unknown Model)” | 2 | Pump-room hub. Their manufacturer, range, and exact model still need reading from the hardware. Don't assume they are SEN0257s. |
| DHT11 | 2 in the older inventory | One on the pump-room Arduino and one formerly on the Pi. The current starter config uses an SHT40 for the Pi's room readings; the pump-room firmware still uses DHT11. |
| Adafruit SHT40 STEMMA QT/Qwiic breakout | Two planned connections; fitted quantity not established | The maintainer reports that the SHT40 is not connected yet. Planned cables serve the Pi and the compressed-air Arduino, with the latter measuring main-lab temperature and humidity. See the [additional parts](MAIN_UNIT.md#additional-parts-requested). |
| USB-A to USB-B leads | One 3 m, two 5 m | Purchase rows 14–15. These connect the Uno hubs to the Pi or its USB hub. Label both ends with the hub name. |

The original purchases also include 1/2-inch pipe fittings, tees, elbows,
washers, hose tails, and 22 mm compression couplers (rows 17–23). These are
installation-specific plumbing, not enough information to reproduce a checked
pressure or water circuit. Keep the thread type, sealing method, pressure
rating, and sensor position with the eventual circuit drawing.

## Which sensor goes on which hub?

The table below describes the **current example firmware**, not a continuity
check of an assembled PCB. The pin names are Arduino labels. Each hub sends
its readings at 9600 baud using the [standard serial format](../firmware/README.md#pipesamplewriter).

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

On 18 September 2026, the maintainer confirmed that the conversion values were
inherited from the original code. All three workbooks were checked, including
their supplier links. They identify purchased parts and earlier observations,
but contain no calibration coefficients, reference measurements, or record of
a calibration check. The original Arduino sources do document conversion
methods, as described below. The Mini Shopping List adds the later SHT40 and
main-unit parts; it does not identify the unknown pump-room pressure sensors.

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
It does not name the source datasheet or its revision. This establishes the
documented fitting method and retained inputs, but is not a record of checking
each assembled temperature channel against a reference thermometer.

The pump-room pressure sensor models remain unknown, so their inherited
conversions cannot yet be tied to a particular sensor specification. Check the
actual sensors and divider resistors when reusing these examples. The older
standalone temperature sketch used a 2.2 kΩ resistor; the combined water-sensor
sketch and current firmware use 4.7 kΩ.

The old inventory reports zero flow on all four flow sensors, zero on both
pump-room pressure channels, and only two working turbo-pump temperature
channels. Those are observations from an undated record, not a diagnosis or
today's status. In particular, zero flow can mean either stopped flow or a
missing pulse signal. Recheck the channels before relying on their alarms.

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

The [PCB directory](../hardware/PCB_files/) contains `PCBv6.zip` and several
Arduino-HAT Gerber archives named prototype1, prototype2, prototype3, and
Final_prototype. A Gerber archive contains board-manufacturing artwork; its
filename doesn't establish which revision is fitted or whether it was tested.
Match the board markings and trace its connections before using one as the
assembly reference.

The [3D-parts README](../hardware/3d_parts/README.txt) explicitly marks the two
STLs beside it as old and no longer used. They are not the touchscreen case
from the later CAD discussions. See the [enclosure history](MAIN_UNIT.md#enclosure-history)
before choosing a model to print.

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
