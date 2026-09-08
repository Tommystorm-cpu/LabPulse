# Hardware

This page records the hardware boundary that can be stated before the final
installation hardware, enclosure, and custom interface circuits are known. It
is intentionally incomplete. Do not treat it as a wiring or assembly guide.

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

The LabPulse GPIO input and output features are therefore complete at the
software interface boundary: configuration selects a BCM GPIO number and the
software reads or drives that 3.3 V logic point. The electrical interface
between that point and future controlled hardware is deliberately custom and
out of scope until the equipment is selected.

## Identifiers are not interchangeable

Keep these identities distinct:

- Arduino board pin labels belong to firmware and its wiring;
- Raspberry Pi configuration uses BCM GPIO numbers;
- I2C bus numbers and device addresses identify bus devices;
- `/dev/serial/by-id/...` identifies a persistent USB serial device;
- measurement and service names identify software entities, not physical pins.

## Existing hardware assets

Repository PCB and enclosure assets are retained as design references. Their
presence does not establish manufacturing readiness, electrical verification,
fit, accessibility, thermal performance, or compatibility with the final
LabPulse hardware. There is intentionally no top-level `hardware/README.md`.

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

Until those facts exist, use this page only to understand the current software
boundary. LabPulse is monitoring software, not a safety-rated controller;
critical equipment needs independent protection.
