#!/usr/bin/env bash
set -euo pipefail

# One-time bootstrapper: copy the refactor files into the live Raspberry Pi
# working directory, then run the generators that users call directly later.
PROJECT_DIR="${LABPULSE_CONTAINER_DIR:-$HOME/labpulse-ha}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIVE_CONFIG="$PROJECT_DIR/config.yaml"
TEMPLATE_CONFIG="$SCRIPT_DIR/config.yaml"

BACKUP=0
FAKE_USB=0

# Print usage from one place so normal help and error paths stay consistent.
usage() {
  cat <<'EOF'
Usage: ./setup_container_fs.sh [options]

One-time bootstrap for the Raspberry Pi LabPulse folder.

Default target:
  ~/labpulse-ha

Override target:
  LABPULSE_CONTAINER_DIR=/path/to/labpulse-ha ./setup_container_fs.sh

Options:
  -fake_usb  Derive config.fake.yaml and mount pseudo-serial sensors,
             including the UPS power monitor, for simulator testing.
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

# Backups are opt-in because this script may be run repeatedly during setup.
backup_if_needed() {
  local path="$1"

  if [ "$BACKUP" -ne 1 ] || [ ! -e "$path" ]; then
    return
  fi

  local backup="${path}.bak.$(date +%Y%m%d-%H%M%S)"
  cp -a "$path" "$backup"
  echo "Backed up existing file: $backup"
}

# Write heredoc content to a file while preserving the optional backup behavior.
write_file() {
  local path="$1"
  backup_if_needed "$path"
  cat > "$path"
}

# Copy repo-managed files into the live ~/labpulse-ha working folder.
copy_file() {
  local source="$1"
  local destination="$2"
  backup_if_needed "$destination"
  cp "$source" "$destination"
}

# Replace copied Python package code so rebuilt containers use this repo state.
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

# Create the live folder skeleton expected by Docker volume mounts.
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

# Keep a plain-English USB mode for the final summary output.
if [ "$FAKE_USB" -eq 1 ]; then
  USB_MODE_DESCRIPTION="fake USB serial simulator, including UPS power"
else
  USB_MODE_DESCRIPTION="real Arduino USB serial devices"
fi

# Minimal local Mosquitto config for the LabPulse stack.
write_file "$PROJECT_DIR/mosquitto/config/mosquitto.conf" <<'EOF'
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest stdout
EOF

# The live folder owns the Dockerfile so docker compose can build from
# ~/labpulse-ha without needing the original repo checkout.
write_file "$PROJECT_DIR/labpulse-python/Dockerfile" <<'EOF'
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends gpiod modemmanager \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY labpulse_common ./labpulse_common
COPY labpulse_hardware ./labpulse_hardware
COPY labpulse_sms ./labpulse_sms

CMD ["python", "-m", "labpulse_hardware", "--service", "pressure_monitor"]
EOF

# Keep the runtime dependency list small for Raspberry Pi builds.
write_file "$PROJECT_DIR/labpulse-python/requirements.txt" <<'EOF'
paho-mqtt
pydantic
pyyaml
pyserial
smbus2
adafruit-blinka
adafruit-circuitpython-dht
lgpio
EOF

# Copy the scripts and Python service code that the live Compose project uses.
copy_file "$SCRIPT_DIR/generate_compose.sh" "$PROJECT_DIR/generate_compose.sh"
chmod +x "$PROJECT_DIR/generate_compose.sh"
copy_file "$SCRIPT_DIR/generate_homeassistant_config.sh" "$PROJECT_DIR/generate_homeassistant_config.sh"
chmod +x "$PROJECT_DIR/generate_homeassistant_config.sh"
copy_file "$SCRIPT_DIR/edit_config.sh" "$PROJECT_DIR/edit_config.sh"
chmod +x "$PROJECT_DIR/edit_config.sh"
copy_file "$SCRIPT_DIR/simulate_serial.py" "$PROJECT_DIR/simulate_serial.py"
chmod +x "$PROJECT_DIR/simulate_serial.py"
copy_file "$SCRIPT_DIR/setup_usb_devices.py" "$PROJECT_DIR/setup_usb_devices.py"
chmod +x "$PROJECT_DIR/setup_usb_devices.py"
replace_dir "$SCRIPT_DIR/labpulse_homeassistant" "$PROJECT_DIR/labpulse_homeassistant"
find "$PROJECT_DIR/labpulse_homeassistant" -type d -name "__pycache__" -prune -exec rm -rf {} +
replace_dir "$SCRIPT_DIR/labpulse_common" "$PROJECT_DIR/labpulse-python/labpulse_common"
replace_dir "$SCRIPT_DIR/labpulse_hardware" "$PROJECT_DIR/labpulse-python/labpulse_hardware"
replace_dir "$SCRIPT_DIR/labpulse_sms" "$PROJECT_DIR/labpulse-python/labpulse_sms"
find "$PROJECT_DIR/labpulse-python" -type d -name "__pycache__" -prune -exec rm -rf {} +
rm -f "$PROJECT_DIR/labpulse-python/main.py"

# Preserve the live user-edited config if it exists. The repo config is only a
# starter template for new installations.
if [ ! -e "$LIVE_CONFIG" ]; then
  copy_file "$TEMPLATE_CONFIG" "$LIVE_CONFIG"
  echo "Created live config from template: $LIVE_CONFIG"
else
  echo "Preserving existing live config: $LIVE_CONFIG"
fi

# Fake mode derives a runtime config so real I2C/serial/GPIO settings remain
# intact in the user-owned config.yaml and are available when switching back.
RUNTIME_CONFIG="$LIVE_CONFIG"
if [ "$FAKE_USB" -eq 1 ]; then
  RUNTIME_CONFIG="$PROJECT_DIR/config.fake.yaml"
fi

# Apply setup-time defaults to the selected runtime config. Fake mode writes a
# derived config.fake.yaml, keeping the live user-edited config.yaml intact.
python3 - "$LIVE_CONFIG" "$RUNTIME_CONFIG" "$FAKE_USB" "$PROJECT_DIR/labpulse-python" <<'PY'
from pathlib import Path
import sys

source_path = Path(sys.argv[1])
destination_path = Path(sys.argv[2])
fake_usb = sys.argv[3] == "1"
python_package_dir = Path(sys.argv[4])

text = source_path.read_text()
text = text.replace('broker: "localhost"', 'broker: "mosquitto"')
text = text.replace("broker: localhost", "broker: mosquitto")

if fake_usb:
    replacements = {
      "FAKE_PUMP_ROOM_PORT": "/tmp/labpulse-fake-serial/pump_room",
      "FAKE_PRESSURE_PORT": "/tmp/labpulse-fake-serial/pressure",
      "FAKE_TURBO_PUMP_PORT": "/tmp/labpulse-fake-serial/turbo_pump",
      "FAKE_UPS_PORT": "/tmp/labpulse-fake-serial/ups_monitor",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement, 1)

    real_room_environment = '''    driver: gpio
    gpio_sensor: dht11
    gpio_pin: "D4"'''
    simulated_room_environment = '''    driver: serial
    parser: pipe
    serial_port: "/tmp/labpulse-fake-serial/room_environment"
    baud_rate: 9600'''
    text = text.replace(real_room_environment, simulated_room_environment, 1)

    # Convert the configured power service to the same normalized measurements and
    # stable identities through the ups_monitor pseudo-serial endpoint. The
    # converter changes only transport-specific keys in that service block.
    sys.path.insert(0, str(python_package_dir))
    from labpulse_common.fake_config import convert_power_service_to_fake_serial

    text = convert_power_service_to_fake_serial(text)

destination_path.write_text(text)
PY

# Pass fake USB mode through to Compose generation so the right device mounts
# are written into compose.yaml.
COMPOSE_MODE_ARGS=()
if [ "$FAKE_USB" -eq 1 ]; then
  COMPOSE_MODE_ARGS+=("-fake_usb")
fi

# Leave the live folder with fresh generated Compose and Home Assistant config.
bash "$PROJECT_DIR/generate_compose.sh" \
  --config "$RUNTIME_CONFIG" \
  --output "$PROJECT_DIR/compose.yaml" \
  --project-dir "$PROJECT_DIR" \
  "${COMPOSE_MODE_ARGS[@]}"

bash "$PROJECT_DIR/generate_homeassistant_config.sh" \
  --config "$RUNTIME_CONFIG" \
  --ha-config-dir "$PROJECT_DIR/homeassistant/config" \
  --project-dir "$PROJECT_DIR"

FAKE_CONFIG_OUTPUT=""
NEXT_COMPOSE_COMMAND="./generate_compose.sh"
NEXT_HOMEASSISTANT_COMMAND="./generate_homeassistant_config.sh"
NEXT_USB_COMMAND="./setup_usb_devices.py --config config.yaml"
if [ "$FAKE_USB" -eq 1 ]; then
  FAKE_CONFIG_OUTPUT="  $PROJECT_DIR/config.fake.yaml"
  NEXT_COMPOSE_COMMAND="./generate_compose.sh --config config.fake.yaml -fake_usb"
  NEXT_HOMEASSISTANT_COMMAND="./generate_homeassistant_config.sh --config config.fake.yaml"
  NEXT_USB_COMMAND="./setup_usb_devices.py --config config.fake.yaml --fake-usb"
fi

# Finish by printing the live paths and the normal next commands.
cat <<EOF

Done.

Created/updated:
  $PROJECT_DIR/compose.yaml
  $PROJECT_DIR/config.yaml
$FAKE_CONFIG_OUTPUT
  $PROJECT_DIR/generate_compose.sh
  $PROJECT_DIR/generate_homeassistant_config.sh
  $PROJECT_DIR/edit_config.sh
  $PROJECT_DIR/simulate_serial.py
  $PROJECT_DIR/setup_usb_devices.py
  $PROJECT_DIR/labpulse_homeassistant/
  $PROJECT_DIR/homeassistant/config/packages/labpulse_generated.yaml
  $PROJECT_DIR/homeassistant/config/labpulse-dashboard.yaml
  $PROJECT_DIR/mosquitto/config/mosquitto.conf
  $PROJECT_DIR/labpulse-python/
  $PROJECT_DIR/labpulse-python/labpulse_common/
  $PROJECT_DIR/labpulse-python/labpulse_hardware/
  $PROJECT_DIR/labpulse-python/labpulse_sms/
  $PROJECT_DIR/logs/

USB mode:
  $USB_MODE_DESCRIPTION

Preserved:
  $PROJECT_DIR/homeassistant/config/

Next commands:
  cd "$PROJECT_DIR"
  $NEXT_USB_COMMAND
  nano config.yaml
  $NEXT_COMPOSE_COMMAND
  $NEXT_HOMEASSISTANT_COMMAND
  docker compose config
  docker compose up -d --build

Important:
  EDIT THIS FILE for sensors and enabled flags:
    $PROJECT_DIR/config.yaml

  Do not edit docker_refactor/config.yaml for the running Pi system.

  In fake mode, config.fake.yaml is derived from config.yaml. Edit config.yaml,
  then rerun setup_container_fs.sh -fake_usb to refresh the fake configuration.
EOF
