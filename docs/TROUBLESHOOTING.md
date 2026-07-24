# Troubleshooting

Start with:

```bash
labpulse doctor
labpulse ps --all
```

Then inspect the failing layer in this order:

```text
host hardware
  → hardware container
  → Mosquitto
  → Home Assistant entity
  → alarm automation
  → SMS worker and modem
```

Avoid changing several layers at once. Confirm the last known-good boundary
before moving downstream.

## Installation is missing

Symptom:

```text
missing compose.yaml
Run 'labpulse setup' first
```

Run:

```bash
labpulse setup
```

For an alternate installation, pass the global option before the command:

```bash
labpulse --live-dir /path/to/live setup
```

## Docker cannot run

Check:

```bash
sudo systemctl status docker
sudo docker compose version
```

LabPulse defaults to `sudo docker` for a non-root Linux user when `sudo` is
available. An installation configured for Docker-group access can use:

```bash
export LABPULSE_DOCKER_COMMAND=docker
```

Use the same setting for later commands or place it in the operator's shell
configuration.

## Configuration is rejected

Use:

```bash
labpulse config
```

The validator reports a path such as:

```text
services → pressure_monitor → driver → options → port
```

Check:

- YAML indentation and colons;
- required service and measurement fields;
- exact registered driver ID;
- driver-owned option names;
- duplicate measurement names;
- setup IDs and measurement membership;
- SMS international number formatting;
- X1200 required measurements and power settings.

Do not edit `config.fake.yaml`; regenerate fake mode from `config.yaml`.

## Containers exit immediately

```bash
labpulse ps --all
labpulse logs --tail 200 SERVICE
```

Frequent causes:

- the container cannot reach `mosquitto`;
- the runtime config still says `localhost`;
- the hardware path does not exist;
- a driver dependency failed to install;
- configuration copied into the build context is stale;
- the image was not rebuilt after setup.

Refresh and rebuild:

```bash
labpulse setup
labpulse up --build
```

Inside LabPulse Python containers, MQTT must be `mosquitto:1883`.

## MQTT connection refused

Check broker status:

```bash
labpulse ps
labpulse logs --tail 100 mosquitto
```

Addresses are intentionally different:

| Client | Broker |
|---|---|
| LabPulse Python containers | `mosquitto:1883` |
| Home Assistant host network | `127.0.0.1:1883` |
| Pi host diagnostics | `127.0.0.1:1883` |

`localhost` inside a sensor container means that sensor container itself, not
Mosquitto.

## Real serial device is missing

Stop competing containers and inspect stable paths:

```bash
labpulse down
ls -l /dev/serial/by-id/
cd ~/labpulse-live
./setup_usb_devices.py --config config.yaml --dry-run
```

Then run the interactive assignment without `--dry-run`.

Avoid `/dev/ttyUSB0` and `/dev/ttyACM0`; enumeration can change after reconnect
or reboot.

If the helper reports zero or multiple changes, reconnect all devices, ensure
only the requested one is unplugged, and repeat. It deliberately refuses to
guess.

## Fake serial data does not appear

Fake setup and simulator startup are separate:

```bash
labpulse setup --fake-usb
cd ~/labpulse-live
./simulate_serial.py start
./simulate_serial.py status
labpulse up --build
```

Check:

```bash
ls -l /tmp/labpulse-fake-serial/
labpulse doctor
labpulse logs --tail 100 labpulse-pressure-monitor
```

If real paths appear in diagnostics, rerun fake setup so Compose mounts
`config.fake.yaml`.

## Serial service repeatedly reconnects

Inspect its log:

```bash
labpulse logs -f labpulse-SERVICE-SLUG
```

Verify:

- the configured stable path exists on the host;
- the device is not open in the Arduino IDE or another process;
- baud rate matches firmware;
- each line follows the standard protocol;
- measurement names match the service config;
- the USB cable and power are stable.

Malformed or unit-bearing values are rejected. See
[Serial protocol](SERIAL_PROTOCOL.md).

## DHT11 is unavailable

Confirm real rather than fake mode and inspect:

```bash
labpulse doctor
labpulse logs -f labpulse-room-environment
```

Verify the configured Blinka pin name and physical wiring. Individual DHT timing
misses are tolerated. Sustained missing samples become stale; unexpected
GPIO/library failures close and reconnect the driver.

LabPulse deliberately constructs the DHT11 with `use_pulseio=False` on Raspberry
Pi. Errors such as `unsigned short is greater than maximum` indicate that an
older PulseIn-enabled build is still deployed; update and rebuild the
`labpulse-room-environment` container. A one-time sensor power cycle may be
needed if the previous process left the DHT11 data line wedged.

Only the DHT service should need broad `/dev` access for this sensor. Rebuild
current source if unrelated workers appear to claim GPIO devices.

## X1200 power monitoring fails

Check:

```bash
ls -l /dev/i2c-1 /dev/gpiochip0
labpulse doctor
labpulse logs -f labpulse-ups-monitor
```

Confirm the configured bus, GPIO chip, line, and polarity. The MAX17043 address
is fixed at `0x36`.

An I2C read failure makes the hardware connection unavailable. A GPIO-only
failure is reported as a component fault while battery voltage and level can
continue; Home Assistant must treat it as Sensor Fault rather than a power
outage.

## Entity is missing in Home Assistant

1. Confirm the service is running.
2. Confirm it published at least one valid sample.
3. Check sensor logs for ignored measurement names.
4. Check Mosquitto logs.
5. Verify the MQTT integration uses `127.0.0.1:1883`.
6. Restart Home Assistant after regenerating YAML.

Discovery for a measurement is published only after its first valid sample.
Service-health discovery is published on service startup.

Changing a service key or measurement name creates a new identity. Old entities
may remain in Home Assistant's registry and should be reviewed manually.

## Unit or icon is unexpected

The published unit is exactly `measurements[].unit`. LabPulse does not enable
Home Assistant unit conversion through MQTT `device_class`.

The configured `device_class` chooses a default icon inside LabPulse. Set an
explicit `icon: mdi:...` to override it. Apply with `labpulse config` and wait
for discovery to be republished after service recreation.

## Dashboard is missing or stale

Check:

```bash
ls ~/labpulse-live/homeassistant/config/labpulse-dashboard.yaml
labpulse config
labpulse restart homeassistant
labpulse logs --tail 100 homeassistant
```

Do not solve generated-dashboard problems by editing Home Assistant private
`.storage` files or installing custom cards. The supported dashboard is native
YAML.

## Alarm does not trigger

Check the Alarm Setup view:

- alarm mode is not Disabled;
- the correct minimum/maximum threshold is active;
- the value remains dangerous for enough of the observation window;
- required danger percentage is reachable;
- the entity is numeric and available;
- the service does not have a confirmed hub fault.

Alarm state can change while notifications remain suppressed.

## Alarm changes but no notification is sent

Check:

- global mute;
- setup mute;
- individual measurement or power mute;
- Home Assistant Test mode;
- correct test versus normal recipient list;
- SMS worker status and logs;
- subscription state for the number.

See [SMS](SMS.md).

## Sensor Fault takes time

Expected timing can include:

1. `maximum_measurement_age_seconds` before MQTT expiry;
2. `service_health.fault_confirm_seconds` for a whole-service fault;
3. Home Assistant automation scheduling.

Repeated identical numeric samples are not stale. Only missing valid samples
cause expiry.

## SMS does not send

```bash
labpulse logs -f labpulse-sms
sudo systemctl status ModemManager
mmcli -L
```

Look for `dry_run`, `duplicate`, `rate_limited`, `queue full`, no active
recipients, modem failure, or unsubscribed-number messages.

## Recover generated files

First preserve user-owned data:

```text
config.yaml
homeassistant/config/
logs/sms_subscriptions.json
```

Then refresh package-managed and generated files:

```bash
labpulse setup --backup
labpulse up --build
labpulse doctor
```

Do not delete the live directory or Home Assistant state as an ordinary
troubleshooting step.

## Ask for help

Include:

- LabPulse revision or package version;
- Raspberry Pi OS and architecture;
- real or fake mode;
- `labpulse doctor` output;
- `labpulse ps --all`;
- relevant container logs;
- sanitized service configuration;
- exact reproduction steps.

Remove phone numbers, credentials, tokens, and private network details.
