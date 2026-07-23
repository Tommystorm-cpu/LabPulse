#!/usr/bin/env bash
set -euo pipefail

# One-time bootstrapper: copy the refactor files into the live Raspberry Pi
# working directory, then run the generators that users call directly later.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASSET_DIR="${LABPULSE_SETUP_ASSET_DIR:-$SCRIPT_DIR}"
PACKAGE_SOURCE="${LABPULSE_PACKAGE_SOURCE:-$SCRIPT_DIR/src/labpulse}"
SETUP_COMMAND="${LABPULSE_SETUP_COMMAND:-./setup_container_fs.sh}"
PROJECT_DIR="${LABPULSE_LIVE_DIR:-$HOME/labpulse-live}"
LIVE_CONFIG="$PROJECT_DIR/config.yaml"
TEMPLATE_CONFIG="$ASSET_DIR/config.yaml"
HOST_REQUIREMENTS_SOURCE="$ASSET_DIR/requirements-host.txt"
HOST_REQUIREMENTS="$PROJECT_DIR/requirements-host.txt"
HOST_VENV="$PROJECT_DIR/.venv"
HOST_PYTHON="$HOST_VENV/bin/python"

BACKUP=0
FAKE_USB=0

# Print usage from one place so normal help and error paths stay consistent.
usage() {
  cat <<EOF
Usage: $SETUP_COMMAND [options]

One-time bootstrap for the Raspberry Pi LabPulse folder.

Default target:
  ~/labpulse-live

Override target:
  labpulse --live-dir /path/to/labpulse-live setup

Options:
  -fake_usb  Derive config.fake.yaml and mount pseudo-serial sensors,
             including the UPS power monitor, for simulator testing.
  --backup  Create .bak timestamp copies before replacing generated files.

After this script has run once, work from ~/labpulse-live:
  ./generate_compose.sh
  ./generate_homeassistant_config.sh
EOF
}

# Create the isolated interpreter used by every command that runs on the Pi.
# Raspberry Pi OS protects its system Python, so LabPulse never installs host
# packages globally or asks users to activate an environment manually.
install_host_python_environment() {
  if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required to install LabPulse." >&2
    echo "Install Raspberry Pi OS's python3-full package, then rerun setup." >&2
    exit 1
  fi
  if [ ! -f "$HOST_REQUIREMENTS_SOURCE" ]; then
    echo "ERROR: Host dependency file is missing: $HOST_REQUIREMENTS_SOURCE" >&2
    exit 1
  fi

  copy_file "$HOST_REQUIREMENTS_SOURCE" "$HOST_REQUIREMENTS"
  if [ ! -x "$HOST_PYTHON" ]; then
    echo "Creating LabPulse host Python environment..."
    if ! python3 -m venv "$HOST_VENV"; then
      echo "ERROR: Could not create $HOST_VENV." >&2
      echo "Install Raspberry Pi OS's python3-full package, then rerun setup." >&2
      exit 1
    fi
  fi

  echo "Installing LabPulse host Python dependencies..."
  "$HOST_PYTHON" -m pip install \
    --disable-pip-version-check \
    --requirement "$HOST_REQUIREMENTS"

  "$HOST_PYTHON" - <<'PY'
import pydantic
import yaml

major = int(pydantic.__version__.split(".", 1)[0])
if major != 2:
    raise SystemExit(
        f"ERROR: LabPulse requires Pydantic 2, found {pydantic.__version__}"
    )
print(f"Host Python ready: Pydantic {pydantic.__version__}, PyYAML {yaml.__version__}")
PY
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

# Copy package-managed files into the live ~/labpulse-live working folder.
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

install_host_python_environment

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
# ~/labpulse-live without needing the original repo checkout.
write_file "$PROJECT_DIR/labpulse-python/Dockerfile" <<'EOF'
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends gpiod modemmanager \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY labpulse ./labpulse

CMD ["python", "-m", "labpulse.hardware", "--service", "pressure_monitor"]
EOF

# Keep the runtime dependency list small for Raspberry Pi builds.
write_file "$PROJECT_DIR/labpulse-python/requirements.txt" <<'EOF'
paho-mqtt
pydantic>=2,<3
PyYAML>=6,<7
pyserial
smbus2
adafruit-blinka
adafruit-circuitpython-dht
lgpio
EOF

# Copy the scripts and Python service code that the live Compose project uses.
copy_file "$ASSET_DIR/generate_compose.sh" "$PROJECT_DIR/generate_compose.sh"
chmod +x "$PROJECT_DIR/generate_compose.sh"
copy_file "$ASSET_DIR/generate_homeassistant_config.sh" "$PROJECT_DIR/generate_homeassistant_config.sh"
chmod +x "$PROJECT_DIR/generate_homeassistant_config.sh"
copy_file "$ASSET_DIR/edit_config.sh" "$PROJECT_DIR/edit_config.sh"
chmod +x "$PROJECT_DIR/edit_config.sh"
copy_file "$ASSET_DIR/simulate_serial.py" "$PROJECT_DIR/simulate_serial.py"
chmod +x "$PROJECT_DIR/simulate_serial.py"
copy_file "$ASSET_DIR/setup_usb_devices.py" "$PROJECT_DIR/setup_usb_devices.py"
chmod +x "$PROJECT_DIR/setup_usb_devices.py"
replace_dir "$PACKAGE_SOURCE" "$PROJECT_DIR/labpulse-python/labpulse"
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

# Derive config.fake.yaml only in fake mode. Real setup never rewrites the
# live user-edited config.yaml.
if [ "$FAKE_USB" -eq 1 ]; then
"$HOST_PYTHON" - "$LIVE_CONFIG" "$RUNTIME_CONFIG" "$FAKE_USB" "$PROJECT_DIR/labpulse-python" <<'PY'
from pathlib import Path
import sys
import yaml

source_path = Path(sys.argv[1])
destination_path = Path(sys.argv[2])
fake_usb = sys.argv[3] == "1"
python_package_dir = Path(sys.argv[4])

text = source_path.read_text()

if fake_usb:
    replacements = {
      "FAKE_PUMP_ROOM_PORT": "/tmp/labpulse-fake-serial/pump_room",
      "FAKE_PRESSURE_PORT": "/tmp/labpulse-fake-serial/pressure",
      "FAKE_TURBO_PUMP_PORT": "/tmp/labpulse-fake-serial/turbo_pump",
      "FAKE_UPS_PORT": "/tmp/labpulse-fake-serial/ups_monitor",
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement, 1)

    # Convert the configured power service to the same normalized measurements and
    # stable identities through the ups_monitor pseudo-serial endpoint. The
    # converter changes only transport-specific keys in that service block.
    sys.path.insert(0, str(python_package_dir))
    from labpulse.common.fake_config import (
        convert_power_service_to_fake_serial,
        convert_service_to_fake_serial,
    )

    services = (yaml.safe_load(text) or {}).get("services", {})
    if "room_environment" in services:
        text = convert_service_to_fake_serial(
            text,
            "room_environment",
            "/tmp/labpulse-fake-serial/room_environment",
        )
    text = convert_power_service_to_fake_serial(text)

destination_path.write_text(text)
PY
fi

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
NEXT_USB_COMMAND="./setup_usb_devices.py --config config.yaml"
if [ "$FAKE_USB" -eq 1 ]; then
  FAKE_CONFIG_OUTPUT="  $PROJECT_DIR/config.fake.yaml"
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
  $PROJECT_DIR/requirements-host.txt
  $PROJECT_DIR/.venv/
  $PROJECT_DIR/homeassistant/config/packages/labpulse_generated.yaml
  $PROJECT_DIR/homeassistant/config/labpulse-dashboard.yaml
  $PROJECT_DIR/mosquitto/config/mosquitto.conf
  $PROJECT_DIR/labpulse-python/
  $PROJECT_DIR/labpulse-python/labpulse/
  $PROJECT_DIR/logs/

USB mode:
  $USB_MODE_DESCRIPTION

Preserved:
  $PROJECT_DIR/homeassistant/config/

Next commands:
  cd "$PROJECT_DIR"
  $NEXT_USB_COMMAND
  labpulse edit
  labpulse up --build
  labpulse restart
  labpulse ps
  labpulse open

Important:
  EDIT THIS FILE for sensors and enabled flags:
    $PROJECT_DIR/config.yaml

  Do not edit a package or repository config.yaml for the running Pi system.

  In fake mode, config.fake.yaml is derived from config.yaml. Edit config.yaml,
  then rerun $SETUP_COMMAND -fake_usb to refresh the fake configuration.
EOF
