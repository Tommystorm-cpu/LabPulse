# Future Hardware USB Setup

This note summarises the current thinking around real Arduino USB devices, stable serial paths, and future setup improvements.

## Current State

The Docker refactor currently reads serial devices from paths configured in the live Pi config:

```text
~/labpulse-ha/config.yaml
```

Each serial service has a `serial_port` field:

```yaml
services:
  pressure_monitor:
    enabled: true
    driver: serial
    parser: pressure
    serial_port: "/dev/serial/by-id/..."
    baud_rate: 9600
    reconnect_interval_seconds: 5
```

For real hardware, the Docker Compose generator mounts:

```text
/dev
```

into each LabPulse Python container. This lets containers read host serial paths such as:

```text
/dev/serial/by-id/usb-Arduino__...
```

## Avoid `/dev/ttyACM0`

Do not rely on paths like:

```text
/dev/ttyACM0
/dev/ttyACM1
```

Those names are assigned by plug-in order. They can change after unplug/replug, reboot, or moving USB ports.

Prefer stable by-id paths:

```text
/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_0353638323635131E2C3-if00
```

These are symlinks based on USB device identity, so they are much more suitable for `config.yaml`.

## Remaining Problem

Stable USB paths identify the Arduino board, but not the physical sensor role.

Linux can show:

```text
/dev/serial/by-id/usb-Arduino__...
```

but it does not know whether that Arduino is:

```text
pressure_monitor
pump_room
turbo_pump
```

That mapping still has to be discovered by a human or by adding identification support to the Arduino sketches.

## Recommended Short-Term Approach

Create a helper script that lists stable serial devices and shows sample output from each one.

Example future command:

```bash
./list_serial_devices.sh
```

Possible output:

```text
Stable path:
  /dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_0353638323635131E2C3-if00

Current kernel path:
  /dev/ttyACM0

Sample lines:
  0.1034
  0.1041
  0.1029
```

From the sample lines, the user can identify the service:

```text
single MPa number              -> pressure_monitor
Flow1/Flow2/RoomTemp/Press1    -> pump_room
Flow1/Flow2/Temp0/Temp1        -> turbo_pump
```

The user then copies the stable `/dev/serial/by-id/...` path into:

```text
~/labpulse-ha/config.yaml
```

## Better Long-Term Approach

Update each Arduino sketch so it can announce its identity.

For example, on startup or command request, an Arduino could print:

```text
DEVICE:pump_room
```

or:

```json
{"device":"pump_room","version":"1.0"}
```

Then a future setup tool could automatically scan all serial devices and write the correct mapping into `config.yaml`.

Example future command:

```bash
./labpulse detect-usb
```

Possible output:

```text
Detected:
  pressure_monitor -> /dev/serial/by-id/usb-Arduino_A
  pump_room        -> /dev/serial/by-id/usb-Arduino_B
  turbo_pump       -> /dev/serial/by-id/usb-Arduino_C
```

## Serial Reconnect Behaviour

The Python serial driver now supports reconnect attempts.

If a USB serial device disappears:

```text
driver marks itself disconnected
old serial handle is closed
service container stays alive
driver periodically tries to reconnect
readings resume when the path returns
```

The retry interval is configured per serial service:

```yaml
reconnect_interval_seconds: 5
```

This helps with both fake USB testing and real Arduino unplug/replug events.

## Development Priority

Recommended next steps:

1. Add a `list_serial_devices.sh` helper that prints `/dev/serial/by-id` paths and sample serial output.
2. Document the manual mapping process in `CONTAINER_SETUP.md`.
3. Later, add Arduino identity messages to the sketches.
4. Eventually, build an automatic USB assignment tool that updates `~/labpulse-ha/config.yaml`.

