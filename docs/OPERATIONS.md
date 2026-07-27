# Operations

The `labpulse` command controls the generated deployment from any working
directory. Commands default to `~/labpulse-live`.

## Command summary

```text
labpulse setup       create or refresh the live installation
labpulse up          start all or selected services
labpulse down        stop and remove all or selected containers
labpulse restart     restart or rebuild all or selected services
labpulse ps          show container status
labpulse logs        show container logs
labpulse config      safely edit and apply configuration
labpulse backup      create a consistent state archive
labpulse restore     reconstruct an installation from a state archive
labpulse doctor      run read-only diagnostics
labpulse open        open Home Assistant
labpulse firmware    show firmware download information
labpulse help        show general or command-specific help
```

Use `labpulse help COMMAND` for detailed syntax.

## Back up and reconstruct

Create a complete LabPulse state archive somewhere outside the live directory:

```bash
mkdir -p ~/labpulse-backups
labpulse backup ~/labpulse-backups/labpulse-$(date +%Y%m%d).tar.gz
```

Backup briefly stops the currently running Compose services, snapshots the
source configuration, complete Home Assistant configuration and private state,
retained Mosquitto data, and SMS subscription/request state, then restarts
exactly those services. The archive contains a manifest and SHA-256 checksum
for every file. Existing output is never replaced unless `--force` is given.

The archive is created with owner-only permissions on Linux, but it is not
encrypted. It contains Home Assistant credentials and tokens, alarm state,
phone numbers, and potentially sensitive history. Store it outside
`~/labpulse-live` on encrypted or access-controlled storage.

Restore onto an existing or newly scaffolded host:

```bash
labpulse restore ~/labpulse-backups/labpulse-20260727.tar.gz
```

Type `RESTORE` at the prompt, or use `--yes` in an already controlled,
non-interactive recovery procedure. Restore:

1. validates all archive paths and checksums before changing state;
2. scaffolds a missing live installation in the archive's recorded real or
   fake-hardware mode;
3. stops any running services;
4. creates a timestamped pre-restore rollback archive when state already
   exists;
5. replaces only the state owned by the backup;
6. regenerates managed deployment files;
7. rebuilds and starts the complete stack;
8. waits for Home Assistant and runs `labpulse doctor`.

If regeneration or startup fails after replacing an existing installation,
LabPulse attempts to restore the automatic rollback snapshot and restarts the
previously running services.

A state archive does not reproduce host-level configuration. On a replacement
Pi, first install Raspberry Pi OS, Docker with Compose, pipx, and the same
compatible LabPulse package. After restore, verify the timezone and NTP,
systemd watchdog, Docker-group policy, modem provisioning, USB identities,
GPIO/I2C wiring, and other physical hardware.

## Start and stop

Start the complete stack in the background:

```bash
labpulse up
```

Rebuild local LabPulse images after setup or source changes:

```bash
labpulse up --build
```

Start selected Compose services:

```bash
labpulse up mosquitto homeassistant
```

Restart everything or one service:

```bash
labpulse restart
labpulse restart homeassistant
labpulse restart labpulse-pressure-monitor
```

Rebuild images and force recreation after source or image changes:

```bash
labpulse restart --build
labpulse restart --build labpulse-room-environment
```

A targeted build restart recreates only the named services and does not restart
their dependencies.

Stop and remove all containers, or only selected services, without deleting
bind-mounted configuration, logs, Mosquitto data, or Home Assistant state:

```bash
labpulse down
labpulse down labpulse-room-environment
labpulse down labpulse-pressure-monitor labpulse-pump-room
```

## Inspect containers and logs

```bash
labpulse ps
labpulse ps --all
labpulse logs
labpulse logs --tail 100
labpulse logs -f
labpulse logs -f homeassistant
labpulse logs -f labpulse-sms
```

Fixed Compose services are `homeassistant`, `mosquitto`, and `labpulse-sms`.
Each enabled hardware service adds `labpulse-<service-slug>`.

Python services also write persistent logs under:

```text
~/labpulse-live/logs/
```

LabPulse containers inherit the host's `/etc/localtime`. Python log timestamps
also include their numeric UTC offset so daylight-saving changes are explicit.

## Change configuration safely

```bash
labpulse config
```

This guarded workflow preserves the active runtime mode. In a fake-USB
installation, it detects the active Compose mount, regenerates
`config.fake.yaml`, and keeps the Compose deployment simulated. In either mode,
the user-owned source remains `~/labpulse-live/config.yaml`.

The command:

1. opens a temporary copy beside the live config;
2. uses `$VISUAL`, then `$EDITOR`, then `nano`;
3. validates the edited YAML and typed configuration;
4. derives and validates `config.fake.yaml` when fake mode is active;
5. exercises Compose and Home Assistant generation for the active mode;
6. keeps one rolling source backup, plus a fake-runtime backup when applicable;
7. replaces the live config only after validation;
8. runs `docker compose config`;
9. runs Home Assistant's configuration check;
10. recreates the stack and shows its status.

If validation or Home Assistant checking fails, the command restores the prior
config and deterministic generated output.

The guarded configuration workflow uses the same Docker command selection as
every other `labpulse` lifecycle command. Set
`LABPULSE_DOCKER_COMMAND=docker` for Docker-group access; otherwise non-root
Linux installations default to `sudo docker`.

## Run diagnostics

```bash
labpulse doctor
```

Doctor is read-only. It checks:

- the live directory;
- source and active runtime configuration;
- explicit real-hardware or fake-USB runtime-mode detection;
- host timezone and NTP synchronization;
- hardware-watchdog availability and systemd runtime timeout;
- generated Home Assistant files;
- declared host paths for enabled drivers;
- Docker daemon access, Engine and Compose versions, and Compose syntax;
- defined versus running Compose services;
- local MQTT reachability on `127.0.0.1:1883`;
- local Home Assistant reachability on `127.0.0.1:8123`.

Results are labelled `PASS`, `WARN`, `FAIL`, or `SKIP`. Any required failure
returns shell status 1. Failures include the next corrective command or the
hardware path, cable, permission, or log check an operator should perform.

Use a longer endpoint timeout on a slow Pi:

```bash
labpulse doctor --timeout 3
```

## Open Home Assistant

```bash
labpulse open
```

This opens `http://localhost:8123` in the Pi's default browser. From another
computer, open `http://<pi-address>:8123` manually.

## Simulated sensors

Start, inspect, and stop the background simulator:

```bash
cd ~/labpulse-live
./simulate_serial.py start
./simulate_serial.py status
./simulate_serial.py stop
```

Set measurement scenarios:

```bash
./simulate_serial.py set pump_room.flow1 danger-low
./simulate_serial.py set room_environment.temperature danger-high
./simulate_serial.py clear pump_room.flow1
./simulate_serial.py reset
```

Ordinary states are `normal`, `recover`, `danger-low`, `danger-high`, and
`stale`. The UPS power states are `mains`, `battery`, and `stale`.

Simulate device removal:

```bash
./simulate_serial.py disconnect pump_room
./simulate_serial.py connect pump_room
```

Start with scenarios already active:

```bash
./simulate_serial.py start \
  --scenario pump_room.flow1=danger-low \
  --scenario room_environment.temperature=danger-high
```

A `stale` measurement stops producing that value while the device and its peer
measurements can remain active. Wait for the configured measurement-age and
service-fault confirmation periods before expecting Sensor Fault.

## Real-Pi GPIO and I2C fault injection

Setup installs two test-only scripts that simulate unavailable hardware at the
container boundary. The X1200 script masks selected device endpoints with
`/dev/null`. The DHT11 script supplies a temporary invalid pin configuration so
the real PulseIn object is never constructed and the live GPIO line is not
disturbed. They recreate only the selected service and do not edit
`compose.yaml`, change host device permissions, unload kernel drivers, claim
GPIO lines, or require live rewiring.

Test the X1200 fuel-gauge interface:

```bash
cd ~/labpulse-live
./test_x1200_faults.sh block-i2c
./test_x1200_faults.sh status
./test_x1200_faults.sh restore
```

Test the X1200 mains-detection GPIO while leaving I2C telemetry available:

```bash
./test_x1200_faults.sh block-gpio
./test_x1200_faults.sh restore
```

Use `block-all` to remove both interfaces. If the service has a non-default
name, pass it before the command:

```bash
./test_x1200_faults.sh --service facility_ups block-gpio
```

Test DHT11 GPIO unavailability:

```bash
./test_dht11_fault.sh block
./test_dht11_fault.sh status
./test_dht11_fault.sh restore
```

Restore stops the faulted DHT11 worker for five seconds before recreating it,
allowing the GPIO/PulseIn resources to settle.

Use `--service NAME` for a non-default DHT11 service. The scripts reject fake
USB deployments and mismatched driver types.

Always finish with `restore`, including after an interrupted test. Do not run
`labpulse config`, `labpulse setup`, or `labpulse up` while a fault is active,
because those commands may recreate the service outside the test override.
Docker Compose 2.24.4 or newer is required for the X1200 device-list override.

## Host hardware watchdog

For the Raspberry Pi 5 reference deployment, use the built-in hardware
watchdog before adding an external watchdog. Add this setting to
`/boot/firmware/config.txt`:

```ini
kernel_watchdog_timeout=30
```

Create `/etc/systemd/system.conf.d/watchdog.conf`:

```bash
sudo mkdir -p /etc/systemd/system.conf.d
printf '[Manager]\nRuntimeWatchdogSec=30s\nRebootWatchdogSec=5min\n' | \
  sudo tee /etc/systemd/system.conf.d/watchdog.conf >/dev/null
sudo reboot
```

After reboot, verify the effective configuration:

```bash
systemctl show \
  --property=RuntimeWatchdogUSec \
  --property=RebootWatchdogUSec
sudo wdctl /dev/watchdog0
journalctl -b | grep -i watchdog
```

The watchdog resets the Pi if systemd can no longer service the hardware timer.
Docker restart policies and LabPulse alarms remain responsible for individual
service failures. Do not deliberately hang or panic a production Pi merely to
test the watchdog; reserve a destructive watchdog-reset test for a maintenance
window with current backups.

An external watchdog is not part of the current reference deployment. If one
is later required, it must independently monitor a heartbeat and control the
X1200 output or Pi power path with boot grace and reset-loop protection.
Cycling only the mains input is insufficient while the X1200 battery is able to
keep the Pi powered.

## Direct generation helpers

Setup copies low-level wrappers into `~/labpulse-live`:

```bash
./generate_compose.sh
./generate_homeassistant_config.sh
```

Normal operators should prefer `labpulse config`, which validates, generates,
checks, and applies changes as one guarded workflow. Direct generator use is
primarily for development or recovery.

Generated files include:

```text
compose.yaml
homeassistant/config/configuration.yaml
homeassistant/config/packages/labpulse_generated.yaml
homeassistant/config/labpulse-dashboard.yaml
```

Do not hand-edit generated files as permanent changes.

## Firmware guidance

```bash
labpulse firmware
```

The current command prints repository and ZIP links. It does not download or
flash firmware. See [Firmware](../firmware/README.md).

## Standalone aliases

Pipx also installs:

```text
labpulse-up
labpulse-down
labpulse-restart
labpulse-ps
labpulse-logs
labpulse-config
labpulse-open
```

The unified `labpulse` command is the documented interface. The older
`labpulse-setup` alias remains temporarily available, but new instructions use
`labpulse setup`.
