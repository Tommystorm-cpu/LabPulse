#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${LABPULSE_CONTAINER_DIR:-$HOME/labpulse-ha}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BACKUP=0
FAKE_USB=0

usage() {
  cat <<'EOF'
Usage: ./setup_container_fs.sh [-fake_usb] [--backup]

Creates the Raspberry Pi Docker Compose folder layout for the LabPulse
container prototype.

Default target:
  ~/labpulse-ha

Override target:
  LABPULSE_CONTAINER_DIR=/path/to/labpulse-ha ./setup_container_fs.sh

Options:
  -fake_usb  Mount socat fake USB serial paths for simulator testing.
  --backup  Create .bak timestamp copies before replacing generated files.

This script preserves the Home Assistant config directory.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    -fake_usb|--fake-usb|--fake_usb)
      FAKE_USB=1
      shift
      ;;
    --backup)
      BACKUP=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

backup_if_needed() {
  local path="$1"

  if [ "$BACKUP" -ne 1 ] || [ ! -e "$path" ]; then
    return
  fi

  local backup="${path}.bak.$(date +%Y%m%d-%H%M%S)"
  cp -a "$path" "$backup"
  echo "Backed up existing file: $backup"
}

write_file() {
  local path="$1"
  backup_if_needed "$path"
  cat > "$path"
}

copy_file() {
  local source="$1"
  local destination="$2"
  backup_if_needed "$destination"
  cp "$source" "$destination"
}

replace_dir() {
  local source="$1"
  local destination="$2"

  if [ -e "$destination" ]; then
    if [ "$BACKUP" -eq 1 ]; then
      local backup="${destination}.bak.$(date +%Y%m%d-%H%M%S)"
      cp -a "$destination" "$backup"
      echo "Backed up existing directory: $backup"
    fi

    rm -rf "$destination"
  fi

  cp -a "$source" "$destination"
}

echo "Setting up LabPulse container filesystem at: $PROJECT_DIR"

mkdir -p "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/homeassistant/config"
mkdir -p "$PROJECT_DIR/mosquitto/config"
mkdir -p "$PROJECT_DIR/mosquitto/data"
mkdir -p "$PROJECT_DIR/mosquitto/log"
mkdir -p "$PROJECT_DIR/labpulse-python"
mkdir -p "$PROJECT_DIR/logs"

if [ "$FAKE_USB" -eq 1 ]; then
  mkdir -p /tmp/labpulse-fake-serial
fi

if [ "$FAKE_USB" -eq 1 ]; then
  PYTHON_DEVICE_MOUNTS='    volumes:
      - ./logs:/app/logs
      - /tmp/labpulse-fake-serial:/tmp/labpulse-fake-serial
      - /dev/pts:/dev/pts'
  USB_MODE_DESCRIPTION="fake USB serial simulator"
else
  PYTHON_DEVICE_MOUNTS='    volumes:
      - ./logs:/app/logs
      - /dev:/dev
    privileged: true'
  USB_MODE_DESCRIPTION="real Arduino USB serial devices"
fi

write_file "$PROJECT_DIR/compose.yaml" <<EOF
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
$PYTHON_DEVICE_MOUNTS
    environment:
      MQTT_BROKER: mosquitto
      MQTT_PORT: 1883
      LABPULSE_LOG_DIR: /app/logs
    restart: unless-stopped
EOF

write_file "$PROJECT_DIR/mosquitto/config/mosquitto.conf" <<'EOF'
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest stdout
EOF

write_file "$PROJECT_DIR/labpulse-python/Dockerfile" <<'EOF'
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fake_sensor.py .
COPY main.py .
COPY labpulse_common ./labpulse_common
COPY config.yaml .

CMD ["python", "main.py", "--service", "pressure_monitor"]
EOF

write_file "$PROJECT_DIR/labpulse-python/requirements.txt" <<'EOF'
paho-mqtt
pydantic
pyyaml
pyserial
EOF

copy_file "$SCRIPT_DIR/fake_sensor.py" "$PROJECT_DIR/labpulse-python/fake_sensor.py"
copy_file "$SCRIPT_DIR/main.py" "$PROJECT_DIR/labpulse-python/main.py"
copy_file "$SCRIPT_DIR/config.yaml" "$PROJECT_DIR/labpulse-python/config.yaml"
replace_dir "$SCRIPT_DIR/labpulse_common" "$PROJECT_DIR/labpulse-python/labpulse_common"

if grep -q 'broker: "localhost"' "$PROJECT_DIR/labpulse-python/config.yaml"; then
  sed -i 's/broker: "localhost"/broker: "mosquitto"/' "$PROJECT_DIR/labpulse-python/config.yaml"
fi

if [ "$FAKE_USB" -eq 1 ]; then
  python3 - "$PROJECT_DIR/labpulse-python/config.yaml" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])

fake_ports = {
    "pump_room": "/tmp/labpulse-fake-serial/pump_room",
    "pressure_monitor": "/tmp/labpulse-fake-serial/pressure",
    "turbo_pump": "/tmp/labpulse-fake-serial/turbo_pump",
}

try:
    import yaml
except ImportError:
    yaml = None

if yaml is not None:
    data = yaml.safe_load(path.read_text())
    for section, serial_port in fake_ports.items():
        if section in data.get("services", {}):
            data["services"][section]["serial_port"] = serial_port
    path.write_text(yaml.safe_dump(data, sort_keys=False))
else:
    text = path.read_text()
    replacements = {
        'serial_port: "/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_03536383236351403122-if00"':
            'serial_port: "/tmp/labpulse-fake-serial/pump_room"',
        'serial_port: "/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_0353638323635131E2C3-if00"':
            'serial_port: "/tmp/labpulse-fake-serial/pressure"',
        'serial_port: "/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_0353638323635140B172-if00"':
            'serial_port: "/tmp/labpulse-fake-serial/turbo_pump"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    path.write_text(text)
PY
fi

cat <<EOF

Done.

Created/updated:
  $PROJECT_DIR/compose.yaml
  $PROJECT_DIR/mosquitto/config/mosquitto.conf
  $PROJECT_DIR/labpulse-python/
  $PROJECT_DIR/logs/

USB mode:
  $USB_MODE_DESCRIPTION

Preserved:
  $PROJECT_DIR/homeassistant/config/

Next commands:
  cd "$PROJECT_DIR"
  docker compose config
  docker compose up -d --build

Important:
  The copied Python config uses mqtt.broker: "mosquitto" for Docker Compose.
EOF
