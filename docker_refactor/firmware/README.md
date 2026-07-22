# LabPulse Arduino firmware

This guide explains how to install, configure, and flash the Arduino firmware
used by LabPulse. The supplied examples match the current LabPulse hardware and
send readings to the Raspberry Pi in the required pipe-delimited format.

## Before you begin

You need:

- Arduino IDE;
- an Arduino Uno and USB cable;
- the Arduino AVR Boards package;
- the Arduino **DHT sensor library**;
- a copy of this `firmware` directory.

Before flashing a connected board, record:

- which LabPulse device it belongs to;
- its current USB port and stable `/dev/serial/by-id/...` path on the Pi;
- its current sketch and wiring;
- any calibration values that differ from the supplied examples.

Flash only one identified Arduino at a time.

## Install in Arduino IDE

Install this directory as the Arduino library `LabPulseFirmware` using either
method below.

### Install from a ZIP

1. Create or download a ZIP whose top-level folder contains
   `library.properties`, `src`, and `examples`.
2. In Arduino IDE, select **Sketch > Include Library > Add .ZIP Library**.
3. Select the ZIP.
4. Allow Arduino IDE to install the declared DHT library dependency if asked.

### Install from the repository

1. Open the Arduino sketchbook directory shown under
   **File > Preferences > Sketchbook location**.
2. Create its `libraries` directory if it does not exist.
3. Copy this complete `firmware` directory to:

   ```text
   <sketchbook>/libraries/LabPulseFirmware
   ```

4. Restart Arduino IDE.
5. Install **DHT sensor library** through **Tools > Manage Libraries** if it is
   not already installed.

## Choose the correct firmware

Open the required example through **File > Examples > LabPulseFirmware**.

| Example | Current measurements | Interval |
| --- | --- | --- |
| `pressure_monitor` | compressed-air `pressure` | 1 second |
| `pump_room` | `flow1`, `flow2`, `temp0`-`temp3`, `roomtemp`, `roomhum`, `press1`, `press2` | 5 seconds |
| `turbo_pump` | `flow1`, `flow2`, `temp0`-`temp3` | 5 seconds |

The supplied configurations match the current LabPulse installation:

| Device | Current wiring and calibration |
| --- | --- |
| Pressure monitor | pressure on A0; 0.48-4.5 V represents 0-1.6 MPa |
| Pump room | flow on D3/D2 at 450 pulses per litre; thermistors on A0-A3 with 4.7 kOhm fixed resistors; DHT11 on D4; pressure on A5/A4 |
| Turbo pump | flow on D2/D3 at 450 pulses per litre; thermistors on A0-A3 with 4.7 kOhm fixed resistors |

If your wiring or calibration differs, edit the `.h` file beside the selected
example before uploading:

```text
examples/pressure_monitor/pressure_monitor.h
examples/pump_room/pump_room.h
examples/turbo_pump/turbo_pump.h
```

Do not change measurement names unless the same names are also used in the
live Pi configuration at `~/labpulse-ha/config.yaml`.

## Verify and upload

1. Connect the identified Arduino.
2. In Arduino IDE, select **Tools > Board > Arduino AVR Boards > Arduino Uno**.
3. Select the exact board under **Tools > Port**.
4. Click **Verify** and resolve any compilation error before continuing.
5. Recheck that the selected example belongs to the connected physical board.
6. Click **Upload**.

No Python build script is required. Arduino IDE compiles the example and its
sensor files into the flashable firmware automatically.

## Check the serial output

After uploading:

1. Open **Tools > Serial Monitor**.
2. Set the baud rate to **9600**.
3. Confirm that one complete sample appears on each line.

Pressure example:

```text
pressure: 1.03
```

Pump-room example:

```text
flow1: 2.45 | flow2: 3.10 | temp0: 20.11 | temp1: 20.22 | temp2: 20.33 | temp3: 20.44 | roomtemp: 21.2 | roomhum: 45.0 | press1: 1.23 | press2: 1.45
```

Every key must match a measurement configured for that service on the Pi.
Values contain no unit text because units are defined in LabPulse configuration.
An unavailable or invalid sensor channel appears as `null`.

## Reconnect it to LabPulse

On the Pi, the corresponding service in `~/labpulse-ha/config.yaml` must use:

```yaml
driver: serial
parser: pipe
baud_rate: 9600
serial_port: "/dev/serial/by-id/usb-Arduino_..."
```

Use the stable `/dev/serial/by-id/...` path rather than `/dev/ttyUSB0` or
`/dev/ttyACM0`. After updating the live configuration, regenerate/restart
LabPulse through its normal setup workflow and confirm every measurement in
Home Assistant.

## Troubleshooting

### `DHT.h: No such file or directory`

Install **DHT sensor library** from Arduino IDE's Library Manager. Accept its
Adafruit Unified Sensor dependency when prompted.

### The board or port is missing

Reconnect the USB cable, try a known data-capable cable, and reopen the
**Tools > Port** menu. Do not select a port until the physical board has been
identified.

### A channel prints `null`

Check that sensor's wiring, supply, connector, pin assignment, and calibration.
One invalid channel does not stop the remaining channels from being reported.

### Flow remains zero

Zero flow is a valid reading. Confirm operation with real flow or a controlled
pulse test; firmware cannot distinguish a stationary flow meter from a
disconnected meter that produces no pulses.

### Values appear under the wrong LabPulse device

Stop the affected service and repeat the Pi USB-identification process. Confirm
the board's physical role and `/dev/serial/by-id/...` mapping before restarting
monitoring.

For protocol, calculation, and implementation details, see
[`../docs/ARDUINO_AND_CPP.md`](../docs/ARDUINO_AND_CPP.md).
