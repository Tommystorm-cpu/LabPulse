# Hardware

You can try LabPulse without sensors, connect an existing Arduino sensor hub,
or use one of the supported Pi interfaces. The software supports all of these,
but the build instructions aren't equally complete. This page helps you choose
a starting point and work out what information you need before connecting it.

## Choose a starting point

| What you want to do | What's available here | What you still need |
|---|---|---|
| Try the dashboard without sensors | [Installation](INSTALLATION.md) and a [guided first session](FIRST_STEPS.md) | A prepared Pi and a browser; no sensor wiring |
| Connect an Arduino which already produces readings | Firmware examples, a serial format, and a [first-sensor walkthrough](FIRST_SENSOR.md) | Verified wiring and calibration for that board and its sensors |
| Build an Arduino sensor hub from parts | [Firmware component descriptions and example pin assignments](../firmware/README.md) | Exact part numbers, a checked circuit, and assembly instructions for your build |
| Connect SHT40, DHT11, or X1200 directly to the Pi | Drivers and [configuration examples](CONFIGURATION.md#built-in-drivers) | Instructions for the exact board revision, its connections, and checks of the real readings |
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
- Raspberry Pi configuration uses BCM GPIO numbers;
- I2C bus numbers and device addresses identify bus devices;
- `/dev/serial/by-id/...` identifies a persistent USB serial device;
- measurement and service names identify software entities, not physical pins.

## Existing hardware assets

The repository contains PCB and enclosure design files. Treat them as design
references until you've checked the revision, circuit, fit, and cooling against
the parts you intend to use. Their presence in the repository doesn't mean
they're a finished build kit.

> **Photo to add: one verified sensor hub.** Show the board, sensor part numbers,
> connector labels, and USB connection. Link the photo to its checked pin table
> and calibration notes so readers know which build it documents.

> **Photo to add: the assembled installation.** Show cable labels, power
> connections, and enclosure layout. Name the hardware revisions shown; don't
> use an unverified prototype as the assembly reference.

## To complete when hardware is selected

The eventual build-and-wire documentation must add verified:

- bill of materials, part numbers, revisions, and suppliers;
- complete schematics and connector/pin tables;
- custom TTL/GPIO input and output interface circuits for the selected loads;
- power distribution, fusing, grounding, isolation, and enclosure bonding;
- photos of assembly, wiring, labels, strain relief, and finished installation;
- enclosure drawings, touchscreen/display mounting, clearances, and cooling;
- commissioning measurements and acceptance results for each physical input
  and output;
- maintenance, safe replacement, and decommissioning instructions.

Until that build record is complete, use the available software guides
alongside the instructions for your exact hardware. LabPulse is monitoring
software, not a safety-rated controller; critical equipment needs independent
protection.
