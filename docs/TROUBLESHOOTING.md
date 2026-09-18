# LabPulse Troubleshooting

Start here when installation, readings, or notifications do not behave as
expected. For a new installation, follow the [Installation guide](INSTALLATION.md)
first. Run the commands below **in the Pi's terminal**, locally or over SSH,
using the same account as the installation. They inspect the deployment without
changing its settings:

```bash
labpulse doctor
labpulse ps --all
labpulse logs --tail 100
```

Keep the first error message before restarting anything. Later errors may be
consequences of it. Change one thing at a time, repeat the failing check, then
confirm that fresh readings return in **System Status**.

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
| Fresh setup shows an old Home Assistant login | [Existing Home Assistant state](#fresh-setup-shows-an-old-home-assistant-login) |
| Alarm timing is unexpected | [Alarm decisions](#an-alarm-does-not-trigger-or-recover) |
| SMS does not arrive | [Notification delivery](#no-notification-was-delivered) |
| Update or restoration fails | [Update](#update-failed-or-sms-worker-is-offline) or [restore](#backup-or-restore-fails) |

### Read the first results

`labpulse doctor` labels each check:

| Result | Meaning | Next step |
|---|---|---|
| `PASS` | This particular check succeeded | Continue; it doesn't prove the rest of the system is healthy |
| `WARN` | Something needs review, such as clock synchronisation | Read the explanation and resolve it if it applies to this installation |
| `FAIL` | A required check failed | Follow its suggested action before relying on the installation |
| `SKIP` | A check wasn't performed, often because an earlier check couldn't supply what it needed | Fix the earlier problem, then run Doctor again |

For example, these are representative lines in Doctor's output, not a captured
report from your Pi:

```text
[PASS] Installation: live directory exists
[FAIL] Resolved configuration freshness: config.resolved.yaml is stale; run 'labpulse config'
```

The first line only confirms that the directory exists. The second means the
generated configuration doesn't match your source settings. Apply the source
through `labpulse config`, then repeat Doctor; don't edit the generated file.

In `labpulse ps --all`, look at the service and state columns. A container that
is exited or keeps restarting needs its log checked. A running container can
still have a disconnected sensor, so also read its **System Status** card.
Logs contain progress as well as errors; find the most recent failure for the
affected service and check whether a later entry reports recovery.

### Choose the service to inspect

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

`labpulse logs --follow SERVICE` keeps the log open as new entries arrive.
Replace `SERVICE` with a name from the table or your deployment. Press
**Ctrl+C** to leave the log; that doesn't stop the service.

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

Setup rebuilds the generated files while preserving your `config.yaml`,
measurement files, and saved Home Assistant state. Select the installation's
intended mode:

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
source settings through `labpulse config`, not the generated runtime file.

## Assigning serial devices

Use `/dev/serial/by-id/...` instead of `/dev/ttyUSB0` or `/dev/ttyACM0`, whose
numbers can change after reconnecting a board. To identify boards interactively,
first use `labpulse config` to disable serial services for boards you do not
have. Then stop the stack and connect every enabled serial board:

```bash
labpulse down
labpulse usb
labpulse config
labpulse up
```

`labpulse usb` works from any directory and uses `~/labpulse-live/config.yaml`
by default. It asks you to unplug and reconnect one board at a time, previews
the detected assignments, and asks before saving. It updates only the assigned
`driver.options.port` lines and keeps `backups/config.yaml.usb-setup-backup`.
The subsequent configuration command applies the new mappings. Close Arduino
serial monitors before restarting workers.

Use `labpulse usb --dry-run` to identify boards without saving. For an installation
elsewhere, use `labpulse --live-dir /srv/labpulse usb`. `--yes` skips the final
save confirmation; you still need to follow the unplug/replug prompts.

## Serial readings are missing or stale

Check the USB connection first, then the sample, then the dashboard:

| What you find | What to check next |
|---|---|
| No board entry under `/dev/serial/by-id/` | USB data cable, board power, hub, and whether Linux recognises the device |
| Board exists, but the configured path differs | Correct `driver.options.port` through `labpulse config` |
| Port exists, but the worker can't open it | Its log, device access, and whether another program has the port open |
| Serial output is blank or unreadable | Firmware, board resets, and matching baud rate, normally 9600 |
| Sample contains `pressure: null` | Sensor wiring and the firmware's validity/calibration checks |
| Sample contains `pressure:1.02`, but that reading is missing | Matching measurement key in the live configuration and then [MQTT discovery](#mqtt-or-home-assistant-entities-are-missing) |

To inspect raw serial output, stop the worker that owns the board before
opening a serial monitor. Each sample must end with a newline; put units in
the configuration, not in the serial value. The [first-sensor walkthrough](FIRST_SENSOR.md#1-check-what-the-arduino-sends)
shows an example.

Close the monitor and restart the worker when finished. Confirm that the
reading's timestamp advances in **System Status**. Its number needn't change
if the physical quantity is steady. Valid fields can continue updating even
when another field in the same sample is `null`.

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

## Fresh setup shows an old Home Assistant login

Reinstalling the LabPulse package does not erase Home Assistant accounts or
history. `labpulse setup` also preserves existing state. Docker images contain
the application; the Home Assistant account data lives in its mounted config
directory.

First open `http://<test-pi-ip>:8123/` in a private browser window, using the
test Pi's actual IP from `hostname -I`. Then inspect its containers and the
directory mounted as Home Assistant's `/config`:

```bash
whoami
sudo docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
sudo docker compose ls -a
sudo docker inspect labpulse-homeassistant --format '{{range .Mounts}}{{if eq .Destination "/config"}}{{.Source}}{{end}}{{end}}'
```

Compare that path with the account you are using. For example, deleting
`/home/alex/labpulse-live` does not reset a deployment under
`/home/sam/labpulse-live`. Docker's project listing can retain a Compose path
even after that file has been deleted; the containers may still be running.

For a disposable test installation, use the
[uninstall procedure](USER_GUIDE.md#removing-an-installation) with its confirmed
live directory before creating a new simulated installation. If the Compose
file is missing, identify and remove that deployment's containers before
removing its remaining data. Do not delete unrelated Docker resources.

If the login page remains after those containers are removed, identify the
remaining listener with `sudo ss -ltnpe 'sport = :8123'`. A listener means
something still owns that port; identify it before starting the new deployment.
IPv4 and IPv6 entries alone do not establish that two instances exist.

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
recipient configuration, `sms.dry_run`, and the SMS service log. Use this order:

1. Confirm the problem reached a confirmed alarm or outage state. A crossed
   threshold alone may still be waiting for its observation window.
2. Check whether notification mutes allow a message. If the Home Assistant
   notification is also absent, start with those controls.
3. Check the recipient list selected by Test mode. Test mode can send real
   SMS; dry-run cannot. Simulation always uses dry-run.
4. Inspect `labpulse logs --tail 100 labpulse-sms`. A dry-run entry means the
   software processed the request without contacting the modem. A send error
   needs the modem and network checks below.

A recovery SMS requires an opening SMS request and current notification permission.
For modem failures, work through [SMS host setup](#sms-host-setup). Modem
acceptance is not proof of handset delivery. After fixing the cause, use
[Testing SMS](USER_GUIDE.md#testing-sms) and check the intended handset;
don't assume an earlier muted notification will be sent automatically.

## Update failed or SMS worker is offline

Read the update error and inspect `labpulse ps --all` and `labpulse logs
labpulse-sms`. Repair the reported package, setup, or Compose problem, then run
`labpulse up` to start the generated stack. There is no retained update mute to
clear. If the SMS worker was disconnected, the broker may have held SMS
requests for it to process on reconnect, including a failure and
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
