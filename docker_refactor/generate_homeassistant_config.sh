#!/usr/bin/env bash
set -euo pipefail

# Generate Home Assistant config from the live LabPulse config. This script is
# copied into ~/labpulse-ha and owns generated YAML plus explicit dashboard
# reset/backup/load operations.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${LABPULSE_CONTAINER_DIR:-$SCRIPT_DIR}"
CONFIG_PATH="$PROJECT_DIR/config.yaml"
HA_CONFIG_DIR="$PROJECT_DIR/homeassistant/config"
RESET_DASHBOARD=0
BACKUP_DASHBOARD=0
LOAD_DASHBOARD=0
RESOLVE_ENTITIES=0
SYNC_DASHBOARD_ENTITIES=0
HA_URL="${LABPULSE_HA_URL:-http://127.0.0.1:8123}"

# Resolve Home Assistant's active storage-backed Overview dashboard. Recent
# releases register Overview as a named dashboard and store it as
# .storage/lovelace.<id>; older installations use .storage/lovelace.
dashboard_storage_path() {
  python3 - "$HA_CONFIG_DIR" <<'PY'
import json
from pathlib import Path
import sys

storage = Path(sys.argv[1]) / ".storage"
registry_path = storage / "lovelace_dashboards"
if registry_path.exists():
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        for item in registry.get("data", {}).get("items", []):
            if item.get("url_path") == "lovelace" and item.get("mode", "storage") == "storage":
                dashboard_id = item.get("id")
                if isinstance(dashboard_id, str) and dashboard_id:
                    print(storage / f"lovelace.{dashboard_id}")
                    raise SystemExit
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
print(storage / "lovelace")
PY
}

# Print usage from one place so normal help and invalid-option errors agree.
usage() {
  cat <<'EOF'
Usage: ./generate_homeassistant_config.sh [options]

Generates Home Assistant config from the live config.yaml and the adjacent
alarm_defaults.json.

Options:
  --config PATH                 Config YAML to read. Default: ./config.yaml
  --ha-config-dir DIR           Home Assistant config folder. Default: ./homeassistant/config
  --project-dir DIR             LabPulse container folder. Default: script directory
  --reset-dashboard             Replace the editable dashboard with the generated starter dashboard.
  --backup-dashboard            Save the current editable dashboard to homeassistant_backups/.
  --load-dashboard              Restore homeassistant_backups/dashboard-latest/lovelace.
  --resolve-entities            Query Home Assistant and require every LabPulse MQTT entity.
  --sync-dashboard-entities     Replace exact stale entity IDs in the editable dashboard.
  --ha-url URL                  Home Assistant base URL. Default: http://127.0.0.1:8123
  -h, --help                    Show this help text.

Generated files:
  homeassistant/config/configuration.yaml
  homeassistant/config/packages/labpulse_generated.yaml
  homeassistant/config/labpulse_entity_map.yaml

Dashboard behavior:
  The active Overview store is resolved from .storage/lovelace_dashboards.
  No dashboard flag preserves that resolved file exactly as-is.
  --reset-dashboard creates or replaces that editable Home Assistant dashboard.
  --sync-dashboard-entities preserves layout and updates only resolved entity IDs.

Registry resolution:
  Set LABPULSE_HA_TOKEN to a Home Assistant long-lived access token.
  Normal generation remains offline and uses deterministic default entity IDs.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --config)
      CONFIG_PATH="$2"
      shift 2
      ;;
    --ha-config-dir)
      HA_CONFIG_DIR="$2"
      shift 2
      ;;
    --project-dir)
      PROJECT_DIR="$2"
      if [ "$CONFIG_PATH" = "$SCRIPT_DIR/config.yaml" ]; then
        CONFIG_PATH="$PROJECT_DIR/config.yaml"
      fi
      if [ "$HA_CONFIG_DIR" = "$SCRIPT_DIR/homeassistant/config" ]; then
        HA_CONFIG_DIR="$PROJECT_DIR/homeassistant/config"
      fi
      shift 2
      ;;
    --reset-dashboard)
      RESET_DASHBOARD=1
      shift
      ;;
    --backup-dashboard)
      BACKUP_DASHBOARD=1
      shift
      ;;
    --load-dashboard)
      LOAD_DASHBOARD=1
      shift
      ;;
    --resolve-entities)
      RESOLVE_ENTITIES=1
      shift
      ;;
    --sync-dashboard-entities)
      SYNC_DASHBOARD_ENTITIES=1
      shift
      ;;
    --ha-url)
      HA_URL="$2"
      shift 2
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

if [ "$RESET_DASHBOARD" -eq 1 ] && [ "$LOAD_DASHBOARD" -eq 1 ]; then
  echo "ERROR: --reset-dashboard and --load-dashboard cannot be used together." >&2
  exit 1
fi

if [ "$RESET_DASHBOARD" -eq 1 ] && [ "$SYNC_DASHBOARD_ENTITIES" -eq 1 ]; then
  echo "ERROR: --reset-dashboard and --sync-dashboard-entities cannot be used together." >&2
  exit 1
fi

if [ "$SYNC_DASHBOARD_ENTITIES" -eq 1 ] && [ "$RESOLVE_ENTITIES" -ne 1 ]; then
  echo "ERROR: --sync-dashboard-entities requires --resolve-entities." >&2
  exit 1
fi

if [ "$LOAD_DASHBOARD" -eq 1 ] && [ "$SYNC_DASHBOARD_ENTITIES" -eq 1 ]; then
  echo "ERROR: --load-dashboard and --sync-dashboard-entities cannot be used together." >&2
  exit 1
fi

if [ "$BACKUP_DASHBOARD" -eq 1 ] && [ "$LOAD_DASHBOARD" -eq 1 ]; then
  echo "ERROR: --backup-dashboard and --load-dashboard cannot be used together." >&2
  exit 1
fi

# A surgical dashboard sync is still a mutation of user-owned state, so always
# take the same timestamped backup used by the explicit backup operation.
if [ "$SYNC_DASHBOARD_ENTITIES" -eq 1 ]; then
  BACKUP_DASHBOARD=1
fi

# Copy one file or directory if it exists, replacing the destination cleanly.
# Used for Home Assistant UI backup/restore snapshots.
copy_if_exists() {
  local source="$1"
  local destination="$2"

  if [ ! -e "$source" ]; then
    return
  fi

  mkdir -p "$(dirname "$destination")"
  rm -rf "$destination"
  cp -a "$source" "$destination"
}

# Snapshot only the editable dashboard. This intentionally avoids copying all
# of .storage so auth/account state is not backed up here.
backup_dashboard() {
  local backup_root="$PROJECT_DIR/homeassistant_backups"
  local timestamp
  timestamp="$(date +%Y%m%d-%H%M%S)"
  local backup_dir="$backup_root/dashboard-$timestamp"
  local latest_dir="$backup_root/dashboard-latest"
  local source
  source="$(dashboard_storage_path)"

  if [ "$BACKUP_DASHBOARD" -ne 1 ]; then
    return
  fi

  if [ ! -e "$source" ]; then
    echo "ERROR: No editable dashboard found to back up: $source" >&2
    exit 1
  fi

  echo "Backing up editable Home Assistant dashboard: $source"
  echo "Backup destination: $backup_dir"

  mkdir -p "$backup_dir"
  copy_if_exists "$source" "$backup_dir/lovelace"

  rm -rf "$latest_dir"
  cp -a "$backup_dir" "$latest_dir"

  echo "Updated latest dashboard backup: $latest_dir"
}

# Restore the latest dashboard snapshot before generated YAML is refreshed.
load_dashboard() {
  local backup_dir="$PROJECT_DIR/homeassistant_backups/dashboard-latest"
  local source="$backup_dir/lovelace"
  local destination
  destination="$(dashboard_storage_path)"

  if [ "$LOAD_DASHBOARD" -ne 1 ]; then
    return
  fi

  if [ ! -e "$source" ]; then
    echo "ERROR: No dashboard backup found at: $source" >&2
    echo "Create one first with: ./generate_homeassistant_config.sh --backup-dashboard" >&2
    exit 1
  fi

  echo "Loading editable Home Assistant dashboard from: $source"
  echo "Restore destination: $destination"

  copy_if_exists "$source" "$destination"
}

# Fail with a readable fix when an earlier sudo/container run left generated
# Home Assistant files owned by another user.
check_homeassistant_config_writable() {
  local package_dir="$HA_CONFIG_DIR/packages"
  local package_file="$package_dir/labpulse_generated.yaml"

  mkdir -p "$package_dir"

  if [ -e "$package_file" ] && [ ! -w "$package_file" ]; then
    echo "ERROR: Cannot write Home Assistant config file: $package_file" >&2
    echo "" >&2
    echo "This usually means ~/labpulse-ha was created by sudo or by another user." >&2
    echo "For a fresh setup, run:" >&2
    echo "  sudo rm -rf \"$PROJECT_DIR\"" >&2
    echo "  cd \"$(pwd)\"" >&2
    echo "  ./setup_container_fs.sh -fake_usb" >&2
    echo "" >&2
    echo "If you want to keep the existing files instead, fix ownership:" >&2
    echo "  sudo chown -R \"$(id -u):$(id -g)\" \"$PROJECT_DIR\"" >&2
    exit 1
  fi

  if [ ! -w "$package_dir" ]; then
    echo "ERROR: Cannot write Home Assistant package directory: $package_dir" >&2
    echo "" >&2
    echo "For a fresh setup, run:" >&2
    echo "  sudo rm -rf \"$PROJECT_DIR\"" >&2
    echo "  cd \"$(pwd)\"" >&2
    echo "  ./setup_container_fs.sh -fake_usb" >&2
    echo "" >&2
    echo "If you want to keep the existing files instead, fix ownership:" >&2
    echo "  sudo chown -R \"$(id -u):$(id -g)\" \"$PROJECT_DIR\"" >&2
    exit 1
  fi
}

# Fail before rendering when Home Assistant's root-owned .storage directory
# prevents the invoking user from creating or replacing the resolved dashboard.
check_dashboard_writable() {
  if [ "$RESET_DASHBOARD" -ne 1 ] && \
     [ "$LOAD_DASHBOARD" -ne 1 ] && \
     [ "$SYNC_DASHBOARD_ENTITIES" -ne 1 ]; then
    return
  fi

  local dashboard_path
  dashboard_path="$(dashboard_storage_path)"
  local storage_dir
  storage_dir="$(dirname "$dashboard_path")"

  if [ -e "$dashboard_path" ]; then
    if [ -w "$dashboard_path" ]; then
      return
    fi

    echo "ERROR: Cannot write active Home Assistant dashboard: $dashboard_path" >&2
    echo "Fix only that file's ownership, then rerun this command:" >&2
    echo "  sudo chown \"$(id -u):$(id -g)\" \"$dashboard_path\"" >&2
    exit 1
  fi

  mkdir -p "$storage_dir" 2>/dev/null || true
  if [ -w "$storage_dir" ]; then
    return
  fi

  echo "ERROR: Cannot create active Home Assistant dashboard: $dashboard_path" >&2
  echo "Home Assistant owns .storage, so create only the resolved dashboard file:" >&2
  echo "  sudo touch \"$dashboard_path\"" >&2
  echo "  sudo chown \"$(id -u):$(id -g)\" \"$dashboard_path\"" >&2
  echo "Then rerun this command while Home Assistant is stopped." >&2
  exit 1
}

# Run shell-side lifecycle actions before the Python generator writes files.
mkdir -p "$HA_CONFIG_DIR"
check_homeassistant_config_writable
check_dashboard_writable
backup_dashboard
load_dashboard

GENERATOR_PACKAGE="$SCRIPT_DIR/labpulse_homeassistant"
if [ ! -f "$GENERATOR_PACKAGE/__main__.py" ]; then
  echo "ERROR: Home Assistant Python generator package not found: $GENERATOR_PACKAGE" >&2
  exit 1
fi

# The Python generator reads config.yaml plus its adjacent alarm_defaults.json,
# builds a normalized render model, and writes generated Home Assistant files.
# It only writes the editable dashboard when RESET_DASHBOARD is 1.
PYTHONPATH="$SCRIPT_DIR:$SCRIPT_DIR/labpulse-python${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m labpulse_homeassistant \
  "$CONFIG_PATH" "$HA_CONFIG_DIR" "$RESET_DASHBOARD" \
  "$RESOLVE_ENTITIES" "$SYNC_DASHBOARD_ENTITIES" "$HA_URL"
