# Container Setup

This guide documents the generated Raspberry Pi Docker filesystem and how it is
created from `docker_refactor/`.

For the shortest setup path, read [HAPPY_PATH_SETUP.md](HAPPY_PATH_SETUP.md).

## Generated Runtime Folder

The default live folder is:

```text
~/labpulse-ha/
```

Override it with:

```bash
LABPULSE_CONTAINER_DIR=/path/to/labpulse-ha ./setup_container_fs.sh
```

Folder layout:

```text
~/labpulse-ha/
  compose.yaml
  config.yaml
  generate_compose.sh
  generate_homeassistant_config.sh

  homeassistant/
    config/
      configuration.yaml
      automations.yaml
      scripts.yaml
      scenes.yaml
      labpulse_entity_map.yaml
      packages/
        labpulse_generated.yaml
      .storage/
        lovelace

  homeassistant_backups/
    dashboard-YYYYMMDD-HHMMSS/
      lovelace
    dashboard-latest/
      lovelace

  mosquitto/
    config/
      mosquitto.conf
    data/
    log/

  labpulse-python/
    Dockerfile
    requirements.txt
    labpulse_common/
    labpulse_hardware/
    labpulse_sms/

  labpulse_homeassistant/
    generator package copied from the repo

  logs/
```

## Bootstrap Script

Run from the repository checkout:

```bash
cd ~/LabPulse/docker_refactor
./setup_container_fs.sh
```

Fake USB mode:

```bash
./setup_container_fs.sh -fake_usb
```

Optional backups before replacing generated files:

```bash
./setup_container_fs.sh --backup
```

The script:

1. Creates the live folder skeleton.
2. Writes Mosquitto config.
3. Writes `labpulse-python/Dockerfile`.
4. Writes `labpulse-python/requirements.txt`.
5. Copies `labpulse_common/`, `labpulse_hardware/`, and `labpulse_sms/`.
6. Copies `labpulse_homeassistant/`.
7. Copies generator shell scripts.
8. Creates `config.yaml` from the repo template only if missing.
9. Converts the starter MQTT broker from `localhost` to `mosquitto`.
10. Applies fake serial paths in fake USB mode.
11. Runs Compose generation.
12. Runs Home Assistant generation with `--reset-dashboard`.

Existing live `config.yaml` is preserved.

Existing `homeassistant/config/` is preserved unless you delete it yourself.

## Generated Compose

`generate_compose.sh` writes:

```text
~/labpulse-ha/compose.yaml
```

It creates:

- Home Assistant
- Mosquitto
- SMS worker
- one Python sensor container per enabled service

The Compose file is generated output. Do not hand-edit it for permanent
changes.

## Real USB Mode

Default setup mounts:

```text
/dev:/dev
```

into LabPulse Python containers and sets:

```yaml
privileged: true
```

This allows serial paths such as:

```text
/dev/serial/by-id/usb-Arduino__...
```

to work inside containers.

Real GPIO-backed services such as DHT11 also require real USB mode because the
Python container needs `/dev` access and privileged GPIO access.

## Fake USB Mode

Fake USB setup mounts:

```text
/tmp/labpulse-fake-serial:/tmp/labpulse-fake-serial
/tmp/labpulse-fake-dht11:/tmp/labpulse-fake-dht11
/dev/pts:/dev/pts
```

It uses paths such as:

```text
/tmp/labpulse-fake-serial/pressure
/tmp/labpulse-fake-serial/pump_room
/tmp/labpulse-fake-serial/turbo_pump
```

The simulator is:

```bash
cd ~/LabPulse/docker_refactor
./simulate_arduinos.sh
```

Install `socat` if needed:

```bash
sudo apt install socat -y
```

Fake USB mode also supports file-backed DHT11 input through:

```text
/tmp/labpulse-fake-dht11/room_environment.env
```

## SMS Container Mounts

With:

```yaml
sms:
  backend: "log"
```

the SMS container uses the normal LabPulse Python base service.

With:

```yaml
sms:
  backend: "mmcli"
```

the generated SMS service gets:

```text
/run/dbus:/run/dbus:ro
/dev:/dev
privileged: true
```

so `mmcli` inside the container can talk to host ModemManager.

Regenerate Compose after changing `sms.backend`.

## Python Runtime Dependencies

The generated LabPulse Python image installs:

```text
paho-mqtt
pydantic
pyyaml
pyserial
adafruit-blinka
adafruit-circuitpython-dht
lgpio
```

The Adafruit and `lgpio` packages are needed for the DHT11 GPIO driver on the
Raspberry Pi.

## Home Assistant Container

Generated Home Assistant service:

```yaml
network_mode: host
```

This allows Home Assistant to use:

```text
127.0.0.1:1883
```

for MQTT.

It mounts:

```text
./homeassistant/config:/config
/etc/localtime:/etc/localtime:ro
/run/dbus:/run/dbus:ro
```

## Mosquitto Container

Generated Mosquitto config:

```conf
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest stdout
```

This is suitable for a private test Pi. A deployed lab system should use MQTT
authentication.

## Rebuilding

After changing Python code or container dependencies:

```bash
cd ~/labpulse-ha
docker compose up -d --build
```

Rebuild one service:

```bash
docker compose up -d --build labpulse-pressure-monitor
```

Check final Compose validity:

```bash
docker compose config
```

## Stopping

```bash
cd ~/labpulse-ha
docker compose down
```

This removes containers but keeps mounted config/data folders.

## Common Container Problems

If a Python container cannot import LabPulse modules, rerun setup so
`labpulse_common/`, `labpulse_hardware/`, and `labpulse_sms/` are copied into
`labpulse-python/`.

If generated Home Assistant files cannot be written, the live folder may be
owned by root from an earlier sudo run. Fix ownership:

```bash
sudo chown -R "$(id -u):$(id -g)" ~/labpulse-ha
```

If a service cannot see real USB devices, check the generated Compose file uses
real USB mode and that the configured path exists on the host:

```bash
ls -l /dev/serial/by-id/
```
