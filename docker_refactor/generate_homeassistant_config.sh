#!/usr/bin/env bash
set -euo pipefail

# Generate Home Assistant config from the live LabPulse config. This script is
# copied into ~/labpulse-ha and owns HA package generation, dashboard seeding,
# and UI backup/restore.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${LABPULSE_CONTAINER_DIR:-$SCRIPT_DIR}"
CONFIG_PATH="$PROJECT_DIR/config.yaml"
HA_CONFIG_DIR="$PROJECT_DIR/homeassistant/config"
BACKUP_HOMEASSISTANT_UI=0
RESTORE_HOMEASSISTANT_UI=0
FRESH_HOMEASSISTANT=0
REFRESH_DASHBOARD=0

# Print usage from one place so normal help and invalid-option errors agree.
usage() {
  cat <<'EOF'
Usage: ./generate_homeassistant_config.sh [options]

Generates Home Assistant config for LabPulse from the live config.yaml.

Options:
  --config PATH                 Config YAML to read. Default: ./config.yaml
  --ha-config-dir DIR           Home Assistant config folder. Default: ./homeassistant/config
  --project-dir DIR             LabPulse container folder. Default: script directory
  --fresh-homeassistant         Replace generated Home Assistant config/dashboard.
  --refresh-dashboard           Rebuild only the editable LabPulse dashboard.
  --backup-homeassistant-ui     Snapshot current Home Assistant UI/config state.
  --restore-homeassistant-ui    Restore the latest Home Assistant UI/config snapshot.
  -h, --help                    Show this help text.

Generated files:
  homeassistant/config/configuration.yaml
  homeassistant/config/packages/labpulse_thresholds.yaml
  homeassistant/config/labpulse_alarm_cards.yaml
  homeassistant/config/.storage/lovelace

The generated dashboard is written as a Home Assistant UI dashboard, not a
YAML-mode Lovelace dashboard, so it remains editable in the Home Assistant UI.
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
    --fresh-homeassistant|--fresh-ha)
      FRESH_HOMEASSISTANT=1
      shift
      ;;
    --backup-homeassistant-ui|--backup-ha-ui)
      BACKUP_HOMEASSISTANT_UI=1
      shift
      ;;
    --refresh-dashboard)
      REFRESH_DASHBOARD=1
      shift
      ;;
    --restore-homeassistant-ui|--restore-ha-ui)
      RESTORE_HOMEASSISTANT_UI=1
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

# A fresh wipe and a restore are opposite operations. Refuse the combination so
# the caller cannot accidentally restore and delete in the same run.
if [ "$FRESH_HOMEASSISTANT" -eq 1 ] && [ "$RESTORE_HOMEASSISTANT_UI" -eq 1 ]; then
  echo "ERROR: --fresh-homeassistant and --restore-homeassistant-ui cannot be used together." >&2
  exit 1
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

# Snapshot the editable dashboard and LabPulse-generated YAML. This intentionally
# avoids copying all of .storage so auth/account state is not backed up here.
backup_homeassistant_ui() {
  local backup_root="$PROJECT_DIR/homeassistant_backups"
  local timestamp
  timestamp="$(date +%Y%m%d-%H%M%S)"
  local backup_dir="$backup_root/ui-$timestamp"
  local latest_dir="$backup_root/ui-latest"

  if [ "$BACKUP_HOMEASSISTANT_UI" -ne 1 ]; then
    return
  fi

  echo "Backing up Home Assistant UI/config state from: $HA_CONFIG_DIR"
  echo "Backup destination: $backup_dir"

  mkdir -p "$backup_dir"

  copy_if_exists "$HA_CONFIG_DIR/.storage/lovelace" "$backup_dir/.storage/lovelace"
  copy_if_exists "$HA_CONFIG_DIR/configuration.yaml" "$backup_dir/configuration.yaml"
  copy_if_exists "$HA_CONFIG_DIR/packages" "$backup_dir/packages"
  copy_if_exists "$HA_CONFIG_DIR/labpulse_alarm_cards.yaml" "$backup_dir/labpulse_alarm_cards.yaml"
  copy_if_exists "$HA_CONFIG_DIR/automations.yaml" "$backup_dir/automations.yaml"
  copy_if_exists "$HA_CONFIG_DIR/input_numbers.yaml" "$backup_dir/input_numbers.yaml"
  copy_if_exists "$HA_CONFIG_DIR/input_booleans.yaml" "$backup_dir/input_booleans.yaml"

  rm -rf "$latest_dir"
  cp -a "$backup_dir" "$latest_dir"

  echo "Updated latest Home Assistant UI backup: $latest_dir"
}

# Restore the latest UI/config snapshot before regenerating LabPulse package
# files. This lets the user recover an edited dashboard layout.
restore_homeassistant_ui() {
  local backup_dir="$PROJECT_DIR/homeassistant_backups/ui-latest"

  if [ "$RESTORE_HOMEASSISTANT_UI" -ne 1 ]; then
    return
  fi

  if [ ! -d "$backup_dir" ]; then
    echo "ERROR: No Home Assistant UI backup found at: $backup_dir" >&2
    echo "Create one first with: ./generate_homeassistant_config.sh --backup-homeassistant-ui" >&2
    exit 1
  fi

  echo "Restoring Home Assistant UI/config state from: $backup_dir"
  echo "Restore destination: $HA_CONFIG_DIR"

  mkdir -p "$HA_CONFIG_DIR"

  copy_if_exists "$backup_dir/.storage/lovelace" "$HA_CONFIG_DIR/.storage/lovelace"
  copy_if_exists "$backup_dir/configuration.yaml" "$HA_CONFIG_DIR/configuration.yaml"
  copy_if_exists "$backup_dir/packages" "$HA_CONFIG_DIR/packages"
  copy_if_exists "$backup_dir/labpulse_alarm_cards.yaml" "$HA_CONFIG_DIR/labpulse_alarm_cards.yaml"
  copy_if_exists "$backup_dir/automations.yaml" "$HA_CONFIG_DIR/automations.yaml"
  copy_if_exists "$backup_dir/input_numbers.yaml" "$HA_CONFIG_DIR/input_numbers.yaml"
  copy_if_exists "$backup_dir/input_booleans.yaml" "$HA_CONFIG_DIR/input_booleans.yaml"
}

# Wipe the Home Assistant config folder for a truly fresh generated setup. The
# path sanity check protects against catastrophic rm -rf mistakes.
fresh_homeassistant_config() {
  if [ "$FRESH_HOMEASSISTANT" -ne 1 ]; then
    return
  fi

  local resolved_config_dir
  resolved_config_dir="$(cd "$HA_CONFIG_DIR" && pwd -P)"

  case "$resolved_config_dir" in
    ""|"/"|"$HOME"|"$PROJECT_DIR")
      echo "ERROR: Refusing to wipe unsafe Home Assistant config path: $resolved_config_dir" >&2
      exit 1
      ;;
  esac

  echo "Fresh Home Assistant generation requested."
  echo "Wiping all Home Assistant config contents in: $resolved_config_dir"

  find "$resolved_config_dir" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
}

# Fail with a readable fix when an earlier sudo/container run left generated
# Home Assistant files owned by another user.
check_homeassistant_config_writable() {
  local package_dir="$HA_CONFIG_DIR/packages"
  local threshold_file="$package_dir/labpulse_thresholds.yaml"

  mkdir -p "$package_dir"

  if [ -e "$threshold_file" ] && [ ! -w "$threshold_file" ]; then
    echo "ERROR: Cannot write Home Assistant config file: $threshold_file" >&2
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

# Run shell-side lifecycle actions before the Python generator writes files.
mkdir -p "$HA_CONFIG_DIR"
backup_homeassistant_ui
restore_homeassistant_ui
fresh_homeassistant_config
check_homeassistant_config_writable

GENERATOR_PACKAGE="$SCRIPT_DIR/labpulse_homeassistant"
if [ ! -f "$GENERATOR_PACKAGE/generator.py" ]; then
  echo "ERROR: Home Assistant Python generator package not found: $GENERATOR_PACKAGE" >&2
  exit 1
fi

# The Python generator does structured YAML/JSON work: reading config.yaml,
# reading Home Assistant's entity registry, building helpers/automations, and
# seeding an editable UI dashboard.
PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m labpulse_homeassistant.generator \
  "$CONFIG_PATH" "$HA_CONFIG_DIR" "$FRESH_HOMEASSISTANT" "$REFRESH_DASHBOARD"
