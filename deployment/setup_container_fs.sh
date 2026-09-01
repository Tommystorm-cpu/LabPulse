#!/usr/bin/env bash
set -euo pipefail

# Prepare the live Raspberry Pi directory once; later commands regenerate from
# the preserved config without reinstalling deployment assets.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASSET_DIR="${LABPULSE_SETUP_ASSET_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PACKAGE_PARENT="${LABPULSE_PACKAGE_PARENT:-$ASSET_DIR/src}"
SETUP_COMMAND="${LABPULSE_SETUP_COMMAND:-./deployment/setup_container_fs.sh}"
PROJECT_DIR="${LABPULSE_LIVE_DIR:-$HOME/labpulse-live}"
LIVE_CONFIG="$PROJECT_DIR/config.yaml"
TEMPLATE_CONFIG="$ASSET_DIR/config.yaml"
HOST_REQUIREMENTS_SOURCE="$ASSET_DIR/requirements-host.txt"
HOST_REQUIREMENTS="$PROJECT_DIR/requirements-host.txt"
HOST_VENV="$PROJECT_DIR/.venv"
HOST_PYTHON="$HOST_VENV/bin/python"

BACKUP=0
FAKE_USB=0

# Print the same help text for both --help and invalid options.
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

  if [ ! -d "$PACKAGE_PARENT/labpulse" ]; then
    echo "ERROR: Installed LabPulse package not found below: $PACKAGE_PARENT" >&2
    echo "Reinstall LabPulse with pipx, then rerun setup." >&2
    exit 1
  fi

  # Make the managed generator environment import the exact pipx-installed
  # LabPulse release without copying its source into the live deployment.
  "$HOST_PYTHON" - "$PACKAGE_PARENT" <<'PY'
from pathlib import Path
import sys
import sysconfig

package_parent = Path(sys.argv[1]).expanduser().resolve()
if "\n" in str(package_parent):
    raise SystemExit("ERROR: LabPulse package path contains a newline")
purelib = Path(sysconfig.get_path("purelib"))
link_path = purelib / "labpulse-installed-package.pth"
link_path.write_text(f"{package_parent}\n", encoding="utf-8")
print(f"Linked managed Python to installed LabPulse: {link_path}")
PY

  "$HOST_PYTHON" - <<'PY'
from labpulse import __version__
from labpulse.hardware.registry import get_driver_definition

get_driver_definition("labpulse.serial_pipe")
print(f"Installed LabPulse package ready: {__version__}")
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

# These two helpers apply the optional backup rule before writing generated
# text or copying a package-managed file into the live directory.
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

echo "Setting up LabPulse container filesystem at: $PROJECT_DIR"

# Docker bind mounts require these host directories to exist before startup.
mkdir -p "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR/homeassistant/config"
mkdir -p "$PROJECT_DIR/mosquitto/config"
mkdir -p "$PROJECT_DIR/mosquitto/data"
mkdir -p "$PROJECT_DIR/mosquitto/log"
mkdir -p "$PROJECT_DIR/logs"

install_host_python_environment

if [ "$FAKE_USB" -eq 1 ]; then
  mkdir -p /tmp/labpulse-fake-serial
fi

# Keep the final operator summary in ordinary language rather than exposing the
# numeric shell flag used above.
if [ "$FAKE_USB" -eq 1 ]; then
  USB_MODE_DESCRIPTION="fake USB serial simulator, including UPS power"
else
  USB_MODE_DESCRIPTION="real Arduino USB serial devices"
fi

# Mosquitto stores subscriptions and retained MQTT state in the mounted data
# directory, while logs remain visible through Docker.
write_file "$PROJECT_DIR/mosquitto/config/mosquitto.conf" <<'EOF'
listener 1883
allow_anonymous true
persistence true
persistence_location /mosquitto/data/
log_dest stdout
EOF

# These are copied into ~/labpulse-live because operators run them after the
# package installation step has finished.
copy_file "$ASSET_DIR/deployment/generate_compose.sh" "$PROJECT_DIR/generate_compose.sh"
chmod +x "$PROJECT_DIR/generate_compose.sh"
copy_file "$ASSET_DIR/deployment/generate_homeassistant_config.sh" "$PROJECT_DIR/generate_homeassistant_config.sh"
chmod +x "$PROJECT_DIR/generate_homeassistant_config.sh"
copy_file "$ASSET_DIR/deployment/edit_config.sh" "$PROJECT_DIR/edit_config.sh"
chmod +x "$PROJECT_DIR/edit_config.sh"
copy_file "$ASSET_DIR/testing/real_hardware/hardware_fault_common.sh" "$PROJECT_DIR/hardware_fault_common.sh"
chmod +x "$PROJECT_DIR/hardware_fault_common.sh"
copy_file "$ASSET_DIR/testing/real_hardware/test_x1200_faults.sh" "$PROJECT_DIR/test_x1200_faults.sh"
chmod +x "$PROJECT_DIR/test_x1200_faults.sh"
copy_file "$ASSET_DIR/testing/real_hardware/test_dht11_fault.sh" "$PROJECT_DIR/test_dht11_fault.sh"
chmod +x "$PROJECT_DIR/test_dht11_fault.sh"
copy_file "$ASSET_DIR/simulate_serial.py" "$PROJECT_DIR/simulate_serial.py"
chmod +x "$PROJECT_DIR/simulate_serial.py"
copy_file "$ASSET_DIR/setup_usb_devices.py" "$PROJECT_DIR/setup_usb_devices.py"
chmod +x "$PROJECT_DIR/setup_usb_devices.py"

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

# Fake mode derives a separate runtime file. The real hardware settings remain
# untouched in the user-edited config.yaml for the next real deployment.
if [ "$FAKE_USB" -eq 1 ]; then
"$HOST_PYTHON" - "$LIVE_CONFIG" "$RUNTIME_CONFIG" "$FAKE_USB" <<'PY'
from pathlib import Path
import sys

source_path = Path(sys.argv[1])
destination_path = Path(sys.argv[2])
fake_usb = sys.argv[3] == "1"

text = source_path.read_text()

if fake_usb:
    from labpulse.common.fake_config import derive_fake_config

    text = derive_fake_config(text)

destination_path.write_text(text)
PY
fi

# Pass fake USB mode through to Compose generation so the right device mounts
# are written into compose.yaml.
COMPOSE_MODE_ARGS=()
if [ "$FAKE_USB" -eq 1 ]; then
  COMPOSE_MODE_ARGS+=("-fake_usb")
fi

# Leave the live folder with outputs built from one validated configuration load.
"$HOST_PYTHON" -m labpulse.deployment \
  --config "$RUNTIME_CONFIG" \
  --compose-output "$PROJECT_DIR/compose.yaml" \
  --project-dir "$PROJECT_DIR" \
  --ha-config-dir "$PROJECT_DIR/homeassistant/config" \
  "${COMPOSE_MODE_ARGS[@]}"

FAKE_CONFIG_OUTPUT=""
NEXT_USB_COMMAND="./setup_usb_devices.py --config config.yaml"
if [ "$FAKE_USB" -eq 1 ]; then
  FAKE_CONFIG_OUTPUT="  $PROJECT_DIR/config.fake.yaml"
  NEXT_USB_COMMAND="./setup_usb_devices.py --config config.fake.yaml --fake-usb"
fi

# Finish with the exact files and commands the operator will use next.
cat <<EOF

Done.

Created/updated:
  $PROJECT_DIR/compose.yaml
  $PROJECT_DIR/config.yaml
$FAKE_CONFIG_OUTPUT
  $PROJECT_DIR/generate_compose.sh
  $PROJECT_DIR/generate_homeassistant_config.sh
  $PROJECT_DIR/edit_config.sh
  $PROJECT_DIR/test_x1200_faults.sh
  $PROJECT_DIR/test_dht11_fault.sh
  $PROJECT_DIR/simulate_serial.py
  $PROJECT_DIR/setup_usb_devices.py
  $PROJECT_DIR/requirements-host.txt
  $PROJECT_DIR/.venv/
  $PROJECT_DIR/homeassistant/config/packages/labpulse_generated.yaml
  $PROJECT_DIR/homeassistant/config/labpulse-dashboard.yaml
  $PROJECT_DIR/mosquitto/config/mosquitto.conf
  $PROJECT_DIR/logs/

USB mode:
  $USB_MODE_DESCRIPTION

Preserved:
  $PROJECT_DIR/homeassistant/config/

Next commands:
  cd "$PROJECT_DIR"
  $NEXT_USB_COMMAND
  labpulse config
  labpulse up
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
