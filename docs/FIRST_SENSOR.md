# Connect your first sensor

This walkthrough connects one Arduino pressure reading to LabPulse. You'll
identify the board, give LabPulse a small configuration, and check the result
on the dashboard. Start with [the simulated walkthrough](FIRST_STEPS.md) if you
haven't used LabPulse before.

Adding support for a different sensor to the open-source project? Follow
[Contributing sensors](../CONTRIBUTING.md#contributing-sensors) for the firmware,
driver, testing, and GitHub pull-request steps.

You need a Pi with LabPulse installed and an Arduino with a working, correctly
wired pressure sensor. This is the software setup, not a pressure-sensor wiring
guide. Check [the hardware guide](HARDWARE.md) and your sensor's documentation
before connecting it.

Use a new or dedicated practice installation. The example below replaces its
configuration with one service. Don't paste it over an existing lab's settings;
for an existing installation, make a backup and add the service to its existing
`services` section instead. Add the setup under `setups` too, or use the ID of
one you've already defined. Keep existing IDs unique.

## 1. Check what the Arduino sends

**On the computer connected to the Arduino**, install the
[LabPulse firmware library](../firmware/README.md#install-the-library) and
choose the example that matches your hardware. The `pressure_monitor` example
includes pressure, temperature, and humidity. Its pressure conversion assumes
a particular calibration; check [those assumptions](../firmware/README.md#pressure-monitor)
against your actual sensor before using it.

After uploading, open the Arduino IDE's Serial Monitor at **9600 baud**. A
usable pressure field looks like this:

```text
pressure: 1.20 | temperature: 20.10 | humidity: 45.0
```

Those numbers are illustrative. Your values should match what the sensors
measure. `pressure: null` means there isn't a usable pressure value; fix that
before going on. The label `pressure` is what LabPulse will match, and the
firmware's pressure value must be in **bar** for this example.

Close Serial Monitor when you've checked the output. Only one program should
use the serial port at a time. Connect the Arduino to the Pi with a USB data
cable if it isn't already connected there.

## 2. Find the board on the Pi

**In the Pi's terminal**, run:

```bash
ls -l /dev/serial/by-id/
```

Find the entry for your Arduino and copy its full path, starting with
`/dev/serial/by-id/`. With several boards connected, use
[Assigning serial devices](TROUBLESHOOTING.md#assigning-serial-devices) to check
which is which. If the directory is missing, check the USB data cable and that
the Pi recognises the board before continuing.

Use this persistent path rather than `/dev/ttyUSB0` or `/dev/ttyACM0`, whose
number can change when devices are reconnected.

For example, a listing might contain `usb-Arduino_Example-if00 -> ../../ttyACM0`.
The path to copy would be `/dev/serial/by-id/usb-Arduino_Example-if00`, not
`../../ttyACM0`. This name is illustrative; use the one printed for your board.

## 3. Describe one reading

Run `labpulse config` **on the Pi**, then select `config.yaml`. On a new practice
installation, replace its contents with the
[complete one-sensor example](examples/minimal-serial.yaml):

```yaml
timezone: Europe/London
mqtt:
  broker: mosquitto
sms:
  dry_run: true
setups:
  compressed_air:
    label: Compressed Air
services:
  pressure_monitor:
    label: Pressure Monitor
    driver:
      type: labpulse.serial_pipe
      options:
        port: /dev/serial/by-id/REPLACE_WITH_YOUR_BOARD
        baud_rate: 9600
    measurements:
      pressure:
        label: Pressure
        setups: [compressed_air]
        unit: bar
        device_class: pressure
        show_graph: true
```

Replace the port with the path from step 2 and set your timezone. The port above
is a placeholder, not a device that exists. For help with spacing and editing,
see [YAML basics](CONFIGURATION.md#a-few-yaml-basics).

The example asks LabPulse to read one Arduino through `labpulse.serial_pipe`,
take the field named `pressure`, and show it in the **Compressed Air** setup.
The other serial fields are ignored because this configuration doesn't request
them. `unit: bar` labels the value; it doesn't convert a reading from another
unit. `show_graph: true` adds a graph to the dashboard.

Save and close the editor. LabPulse checks the configuration before applying
it. If it reports a file and field with an error, correct those and try again.
Keep `sms.dry_run: true` while testing.

## 4. Start reading real hardware

If you've been using simulation, saving the configuration keeps simulation
enabled. To switch to the Arduino, run **on the Pi**:

```bash
labpulse down
labpulse setup
labpulse up
labpulse ps
labpulse doctor
```

If the installation was already using real hardware, saving a changed
configuration can start its workers immediately. You can check them with
`labpulse ps` and `labpulse doctor`.

In Home Assistant, keep **Test mode** and **Mute all notifications** on. Open
**System Status**: **Pressure Monitor** should say **Working**, with a current
pressure reading. Open **Monitor** to find it under **Compressed Air**.

If it doesn't appear, inspect the service's logs:

```bash
labpulse logs --tail 100 labpulse-pressure-monitor
```

Check the port, baud rate, and `pressure` field name before changing alarm
settings. [Serial troubleshooting](TROUBLESHOOTING.md#serial-readings-are-missing-or-stale) covers missing devices
and stale readings.

## 5. Check the reading, then set an alarm

Compare the displayed pressure with a suitable reference instrument. Seeing
**Working** proves that data is arriving; it doesn't prove the calibration.
If the units or values don't agree, fix the firmware conversion or configuration
before using alarms.

With this practice board, unplug its USB connection and watch **System Status**.
After LabPulse detects the loss, the service should stop showing **Working**.
Reconnect it and check that fresh readings return. Detection and recovery have
delays, so don't expect every dashboard state to change instantly.

Open **Alarm Setup**, select **Configure** beside **Compressed Air**, then
**Configure** beside pressure. Set the mode, limits, and timing for your actual system using
[Configuring alarms](USER_GUIDE.md#configuring-alarms). Test a suitable condition
and recovery before enabling notifications. The practice limits from the
simulation guide are not operating limits for your equipment.

When the reading and alarms behave as expected, save a backup:

```bash
labpulse backup ~/labpulse-first-sensor.tar.gz
```

Use a new filename if that backup already exists. Follow
[Testing SMS](USER_GUIDE.md#testing-sms) separately if you want real text messages.

Keep a short record with the board: its sensor model, firmware revision, USB
path, measurement unit, and the reference reading used to check it. You now
have one identified sensor producing a checked reading; those notes make it
possible for someone else to replace or troubleshoot it later.
