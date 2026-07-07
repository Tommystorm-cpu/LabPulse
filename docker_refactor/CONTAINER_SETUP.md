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

  labpulse-python/
    Dockerfile
    requirements.txt
    config.yaml
    fake_sensor.py
    labpulse_common/
```

`homeassistant/config/` is mounted into the Home Assistant container as `/config`.

`mosquitto/config/`, `mosquitto/data/`, and `mosquitto/log/` are mounted into the Mosquitto container.

`labpulse-python/` is built into the Python container image.

## Create The Layout With The Script

From a clone of this repository on the Raspberry Pi:

```bash
cd ~/LabPulse/docker_refactor
chmod +x setup_container_fs.sh
./setup_container_fs.sh
```

By default, the script creates or updates:

```text
~/labpulse-ha/
```

It preserves:

```text
~/labpulse-ha/homeassistant/config/
```

so existing Home Assistant setup, users, dashboards, and entity data are not removed.

To use a different target folder:

```bash
LABPULSE_CONTAINER_DIR=/path/to/labpulse-ha ./setup_container_fs.sh
```

To replace generated files without creating `.bak` copies:

```bash
./setup_container_fs.sh --force
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
    environment:
      MQTT_BROKER: mosquitto
      MQTT_PORT: 1883
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
COPY labpulse_common ./labpulse_common
COPY config.yaml .

CMD ["python", "fake_sensor.py"]
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
