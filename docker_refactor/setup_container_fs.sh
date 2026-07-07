#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${LABPULSE_CONTAINER_DIR:-$HOME/labpulse-ha}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BACKUP=0

usage() {
  cat <<'EOF'
Usage: ./setup_container_fs.sh [--backup]

Creates the Raspberry Pi Docker Compose folder layout for the LabPulse
container prototype.

Default target:
  ~/labpulse-ha

Override target:
  LABPULSE_CONTAINER_DIR=/path/to/labpulse-ha ./setup_container_fs.sh

Options:
  --backup  Create .bak timestamp copies before replacing generated files.

This script preserves the Home Assistant config directory.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
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

write_file "$PROJECT_DIR/compose.yaml" <<'EOF'
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
COPY labpulse_common ./labpulse_common
COPY config.yaml .

CMD ["python", "fake_sensor.py"]
EOF

write_file "$PROJECT_DIR/labpulse-python/requirements.txt" <<'EOF'
paho-mqtt
pydantic
pyyaml
EOF

copy_file "$SCRIPT_DIR/fake_sensor.py" "$PROJECT_DIR/labpulse-python/fake_sensor.py"
copy_file "$SCRIPT_DIR/config.yaml" "$PROJECT_DIR/labpulse-python/config.yaml"
replace_dir "$SCRIPT_DIR/labpulse_common" "$PROJECT_DIR/labpulse-python/labpulse_common"

if grep -q 'broker: "localhost"' "$PROJECT_DIR/labpulse-python/config.yaml"; then
  sed -i 's/broker: "localhost"/broker: "mosquitto"/' "$PROJECT_DIR/labpulse-python/config.yaml"
fi

cat <<EOF

Done.

Created/updated:
  $PROJECT_DIR/compose.yaml
  $PROJECT_DIR/mosquitto/config/mosquitto.conf
  $PROJECT_DIR/labpulse-python/

Preserved:
  $PROJECT_DIR/homeassistant/config/

Next commands:
  cd "$PROJECT_DIR"
  docker compose config
  docker compose up -d --build

Important:
  The copied Python config uses mqtt.broker: "mosquitto" for Docker Compose.
EOF
