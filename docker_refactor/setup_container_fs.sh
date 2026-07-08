#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${LABPULSE_CONTAINER_DIR:-$HOME/labpulse-ha}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIVE_CONFIG="$PROJECT_DIR/config.yaml"
TEMPLATE_CONFIG="$SCRIPT_DIR/config.yaml"

BACKUP=0
FAKE_USB=0

usage() {
  cat <<'EOF'
Usage: ./setup_container_fs.sh [options]

One-time bootstrap for the Raspberry Pi LabPulse folder.

Default target:
  ~/labpulse-ha

Override target:
  LABPULSE_CONTAINER_DIR=/path/to/labpulse-ha ./setup_container_fs.sh

Options:
  -fake_usb  Mount socat fake USB serial paths for simulator testing.
  --backup  Create .bak timestamp copies before replacing generated files.

After this script has run once, work from ~/labpulse-ha:
  ./generate_compose.sh
  ./generate_homeassistant_config.sh
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
  USB_MODE_DESCRIPTION="fake USB serial simulator"
else
  USB_MODE_DESCRIPTION="real Arduino USB serial devices"
fi

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
copy_file "$SCRIPT_DIR/generate_compose.sh" "$PROJECT_DIR/generate_compose.sh"
chmod +x "$PROJECT_DIR/generate_compose.sh"
copy_file "$SCRIPT_DIR/generate_homeassistant_config.sh" "$PROJECT_DIR/generate_homeassistant_config.sh"
chmod +x "$PROJECT_DIR/generate_homeassistant_config.sh"
replace_dir "$SCRIPT_DIR/labpulse_common" "$PROJECT_DIR/labpulse-python/labpulse_common"

if [ ! -e "$LIVE_CONFIG" ]; then
  if [ -e "$PROJECT_DIR/labpulse-python/config.yaml" ]; then
    copy_file "$PROJECT_DIR/labpulse-python/config.yaml" "$LIVE_CONFIG"
    echo "Migrated legacy labpulse-python/config.yaml to live config: $LIVE_CONFIG"
  else
    copy_file "$TEMPLATE_CONFIG" "$LIVE_CONFIG"
    echo "Created live config from template: $LIVE_CONFIG"
  fi
else
  echo "Preserving existing live config: $LIVE_CONFIG"
fi

python3 - "$LIVE_CONFIG" "$FAKE_USB" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
fake_usb = sys.argv[2] == "1"

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

    data.setdefault("mqtt", {})["broker"] = "mosquitto"

    for service_config in data.get("services", {}).values():
        service_config.setdefault("enabled", True)

    if fake_usb:
        for section, serial_port in fake_ports.items():
            if section in data.get("services", {}):
                data["services"][section]["serial_port"] = serial_port

    path.write_text(yaml.safe_dump(data, sort_keys=False))
else:
    text = path.read_text()
    text = text.replace('broker: "localhost"', 'broker: "mosquitto"')
    text = text.replace("broker: localhost", "broker: mosquitto")

    if fake_usb:
        replacements = {
            'serial_port: "/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_03536383236351403122-if00"':
                'serial_port: "/tmp/labpulse-fake-serial/pump_room"',
            'serial_port: "/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_0353638323635131E2C3-if00"':
                'serial_port: "/tmp/labpulse-fake-serial/pressure"',
            'serial_port: "/dev/serial/by-id/usb-Arduino__www.arduino.cc__0043_0353638323635140B172-if00"':
                'serial_port: "/tmp/labpulse-fake-serial/turbo_pump"',
            'serial_port: "/dev/serial/by-id/..."':
                'serial_port: "/tmp/labpulse-fake-serial/pressure"',
        }
        for old, new in replacements.items():
            text = text.replace(old, new, 1)

    path.write_text(text)
PY

COMPOSE_MODE_ARGS=()
if [ "$FAKE_USB" -eq 1 ]; then
  COMPOSE_MODE_ARGS+=("-fake_usb")
fi

bash "$PROJECT_DIR/generate_compose.sh" \
  --config "$LIVE_CONFIG" \
  --output "$PROJECT_DIR/compose.yaml" \
  --project-dir "$PROJECT_DIR" \
  "${COMPOSE_MODE_ARGS[@]}"

bash "$PROJECT_DIR/generate_homeassistant_config.sh" \
  --config "$LIVE_CONFIG" \
  --ha-config-dir "$PROJECT_DIR/homeassistant/config" \
  --project-dir "$PROJECT_DIR"

cat <<EOF

Done.

Created/updated:
  $PROJECT_DIR/compose.yaml
  $PROJECT_DIR/config.yaml
  $PROJECT_DIR/generate_compose.sh
  $PROJECT_DIR/generate_homeassistant_config.sh
  $PROJECT_DIR/homeassistant/config/packages/labpulse_thresholds.yaml
  $PROJECT_DIR/homeassistant/config/labpulse_alarm_cards.yaml
  $PROJECT_DIR/homeassistant/config/.storage/lovelace
  $PROJECT_DIR/mosquitto/config/mosquitto.conf
  $PROJECT_DIR/labpulse-python/
  $PROJECT_DIR/logs/

USB mode:
  $USB_MODE_DESCRIPTION

Preserved:
  $PROJECT_DIR/homeassistant/config/

Next commands:
  cd "$PROJECT_DIR"
  nano config.yaml
  ./generate_compose.sh
  ./generate_homeassistant_config.sh
  docker compose config
  docker compose up -d --build

Important:
  EDIT THIS FILE for sensors and enabled flags:
    $PROJECT_DIR/config.yaml

  Do not edit docker_refactor/config.yaml for the running Pi system.
EOF
