# LabPulse Troubleshooting

Start here when installation, readings, or notifications do not behave as
expected. For a new installation, follow the [Installation guide](INSTALLATION.md)
first. These commands inspect the current deployment:

```bash
labpulse doctor
labpulse ps --all
labpulse logs --tail 100
```

Follow the data from the hardware or external publisher to its worker,
Mosquitto, Home Assistant, and finally SMS. Check the last working step before
changing the next one.

## Find the problem

| Symptom | Start here |
|---|---|
| Command missing or installation fails | [pipx and PATH](#pipx-cannot-find-or-install-labpulse) |
| Docker permissions or Compose errors | [Docker access](#docker-cannot-run) |
| Doctor reports host warnings | [Clock and watchdog](#host-clock-or-watchdog-warning) |
| Generated files are missing or damaged | [Regenerate the deployment](#installation-or-generated-files-are-missing) |
| Configuration is rejected | [Source validation](#configuration-fragment-or-resolved-runtime-fails) |
| Containers restart or readings are missing | [Workers and devices](#containers-exit-or-restart-repeatedly) |
| Dashboard is empty | [MQTT and discovery](#mqtt-or-home-assistant-entities-are-missing) |
| Alarm timing is unexpected | [Alarm decisions](#an-alarm-does-not-trigger-or-recover) |
| SMS does not arrive | [Notification delivery](#no-notification-was-delivered) |
| Update or restoration fails | [Update](#update-failed-or-sms-worker-is-offline) or [restore](#backup-or-restore-fails) |

Use Compose service names with `labpulse logs` and `labpulse restart`:

| Component | Compose service | Container name |
|---|---|---|
| Home Assistant | `homeassistant` | `labpulse-homeassistant` |
| MQTT broker | `mosquitto` | `labpulse-mqtt` |
| SMS worker | `labpulse-sms` | `labpulse-sms` |
| Example pressure worker | `labpulse-pressure-monitor` | `labpulse-pressure-monitor` |

Your worker names depend on the service IDs in the live configuration. For an
alternate installation, put `--live-dir /path/to/live` before each LabPulse
command and adjust the paths below.

## pipx cannot find or install LabPulse

Run `pipx list` and `pipx ensurepath`, then open a new shell. Confirm that
`labpulse version` works. If the package cannot be downloaded, check network
access and the selected version on the [PyPI package page](https://pypi.org/project/labpulse/).
For a first installation with stale package metadata, retry:

```bash
pipx install --pip-args="--no-cache-dir" labpulse
```

Do not use `sudo pip` or `--break-system-packages`. For an existing deployment,
use `labpulse update` for its package and deployment refresh workflow.

## Docker cannot run

```bash
sudo systemctl status docker
sudo docker version
sudo docker compose version
```

LabPulse normally selects `sudo docker` for a non-root Pi user. If you have
deliberately configured Docker-group access, set
`export LABPULSE_DOCKER_COMMAND=docker` consistently. Docker-group membership
grants root-equivalent access; it is not a prerequisite for LabPulse. Direct
Docker examples in this guide use `sudo` and do not read that environment
variable themselves.

If Compose is missing, install the plugin using the
[Docker instructions](https://docs.docker.com/compose/install/linux/).

## Host clock or watchdog warning

Inspect `timedatectl status`. Set the correct timezone and enable NTP as shown
in [Prepare the Pi](INSTALLATION.md#prepare-the-pi). Match the live
`timezone` setting with `labpulse config`. Wait for clock synchronisation before
judging alarm timestamps or external MQTT record age.

For the watchdog, inspect:

```bash
ls -l /dev/watchdog0
systemctl show --property=RuntimeWatchdogUSec --value
```

Doctor warns when the device is absent or systemd's runtime watchdog is
disabled. LabPulse does not configure it. The reference deployment uses a
30-second runtime timeout. On Bookworm, configure systemd's
`RuntimeWatchdogSec` before enabling the firmware watchdog, as explained in
Raspberry Pi's [watchdog instructions](https://www.raspberrypi.com/documentation/computers/config_txt.html#kernel_watchdog_timeout).
Repeat these checks after applying the settings and restarting the host.
Schedule any host reboot around running experiments. A watchdog helps recover
some host failures; it does not prove that sensors or SMS are working.

## Installation or generated files are missing

Setup regenerates managed files while preserving the live source bundle and
Home Assistant private state. Select the installation's intended mode:

```bash
# Real hardware
labpulse setup --backup
```

For simulation, use this instead:

```bash
labpulse setup --backup --fake-hardware
```

Plain setup selects real hardware. If the existing Compose file is readable,
its `/app/config.yaml` mount identifies the generated mode: `config.fake.yaml`
for simulation or `config.resolved.yaml` for real hardware.

Once setup succeeds, recreate the stack so all workers use the regenerated
files and Home Assistant reloads its YAML:

```bash
cd ~/labpulse-live
sudo docker compose up -d --remove-orphans --force-recreate
labpulse doctor
```

This restarts the deployment. `--backup` keeps rolling copies of replaced
package-managed files in `backups/`; it is not a full state archive.

Saving an unchanged `labpulse config` edit is **not** a general repair command.
The editor can exit when the source and resolved runtime are unchanged even
if a dashboard, Compose file, or fake runtime is damaged. Edit source settings
with the guarded editor; use setup for generated-file repair.

## Containers exit or restart repeatedly

Inspect one affected worker:

```bash
labpulse ps --all
labpulse logs --tail 100 labpulse-pressure-monitor
```

Check for missing host devices, invalid driver options, Docker permissions,
MQTT connection failures, or an unintended hardware mode. Compare Compose's
runtime mount with `config.resolved.yaml` or `config.fake.yaml`. Edit the
source bundle, not the generated runtime.

## Assigning serial devices

Use `/dev/serial/by-id/...` instead of `/dev/ttyUSB0` or `/dev/ttyACM0`, whose
numbers can change after reconnecting a board. To identify boards interactively,
first use `labpulse config` to disable serial services for boards you do not
have. Then stop the stack and connect every enabled serial board:

```bash
labpulse down
cd ~/labpulse-live
./setup_usb_devices.py --config config.yaml
labpulse config
labpulse up
```

The helper asks you to unplug and reconnect one board at a time. It updates
`driver.options.port` and keeps `backups/config.yaml.usb-setup-backup`.
The subsequent configuration command applies the new mappings. Close Arduino
serial monitors before restarting workers.

## Serial readings are missing or stale

Check that the configured path exists with `ls -l /dev/serial/by-id/` and read
the worker log. Stop its worker before opening a serial monitor at the
configured baud rate, normally 9600. Each newline-terminated sample needs a
usable field such as `pressure:1.02`; units belong in YAML.

Check measurement names, empty output, `null` channels, firmware resets, and
USB power. A partial sample can publish valid sibling fields. A service with
no valid samples eventually reconnects; individual measurements also expire
in Home Assistant. See the [firmware guide](../firmware/README.md).

## Fake-hardware readings do not appear

Simulation starts with the ordinary stack and needs no separate serial
simulator. Check that Compose mounts `config.fake.yaml` and sensor/output
commands include `--simulate`. If the mode or generated files are wrong, use
the [simulation repair procedure](#installation-or-generated-files-are-missing).
Check freshness rather than requiring every numeric value to vary; simulated
digital inputs can be constant.

## GPIO, DHT11, SHT40 or X1200 is unavailable

For GPIO, check the configured `/dev/gpiochipN`, line offset, polarity, and
whether another process owns the line. Header pins, BCM signals, and chip line
offsets are different identifiers. Output readback proves only the Pi latch,
not equipment movement.

For DHT11, check the Blinka pin name and wiring. Occasional timing errors can
be transient; sustained failures need investigation. For SHT40, confirm I2C is
enabled and the configured `/dev/i2c-<bus>` exists. For X1200, check I2C battery
telemetry and mains GPIO separately: one can fail while the other keeps working.
Use the [driver options](CONFIGURATION.md#built-in-drivers) and verify wiring
against the actual device revision.

## MQTT or Home Assistant entities are missing

```bash
labpulse logs --tail 100 mosquitto
labpulse logs --tail 100 homeassistant
```

Home Assistant's MQTT integration uses `127.0.0.1:1883`. LabPulse containers
use `mosquitto:1883`; `localhost` inside a worker means that worker. Confirm
the integration is connected and discovery is enabled. Inspect the affected
worker's publication logs and restart it if discovery needs republishing.

If only the generated dashboard is damaged, use
[generated-file repair](#installation-or-generated-files-are-missing).
For unexpected units or icons, check the source measurement metadata. Physical
MQTT sensors preserve the configured unit; calculated sensors currently also
expose their configured Home Assistant device class, so check their entity
settings separately.

## Named MQTT or calculated readings are unavailable

For named MQTT input, compare the topic, protocol/version, source timestamp,
case-sensitive source headers, and record-age limit with the actual message.
`recorded_at` is the source record time, not the time an old record was resent.
Use the [Triton guide](TRITON_PUBLISHER.md) for external TLS and publisher checks.

With heartbeat monitoring, a running publisher can remain online while old
measurements expire. Waiting for its first fresh heartbeat shows **Needs
attention** until health is established or the timeout expires. A heartbeat
does not make old readings current.

For calculated measurements, check every physical input and any divisor.
Unavailable/non-numeric inputs and division by zero make the result unavailable.
Calculations cannot depend on other calculated measurements.

## An alarm does not trigger or recover

Check that the measurement has `alarmed: true`, its alarm mode is not
**Disabled**, and the configured threshold matches the intended unit and
condition. The danger percentage is the share of elapsed time in the danger
zone, not a count of samples. In a fully observed 120-second window, 70% means
84 seconds in that state. Home Assistant's
[History Stats integration](https://www.home-assistant.io/integrations/history_stats/#sensor-type)
supplies this evidence and updates on state changes or periodically.

Recovery requires continuously safe data for the configured recovery time.
The high-alarm boundary is `value <= maximum - deadband`; the low-alarm
boundary is `value >= minimum + deadband`. Mutes and Test mode affect delivery,
not threshold calculations. Missing readings and service outages use their
own confirmation rules.

## SMS host setup

On the Pi, install and start the host ModemManager service:

```bash
sudo apt install -y modemmanager
sudo systemctl enable --now ModemManager
sudo mmcli --list-modems
```

Inspect the modem ID reported by that final command with `sudo mmcli -m ID`,
replacing `ID` with its actual number. Check SIM readiness, network registration,
signal, and the modem's SMS support. PIN, antenna, modem, and mobile-network
setup depend on the installed hardware; follow its supplier's instructions.
LabPulse selects the first modem returned by ModemManager and has no YAML
modem-selection field.

Once the host sees the modem, configure normal and test recipients and set
`sms.dry_run: false` with `labpulse config`. Real-mode generation then grants
the SMS worker host device and D-Bus access. Simulation still forces dry-run.
Follow [Testing SMS](USER_GUIDE.md#testing-sms) with Test mode enabled and
confirm receipt on the intended handset.

## Configuration was accepted but containers did not refresh

The guarded editor can fail during generation, Compose/HA checks, or container
recreation. After installing candidate source, it attempts to restore the
previous source bundle and regenerate the old deployment on these failures.
If recreation failed, it also attempts to recreate the old stack.

Read the error to establish whether rollback succeeded, inspect
`labpulse ps --all` and logs, and fix the reported Docker or device problem.
Run `labpulse up` once the intended source and generated files are in place.
The operations are not one atomic transaction, and rollback can itself fail.
The source rollback copy is in `~/labpulse-live/backups/config-source.edit-backup/`.

## Backup or restore fails

Keep archives outside the live directory. Existing archive paths are rejected
unless you deliberately supply `--force`. Check disk space and permissions.
Do not bypass an archive path/type/checksum rejection.

For an external MQTT listener, restoration also requires these separately
saved files under `~/labpulse-live/mosquitto/config/`:

```text
certs/server.crt
certs/server.key
external-passwords
external-acl
```

They are absent from LabPulse state archives, including automatic rollback
archives. Restore them with the [Triton guide's permissions](TRITON_PUBLISHER.md#6-create-both-mqtt-accounts-and-access-rules-pi-once)
before regenerating a listener-enabled configuration. Host networking and
Windows publisher state also need separate reconstruction.

Restore uses the installed LabPulse package to regenerate files; it does not
install the archive's recorded release. If Home Assistant readiness or Doctor
fails after the stack starts, the restored state remains in place. Inspect it
before repeating restoration and preserve any automatic pre-restore archive.

## Configuration fragment or resolved runtime fails

Run `labpulse doctor` first. A `measurements_file` must be a relative `.yaml`
or `.yml` path beneath `config.d`, may not use symlinks or `..`, and must contain
a non-empty measurement mapping without a surrounding `measurements:` key.
LabPulse rejects duplicate keys and reports the fragment path for measurement
schema errors. A service must define exactly one of inline `measurements` and
`measurements_file`.

Also check YAML indentation, duplicate keys, registered driver IDs, setup
references, and option spelling. Unknown fields are rejected. If an older
configuration contains `sms.send_recovery_sms`, remove that retired field;
current recovery requests follow an opening request and current mute settings.

If Doctor reports that `config.resolved.yaml` is missing, stale, or different
from the source bundle, run `labpulse config` and save the guarded edit. Do not
repair the resolved file or Compose mount manually. Real containers mount
`config.resolved.yaml`; fake mode mounts `config.fake.yaml`, which is derived
after resolution.

## Service Offline

Inspect the service status and container logs. Offline means the driver is
disconnected, reconnecting, or in an error state; it does not identify a
physical sensor as the cause. One confirmed service incident suppresses
unavailable-reading incidents beneath that service.

## Service Needs attention

Read the explanation on System Status. The service may be awaiting its first
publisher heartbeat, reporting a component fault, or missing required readings.
Valid sibling readings remain usable. An optional missing MQTT field can still
produce a driver component fault and therefore **Needs attention**, even though
it does not open a required-reading incident.

## No recent data

If the service is Working or Needs attention, inspect the named sensor, wiring,
firmware, source field, and service log. Required readings open one incident
after `missing_confirm_seconds`; readings configured with `required: false`
display **No recent data — optional** without a missing-reading notification.
Their valid numeric values can still trigger threshold alarms.

Calculated readings are unavailable when a dependency is unavailable or a
division would use zero. Their configured `required` setting applies to the
calculated result.

## No notification was delivered

For a missing persistent Home Assistant notification, check that the incident
was confirmed and that Global Mute and its service, reading, setup, or power
mute allow delivery. SMS worker state does not block these notifications.
For a missing SMS, also check Test mode,
recipient configuration, `sms.dry_run`, and the SMS service log. A recovery SMS
requires an opening SMS request and current notification permission.
For modem failures, work through [SMS host setup](#sms-host-setup). Modem
acceptance is not proof of handset delivery.

## Update failed or SMS worker is offline

Read the update error and inspect `labpulse ps --all` and `labpulse logs
labpulse-sms`. Repair the reported package, setup, or Compose problem, then run
`labpulse up` to start the generated stack. There is no retained update mute to
clear. If the SMS worker was disconnected, queued QoS 1 requests from its
persistent MQTT session may be delivered on reconnect, including a failure and
its recovery close together. Check Test mode and recipient settings before
interpreting where those messages were sent.

An update can install the new package before setup or recreation fails; it
does not automatically reinstall the previous release. If you choose to roll
back, pass the recorded previous version to `labpulse update`, and restore
compatible configuration/state separately when needed. Do not assume an old
release accepts the current configuration. An update to the already installed
version exits without repairing files; use [setup](#installation-or-generated-files-are-missing)
for that case.

## Old LabPulse helper history remains stored

Recorder exclusions stop new history for LabPulse's internal helpers after the
generated Home Assistant configuration is applied. Existing rows remain until
normal Recorder purging removes them. To remove them immediately, open Home
Assistant **Developer Tools → Actions**, select `recorder.purge_entities`, switch
to YAML mode, and run this optional one-time action:

```yaml
action: recorder.purge_entities
data:
  entity_globs:
    - binary_sensor.labpulse_*_reading_available
    - binary_sensor.labpulse_*_recovery_zone
    - binary_sensor.labpulse_*_service_offline
    - binary_sensor.labpulse_bulk_*
    - sensor.labpulse_*_observed_danger_percent
    - sensor.labpulse_bulk_*
    - input_boolean.labpulse_*
    - input_button.labpulse_*
    - input_datetime.labpulse_*
    - input_number.labpulse_*
    - input_select.labpulse_*
    - automation.labpulse_*
    - script.labpulse_*
```

Purging removes stored history only. Home Assistant's History **Add target**
picker lists all registered entities, including entities excluded from
Recorder, so this procedure does not remove helpers from that menu.

This deliberately does not match physical or calculated measurement sensors,
or `binary_sensor.labpulse_*_danger_zone`, whose history is required by the
alarm observation window.

## Asking for help

Include the LabPulse version, Pi model, OS, Python/Docker/Compose versions,
hardware mode, enabled driver IDs, Doctor output, and relevant logs. Remove
credentials, phone numbers, tokens, and private network details before sharing.
