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
BACKUP_DIR="$PROJECT_DIR/backups"

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
  --fake-hardware  Run every configured sensor and output through safe,
                   in-memory simulation while preserving the real config.
  --backup  Keep one rolling copy of each replaced file in backups/.

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
    -fake_usb|--fake-hardware|--fake-usb|--fake_usb)
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

# Older releases left timestamped and tool-specific backups beside the active
# files. An explicitly backed-up setup consolidates those copies so upgrading
# also clears the old live-directory clutter without losing rollback coverage.
consolidate_legacy_backups() {
  if [ "$BACKUP" -ne 1 ]; then
    return
  fi

  mkdir -p "$BACKUP_DIR"
  local old_backup
  local old_name
  local active_name
  local active_path
  for old_backup in "$PROJECT_DIR"/*.bak.*; do
    if [ ! -f "$old_backup" ]; then
      continue
    fi

    old_name="$(basename "$old_backup")"
    active_name="${old_name%%.bak.*}"
    active_path="$PROJECT_DIR/$active_name"
    if [ -f "$active_path" ]; then
      cp -a "$active_path" "$BACKUP_DIR/$active_name.bak"
    fi
    rm -f -- "$old_backup"
  done

  for old_name in \
    config.yaml.edit-backup \
    config.fake.yaml.edit-backup \
    config.yaml.usb-setup-backup; do
    old_backup="$PROJECT_DIR/$old_name"
    if [ -f "$old_backup" ]; then
      mv -f -- "$old_backup" "$BACKUP_DIR/$old_name"
    fi
  done
}

# Backups are opt-in because this script may be run repeatedly during setup.
# Each destination has one predictable rolling copy outside the live root.
backup_if_needed() {
  local path="$1"

  if [ "$BACKUP" -ne 1 ] || [ ! -e "$path" ]; then
    return
  fi

  mkdir -p "$BACKUP_DIR"
  local backup="$BACKUP_DIR/$(basename "$path").bak"
  cp -a "$path" "$backup"
  echo "Backed up existing file: $backup"

  # Once the current file is safely copied, remove the timestamped copies made
  # by older LabPulse releases for this exact destination.
  local old_backup
  for old_backup in "${path}.bak."*; do
    if [ -e "$old_backup" ]; then
      rm -f -- "$old_backup"
    fi
  done
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
mkdir -p "$PROJECT_DIR/config.d"
mkdir -p "$PROJECT_DIR/homeassistant/config"
mkdir -p "$PROJECT_DIR/mosquitto/config"
mkdir -p "$PROJECT_DIR/mosquitto/data"
mkdir -p "$PROJECT_DIR/mosquitto/log"
mkdir -p "$PROJECT_DIR/logs"

consolidate_legacy_backups

install_host_python_environment

# Keep the final operator summary in ordinary language rather than exposing the
# numeric shell flag used above.
if [ "$FAKE_USB" -eq 1 ]; then
  USB_MODE_DESCRIPTION="complete fake hardware; no LabPulse worker accesses physical devices"
else
  USB_MODE_DESCRIPTION="real configured hardware"
fi

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

# Preserve the live user-edited config if it exists. The repo config is only a
# starter template for new installations.
if [ ! -e "$LIVE_CONFIG" ]; then
  copy_file "$TEMPLATE_CONFIG" "$LIVE_CONFIG"
  if [ -d "$ASSET_DIR/config.d" ]; then
    cp -a "$ASSET_DIR/config.d/." "$PROJECT_DIR/config.d/"
  fi
  echo "Created live config from template: $LIVE_CONFIG"
else
  echo "Preserving existing live config: $LIVE_CONFIG"
fi

# Deployment resolves operator-owned measurement fragments first, then writes
# config.resolved.yaml and derives config.fake.yaml from that complete document.
RUNTIME_CONFIG="$LIVE_CONFIG"

# Pass fake-hardware mode through to Compose generation so workers select safe
# in-memory drivers and receive no physical device mounts.
COMPOSE_MODE_ARGS=()
if [ "$FAKE_USB" -eq 1 ]; then
  COMPOSE_MODE_ARGS+=("--fake-hardware")
fi

# Leave the live folder with outputs built from one validated configuration load.
"$HOST_PYTHON" -m labpulse.deployment \
  --config "$RUNTIME_CONFIG" \
  --compose-output "$PROJECT_DIR/compose.yaml" \
  --project-dir "$PROJECT_DIR" \
  --ha-config-dir "$PROJECT_DIR/homeassistant/config" \
  "${COMPOSE_MODE_ARGS[@]}"

FAKE_CONFIG_OUTPUT=""
NEXT_HARDWARE_COMMAND="labpulse --live-dir \"$PROJECT_DIR\" usb"
if [ "$FAKE_USB" -eq 1 ]; then
  FAKE_CONFIG_OUTPUT="  $PROJECT_DIR/config.fake.yaml"
  NEXT_HARDWARE_COMMAND="# No device assignment or separate simulator is needed."
fi

# Finish with the exact files and commands the operator will use next.
cat <<EOF

Done.

Created/updated:
  $PROJECT_DIR/compose.yaml
  $PROJECT_DIR/config.yaml
  $PROJECT_DIR/config.d/
  $PROJECT_DIR/config.resolved.yaml
$FAKE_CONFIG_OUTPUT
  $PROJECT_DIR/generate_compose.sh
  $PROJECT_DIR/generate_homeassistant_config.sh
  $PROJECT_DIR/edit_config.sh
  $PROJECT_DIR/test_x1200_faults.sh
  $PROJECT_DIR/test_dht11_fault.sh
  $PROJECT_DIR/requirements-host.txt
  $PROJECT_DIR/.venv/
  $PROJECT_DIR/homeassistant/config/packages/labpulse_generated.yaml
  $PROJECT_DIR/homeassistant/config/labpulse-dashboard.yaml
  $PROJECT_DIR/mosquitto/config/mosquitto.conf
  $PROJECT_DIR/logs/

Hardware mode:
  $USB_MODE_DESCRIPTION

Preserved:
  $PROJECT_DIR/homeassistant/config/

Next commands:
  cd "$PROJECT_DIR"
  $NEXT_HARDWARE_COMMAND
  labpulse config
  labpulse up
  labpulse restart
  labpulse ps
  labpulse open

Important:
  EDIT THESE SOURCES for sensors and enabled flags:
    $PROJECT_DIR/config.yaml
    $PROJECT_DIR/config.d/*.yaml (when referenced by measurements_file)

  Do not edit config.resolved.yaml, config.fake.yaml, or a package/repository
  config.yaml for the running Pi system.

  In fake mode, config.fake.yaml preserves the complete resolved source bundle.
  Compose selects in-memory drivers at runtime. Run labpulse config after
  editing to refresh every generated file.
EOF
