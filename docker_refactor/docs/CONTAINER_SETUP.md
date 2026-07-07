# LabPulse Container Setup

This guide documents the Docker-based LabPulse test setup used on the Raspberry Pi.

The target architecture is:

```text
Raspberry Pi
  Docker Compose project
    homeassistant container
    mosquitto container
    labpulse-python container
```

Each container has one job:

- `homeassistant` runs the Home Assistant web interface.
- `mosquitto` runs the MQTT broker.
- `labpulse-python` runs the LabPulse Python scripts that publish sensor readings.

## Folder Layout

The Raspberry Pi working folder is:

```text
~/labpulse-ha/
  compose.yaml

  homeassistant/
    config/

  mosquitto/
    config/
      mosquitto.conf
    data/
    log/

  logs/

  labpulse-python/
    Dockerfile
    requirements.txt
    config.yaml
    fake_sensor.py
    main.py
    labpulse_common/
```

`homeassistant/config/` is mounted into the Home Assistant container as `/config`.

`mosquitto/config/`, `mosquitto/data/`, and `mosquitto/log/` are mounted into the Mosquitto container.

`logs/` stores LabPulse Python log files written by the Python container.

`labpulse-python/` is built into the Python container image.

## Create The Layout With The Script

From a clone of this repository on the Raspberry Pi:

```bash
cd ~/LabPulse/docker_refactor
chmod +x setup_container_fs.sh
./setup_container_fs.sh
```

By default this creates a real-Arduino setup. The Python container is given access to:

```text
/dev
```

Use this for the final hardware setup with real USB Arduinos. This lets Python use stable config paths such as:

```text
/dev/serial/by-id/usb-Arduino__...
```

when the Arduinos are plugged in.

For fake USB serial testing with `simulate_arduinos.sh`, run:

```bash
./setup_container_fs.sh -fake_usb
```

That version mounts:

```text
/tmp/labpulse-fake-serial
/dev/pts
```

into the Python container.

It also rewrites the copied `labpulse-python/config.yaml` serial ports to:

```yaml
pressure_monitor:
  serial_port: "/tmp/labpulse-fake-serial/pressure"

pump_room:
  serial_port: "/tmp/labpulse-fake-serial/pump_room"

turbo_pump:
  serial_port: "/tmp/labpulse-fake-serial/turbo_pump"
```

By default, the script creates or updates:

```text
~/labpulse-ha/
```

It overwrites the generated Compose, Mosquitto, and Python container files by default.

It preserves:

```text
~/labpulse-ha/homeassistant/config/
```

so existing Home Assistant setup, users, dashboards, and entity data are not removed.

To use a different target folder:

```bash
LABPULSE_CONTAINER_DIR=/path/to/labpulse-ha ./setup_container_fs.sh
```

To create `.bak` copies before replacing generated files:

```bash
./setup_container_fs.sh --backup
```

The script also copies `docker_refactor/config.yaml` into the Python container folder and changes:

```yaml
broker: "localhost"
```

to:

```yaml
broker: "mosquitto"
```

for the container setup.

## Docker Compose File

`~/labpulse-ha/compose.yaml`:

```yaml
services:
  homeassistant:
    container_name: labpulse-homeassistant
    image: ghcr.io/home-assistant/home-assistant:stable
    volumes:
      - ./homeassistant/config:/config
      - /etc/localtime:/etc/localtime:ro
      - /run/dbus:/run/dbus:ro
    restart: unless-stopped
    privileged: true
    network_mode: host
    environment:
      TZ: Europe/London

  mosquitto:
    container_name: labpulse-mqtt
    image: eclipse-mosquitto:2
    ports:
      - "1883:1883"
    volumes:
      - ./mosquitto/config:/mosquitto/config
      - ./mosquitto/data:/mosquitto/data
      - ./mosquitto/log:/mosquitto/log
    restart: unless-stopped

  labpulse-python:
    container_name: labpulse-python
    build: ./labpulse-python
    depends_on:
      - mosquitto
    volumes:
      - ./logs:/app/logs
      - /dev:/dev
    privileged: true
    environment:
      MQTT_BROKER: mosquitto
      MQTT_PORT: 1883
      LABPULSE_LOG_DIR: /app/logs
    restart: unless-stopped
```

## Mosquitto Config

`~/labpulse-ha/mosquitto/config/mosquitto.conf`:

```conf
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest stdout
```

This unauthenticated config is suitable for a private test Pi. A deployed lab system should use MQTT usernames/passwords.

## Python Container

`~/labpulse-ha/labpulse-python/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fake_sensor.py .
COPY main.py .
COPY labpulse_common ./labpulse_common
COPY config.yaml .

CMD ["python", "main.py", "--service", "pressure_monitor"]
```

`~/labpulse-ha/labpulse-python/requirements.txt` should include:

```text
paho-mqtt
pydantic
pyyaml
```

Add any extra packages needed by the real LabPulse scripts.

## Important MQTT Broker Name

When LabPulse Python scripts run directly on the Raspberry Pi, this works:

```yaml
mqtt:
  broker: "localhost"
  port: 1883
```

Inside the `labpulse-python` container, `localhost` means the Python container itself. It does not mean the Mosquitto container.

For the container setup, `config.yaml` must use the Docker Compose service name:

```yaml
mqtt:
  broker: "mosquitto"
  port: 1883
```

This is the most important config change.

```text
labpulse-python container -> mosquitto:1883
```

Home Assistant is different because this setup uses `network_mode: host`. In the Home Assistant MQTT integration, the broker can be:

```text
127.0.0.1
```

with port:

```text
1883
```

So the two MQTT addresses are:

```text
Python config.yaml:         mosquitto
Home Assistant integration: 127.0.0.1
```

## Start The System

From the Pi:

```bash
cd ~/labpulse-ha
docker compose up -d --build
```

Check the containers:

```bash
docker compose ps
```

Expected containers:

```text
labpulse-homeassistant
labpulse-mqtt
labpulse-python
```

Open Home Assistant from another computer on the same network:

```text
http://PI_IP_ADDRESS:8123
```

Example:

```text
http://10.32.100.195:8123
```

## Rebuild One Container

After changing only the Python scripts or Python Dockerfile:

```bash
docker compose up -d --build labpulse-python
```

Watch the Python logs:

```bash
docker compose logs -f labpulse-python
```

The same Python logs are also written to files on the Pi:

```text
~/labpulse-ha/logs/
```

For example:

```text
~/labpulse-ha/logs/fake_sensor.log
~/labpulse-ha/logs/pump_room.log
```

Watch Mosquitto logs:

```bash
docker compose logs -f mosquitto
```

Watch Home Assistant logs:

```bash
docker compose logs -f homeassistant
```

## Test MQTT Manually

Subscribe to all MQTT messages:

```bash
docker run --rm -it --network host eclipse-mosquitto:2 mosquitto_sub -h 127.0.0.1 -p 1883 -t '#' -v
```

Publish a test message:

```bash
docker run --rm --network host eclipse-mosquitto:2 mosquitto_pub -h 127.0.0.1 -p 1883 -t 'labpulse/test/hello' -m 'hello'
```

The subscriber should print:

```text
labpulse/test/hello hello
```

## Simulate Arduino Serial Devices

For testing scripts that normally read from USB Arduinos, use:

```bash
cd ~/LabPulse/docker_refactor
chmod +x simulate_arduinos.sh
./simulate_arduinos.sh
```

The script uses `socat` to create fake serial devices and continuously writes Arduino-like readings to them.

Install `socat` on the Pi if needed:

```bash
sudo apt install socat -y
```

Default fake serial paths:

```text
/tmp/labpulse-fake-serial/pressure
/tmp/labpulse-fake-serial/pump_room
/tmp/labpulse-fake-serial/turbo_pump
```

When `setup_container_fs.sh -fake_usb` is used, the generated Compose file mounts `/tmp/labpulse-fake-serial` and `/dev/pts` into the `labpulse-python` container so these fake serial links can be read from inside Docker.

In fake USB mode, the setup script creates the `/tmp/labpulse-fake-serial` directory if it does not already exist. The actual fake device links, such as `/tmp/labpulse-fake-serial/pressure`, only exist while `simulate_arduinos.sh` is running.

For fake serial testing, set these `config.yaml` values:

```yaml
pressure_monitor:
  serial_port: "/tmp/labpulse-fake-serial/pressure"

pump_room:
  serial_port: "/tmp/labpulse-fake-serial/pump_room"

turbo_pump:
  serial_port: "/tmp/labpulse-fake-serial/turbo_pump"
```

The simulator writes serial lines matching the Arduino sketches in the repository.

See [ARDUINO_SERIAL_FORMATS.md](ARDUINO_SERIAL_FORMATS.md) for the exact line formats and notes on which lines the current Python parsers handle.

Stop the simulator with:

```text
Ctrl+C
```

Stopping and restarting the simulator also simulates serial devices disappearing and returning.

## Stop The System

```bash
cd ~/labpulse-ha
docker compose down
```

This stops and removes the containers, but keeps the mounted config/data folders.

## Useful Troubleshooting

Check what is using port `8123`:

```bash
sudo ss -ltnp | grep 8123
```

Check what is using port `1883`:

```bash
sudo ss -ltnp | grep 1883
```

If `labpulse-python` repeatedly restarts, read its logs:

```bash
docker compose logs -f labpulse-python
```

or check the persistent Python log files:

```bash
ls -la ~/labpulse-ha/logs
tail -f ~/labpulse-ha/logs/fake_sensor.log
```

Common causes:

- `config.yaml` still says `broker: "localhost"` instead of `broker: "mosquitto"`.
- `labpulse_common/` was not copied into the Python container image.
- `requirements.txt` is missing a Python dependency.
- The Python script has an import path that worked on the host but not inside `/app` in the container.

If Home Assistant cannot connect to MQTT, check that its MQTT integration uses:

```text
Broker: 127.0.0.1
Port: 1883
```

and check that Mosquitto is running:

```bash
docker compose ps
docker compose logs --tail 50 mosquitto
```
