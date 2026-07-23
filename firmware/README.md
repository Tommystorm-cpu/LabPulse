# LabPulse Arduino firmware

This guide takes a first-time Arduino user from the downloaded LabPulse files
to a working Arduino. The supplied examples match the current LabPulse
hardware and send readings to the Raspberry Pi in the required pipe-delimited
format.

> **Important:** this `firmware` folder is an Arduino **library**, not a single
> standalone sketch. Install the complete folder before opening an example.
> Opening an `.ino` file directly from the repository causes errors such as
> `LinearPressureSensor.h: No such file or directory`.

## Before you begin

You need:

- a Raspberry Pi with Arduino IDE 1.8.19 for Linux ARM installed;
- an Arduino Uno and USB cable;
- a copy of this `firmware` directory.

Arduino does not provide an official Raspberry Pi/ARM build of Arduino IDE 2.
On a Pi, use the Linux ARM 32-bit or ARM 64-bit release of Arduino IDE 1.8.19.
The older IDE supplied by Raspberry Pi OS may not find current libraries.

### Install or update Arduino IDE on the Raspberry Pi

1. Open **Terminal** from the Raspberry Pi menu.
2. Enter `uname -m` and press Enter.
3. Download Arduino IDE 1.8.19 from the
   [official Arduino software page](https://www.arduino.cc/en/software):
   - choose **Linux ARM 64 bits** if the command printed `aarch64`;
   - choose **Linux ARM 32 bits** if it printed `armv7l`.
4. In File Manager, open `Downloads`, right-click the downloaded archive, and
   extract it. This creates a directory named `arduino-1.8.19`.
5. Return to Terminal and run:

   ```bash
   cd ~/Downloads/arduino-1.8.19
   sudo ./install.sh
   ```

6. Start Arduino and select **Help > About Arduino**. Confirm it reports
   version 1.8.19 before removing an older installation.

Before flashing a connected board, record:

- which LabPulse device it belongs to;
- its current USB port and stable `/dev/serial/by-id/...` path on the Pi;
- its current sketch and wiring;
- any calibration values that differ from the supplied examples.

Flash only one identified Arduino at a time.

## Step 1: install LabPulseFirmware

Arduino must see the complete folder as an installed library. Follow these
steps even if the example `.ino` files are already visible in the repository.

1. Open Arduino IDE and select **File > Preferences**.
2. Read the path beside **Sketchbook location**. On a Raspberry Pi it is
   normally `/home/your-username/Arduino`.
3. Do **not** set the sketchbook location to the LabPulse repository. The
   repository is where the source files are stored; the sketchbook is where
   Arduino looks for installed libraries. If it currently points to the
   repository, change it back to `/home/your-username/Arduino`.
4. Close Arduino IDE.
5. Open the Pi's File Manager and browse to that sketchbook directory.
6. Create a folder named `libraries` inside it if one is not already present.
7. Copy the **complete** LabPulse `firmware` folder into `libraries`.
8. Rename the copied folder to `LabPulseFirmware`.

The result must have this structure:

```text
Arduino/
  libraries/
    LabPulseFirmware/
      library.properties
      src/
      examples/
```

Do not copy only `examples`, and do not put `LabPulseFirmware` inside a second
`firmware` folder.

9. Start Arduino IDE again.
10. Select **File > Examples**. A section named **LabPulseFirmware** should now
   appear. If it does not, recheck the folder structure above.

## Step 2: install the required Arduino libraries

1. In Arduino IDE 1.8.19, select
   **Sketch > Include Library > Manage Libraries...**
2. Wait for the library list to finish downloading.
3. Search for exactly `DHT sensor library`.
4. Select **DHT sensor library by Adafruit**. Do not select `TinyDHT`.
5. Click **Install** and accept the **Adafruit Unified Sensor** dependency if
   prompted.
6. Select **Tools > Board > Boards Manager...**, search for
   `Arduino AVR Boards`, and install it if it is not already installed.

## Step 3: choose the correct firmware

Open the required example through **File > Examples > LabPulseFirmware**.
Always open it from this menu; do not open the repository's `.ino` file
directly.

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

For the conversion equations, coefficients, validation ranges, and the exact
difference between numeric zero and `null`, see
[`src/README.md`](src/README.md).

If your wiring or calibration differs, edit the `.h` file beside the selected
example before uploading:

```text
examples/pressure_monitor/pressure_monitor.h
examples/pump_room/pump_room.h
examples/turbo_pump/turbo_pump.h
```

Near the top of each `.h` file is an authoritative **pin-to-measurement map**.
Each entry contains the Arduino pin followed by the emitted name, for example:

```cpp
constexpr LabPulse::PinMeasurement FLOW1 = {3, "flow1"};
```

Edit `3` to change the input pin, or edit `"flow1"` to change the serial name.
The sensor configuration and `.cpp` output both use this record, so neither
value is duplicated elsewhere.

Do not change measurement names unless the same names are also used in the
live Pi configuration at `~/labpulse-live/config.yaml`.

## Step 4: verify and upload

1. Connect the identified Arduino.
2. In Arduino IDE, select **Tools > Board > Arduino AVR Boards > Arduino Uno**.
3. Select the connected Arduino under **Tools > Port**. On a Raspberry Pi it
   normally looks like `/dev/ttyACM0` or `/dev/ttyACM1`.
4. Click the tick-mark **Verify** button. Successful verification ends with a
   message about sketch and memory usage, without an orange error banner.
5. Recheck that the selected example belongs to the connected physical board.
6. Click the right-arrow **Upload** button. Wait for `Done uploading` before
   disconnecting anything.

No Python build script is required. Arduino IDE compiles the example and its
sensor files into the flashable firmware automatically.

## Step 5: check the serial output

After uploading:

1. Stop the LabPulse service that normally reads this Arduino. Serial Monitor
   and LabPulse must not read the same serial port at the same time.
2. Open **Tools > Serial Monitor**.
3. Set the baud rate to **9600**.
4. Confirm that one complete sample appears on each line.

A pump-room sample should look like this single line:

```text
flow1: 2.45 | flow2: 3.10 | temp0: 20.11 | temp1: 20.22 | temp2: 20.33 | temp3: 20.44 | roomtemp: 21.2 | roomhum: 45.0 | press1: 1.23 | press2: 1.45
```

Every key must match a measurement configured for that service on the Pi.
Values contain no unit text because units are defined in LabPulse configuration.
An unavailable or invalid sensor channel appears as `null`.

## Reconnect it to LabPulse

On the Pi, the corresponding service in `~/labpulse-live/config.yaml` must use:

```yaml
driver:
  type: labpulse.serial_pipe
  options:
    port: "/dev/serial/by-id/usb-Arduino_..."
    baud_rate: 9600
```

Use the stable `/dev/serial/by-id/...` path rather than `/dev/ttyUSB0` or
`/dev/ttyACM0`. After updating the live configuration, regenerate/restart
LabPulse through its normal setup workflow and confirm every measurement in
Home Assistant.

## Adapt an example for another lab

When a lab needs a different mixture of sensors:

1. Copy the closest directory under `examples/` and give the directory, `.ino`,
   `.h`, and `.cpp` files the same new base name.
2. Put pins, calibration values, intervals, and output precision in the `.h`.
3. In the `.cpp`, construct the required sensor objects from those settings.
4. Read each sensor and pass every result to `PipeSampleWriter` in the required
   output order.
5. Add exactly the same measurement names to the service in the Pi's live
   `~/labpulse-live/config.yaml`.

Do not write another serial format or add units to the Arduino output. Reuse
the supplied sensor classes and `PipeSampleWriter` so the normal LabPulse
serial path continues to work.

The complete file templates, sensor configuration fields, setup/loop pattern,
flow-interrupt example, and output rules are documented in
[`../docs/ARDUINO_AND_CPP.md`](../docs/ARDUINO_AND_CPP.md#writing-a-new-device-firmware).

## Troubleshooting

### `LinearPressureSensor.h: No such file or directory`

The example was opened directly, or the LabPulse library is in the wrong
directory. Repeat **Step 1**, restart Arduino IDE, and open the example only
through **File > Examples > LabPulseFirmware**. In particular, make sure
**File > Preferences > Sketchbook location** is the same sketchbook directory
that contains `libraries/LabPulseFirmware`.

### `DHT.h: No such file or directory`

Install **DHT sensor library** by Adafruit from Arduino IDE's Library Manager.
Accept its **Adafruit Unified Sensor** dependency when prompted. This is the
library that provides the `DHT.h` header used by the firmware.

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

### Serial Monitor shows incomplete or mixed-up text

Another program is probably reading the Arduino at the same time. Close Serial
Monitor and run `sudo fuser -v /dev/ttyACM1`, replacing the port if necessary.
Stop the listed LabPulse service before reopening Serial Monitor. Only one
program can reliably consume the serial stream.

For protocol, calculation, and implementation details, see
[`../docs/ARDUINO_AND_CPP.md`](../docs/ARDUINO_AND_CPP.md).
