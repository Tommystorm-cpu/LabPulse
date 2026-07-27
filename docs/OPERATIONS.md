# Operations

The `labpulse` command controls the generated deployment from any working
directory. Commands default to `~/labpulse-live`.

## Command summary

```text
labpulse setup       create or refresh the live installation
labpulse up          start all or selected services
labpulse down        stop and remove containers
labpulse restart     restart all or selected services
labpulse ps          show container status
labpulse logs        show container logs
labpulse config      safely edit and apply configuration
labpulse doctor      run read-only diagnostics
labpulse open        open Home Assistant
labpulse firmware    show firmware download information
labpulse help        show general or command-specific help
```

Use `labpulse help COMMAND` for detailed syntax.

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

Stop and remove containers without deleting bind-mounted configuration, logs,
Mosquitto data, or Home Assistant state:

```bash
labpulse down
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

This guarded workflow currently applies real-hardware configuration. In a
fake-USB installation, edit `~/labpulse-live/config.yaml` directly and run
`labpulse setup --fake-usb` so the derived runtime config and Compose mounts
remain simulated.

The command:

1. opens a temporary copy beside the live config;
2. uses `$VISUAL`, then `$EDITOR`, then `nano`;
3. validates the edited YAML and typed configuration;
4. exercises Compose and Home Assistant generation;
5. keeps one rolling `config.yaml.edit-backup`;
6. replaces the live config only after validation;
7. runs `docker compose config`;
8. runs Home Assistant's configuration check;
9. recreates the stack and shows its status.

If validation or Home Assistant checking fails, the command restores the prior
config and deterministic generated output.

The command uses `sudo docker` in its current Linux workflow. Set
`LABPULSE_DOCKER_COMMAND` for ordinary lifecycle commands when Docker is
configured differently.

## Run diagnostics

```bash
labpulse doctor
```

Doctor is read-only. It checks:

- the live directory;
- source and active runtime configuration;
- fake-mode runtime config detection;
- generated Home Assistant files;
- declared host paths for enabled drivers;
- Docker Compose availability and syntax;
- defined versus running Compose services;
- local MQTT reachability on `127.0.0.1:1883`;
- local Home Assistant reachability on `127.0.0.1:8123`.

Results are labelled `PASS`, `WARN`, `FAIL`, or `SKIP`. Any required failure
returns shell status 1.

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
