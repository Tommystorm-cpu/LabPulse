#!/usr/bin/env bash
set -euo pipefail

# Edit, validate, and apply the live Raspberry Pi LabPulse configuration.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${LABPULSE_CONTAINER_DIR:-$SCRIPT_DIR}"
CONFIG_PATH="$PROJECT_DIR/config.yaml"
CONFIG_BACKUP="$PROJECT_DIR/config.yaml.edit-backup"
COMPOSE_SCRIPT="$PROJECT_DIR/generate_compose.sh"
HOMEASSISTANT_SCRIPT="$PROJECT_DIR/generate_homeassistant_config.sh"

# Remove temporary validation files without touching the live configuration.
cleanup() {
  if [ -n "${WORK_CONFIG:-}" ] && [ -e "$WORK_CONFIG" ]; then
    rm -f "$WORK_CONFIG"
  fi
  if [ -n "${CHECK_DIR:-}" ] && [ -d "$CHECK_DIR" ]; then
    rm -rf "$CHECK_DIR"
  fi
}
trap cleanup EXIT

# Stop early when setup has not installed every file this workflow needs.
for required_path in "$CONFIG_PATH" "$COMPOSE_SCRIPT" "$HOMEASSISTANT_SCRIPT"; do
  if [ ! -f "$required_path" ]; then
    echo "ERROR: Required LabPulse file is missing: $required_path" >&2
    exit 1
  fi
done

# Work beside config.yaml so any relative config paths keep the same base directory.
WORK_CONFIG="$(mktemp "$PROJECT_DIR/.config.yaml.editing.XXXXXX")"
CHECK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/labpulse-config-check.XXXXXX")"
cp -p "$CONFIG_PATH" "$WORK_CONFIG"

EDITOR_COMMAND="${VISUAL:-${EDITOR:-nano}}"
read -r -a EDITOR_PARTS <<< "$EDITOR_COMMAND"
if [ "${#EDITOR_PARTS[@]}" -eq 0 ]; then
  echo "ERROR: VISUAL or EDITOR resolved to an empty command." >&2
  exit 1
fi

echo "Editing live LabPulse configuration: $CONFIG_PATH"
if ! "${EDITOR_PARTS[@]}" "$WORK_CONFIG"; then
  echo "Editor exited with an error; no changes were applied." >&2
  exit 1
fi

if cmp -s "$CONFIG_PATH" "$WORK_CONFIG"; then
  echo "No configuration changes detected; nothing was restarted."
  exit 0
fi

echo "Validating configuration schema..."
PYTHONPATH="$PROJECT_DIR/src:$PROJECT_DIR/labpulse-python${PYTHONPATH:+:$PYTHONPATH}" \
  python3 - "$WORK_CONFIG" <<'PY'
from pathlib import Path
import sys

from labpulse.common.config import load_config

load_config(Path(sys.argv[1]))
print("Configuration schema is valid.")
PY

# Exercise both generators away from the live outputs before installing anything.
echo "Checking generated Compose and Home Assistant configuration..."
bash "$COMPOSE_SCRIPT" \
  --config "$WORK_CONFIG" \
  --output "$CHECK_DIR/compose.yaml" \
  --project-dir "$PROJECT_DIR"
bash "$HOMEASSISTANT_SCRIPT" \
  --config "$WORK_CONFIG" \
  --ha-config-dir "$CHECK_DIR/homeassistant/config" \
  --project-dir "$PROJECT_DIR"

# Keep one predictable rollback copy instead of accumulating timestamped backups.
cp -p "$CONFIG_PATH" "$CONFIG_BACKUP"
cp -p "$WORK_CONFIG" "$CONFIG_PATH"

# Restore the prior source of truth and its deterministic outputs after a failed check.
restore_previous_config() {
  echo "Restoring the previous validated configuration..." >&2
  cp -p "$CONFIG_BACKUP" "$CONFIG_PATH"
  bash "$COMPOSE_SCRIPT" \
    --config "$CONFIG_PATH" \
    --output "$PROJECT_DIR/compose.yaml" \
    --project-dir "$PROJECT_DIR"
  bash "$HOMEASSISTANT_SCRIPT" \
    --config "$CONFIG_PATH" \
    --ha-config-dir "$PROJECT_DIR/homeassistant/config" \
    --project-dir "$PROJECT_DIR"
}

echo "Generating live configuration..."
if ! bash "$COMPOSE_SCRIPT" \
  --config "$CONFIG_PATH" \
  --output "$PROJECT_DIR/compose.yaml" \
  --project-dir "$PROJECT_DIR"; then
  restore_previous_config
  exit 1
fi
if ! bash "$HOMEASSISTANT_SCRIPT" \
  --config "$CONFIG_PATH" \
  --ha-config-dir "$PROJECT_DIR/homeassistant/config" \
  --project-dir "$PROJECT_DIR"; then
  restore_previous_config
  exit 1
fi

cd "$PROJECT_DIR"
if ! sudo docker compose config --quiet; then
  echo "Docker Compose rejected the generated configuration." >&2
  restore_previous_config
  exit 1
fi

echo "Checking the generated YAML with Home Assistant..."
if ! RUNNING_SERVICES="$(sudo docker compose ps --status running --services)"; then
  echo "Could not inspect the running Compose services." >&2
  restore_previous_config
  exit 1
fi
if grep -qx "homeassistant" <<< "$RUNNING_SERVICES"; then
  HA_CHECK=(sudo docker compose exec -T homeassistant)
else
  HA_CHECK=(sudo docker compose run --rm --no-deps homeassistant)
fi
if ! "${HA_CHECK[@]}" python -m homeassistant --script check_config --config /config; then
  echo "Home Assistant rejected the generated configuration." >&2
  restore_previous_config
  exit 1
fi

echo "Refreshing LabPulse and Home Assistant..."
sudo docker compose up -d --remove-orphans --force-recreate
sudo docker compose ps

cat <<EOF

Configuration applied successfully.
Live config: $CONFIG_PATH
Rollback copy: $CONFIG_BACKUP

SAFETY REMINDER
Home Assistant has been refreshed. Check Monitor for "Global Mute Applied" and
"Test Mode Applied", review the new configuration, and only disable either
safeguard when its notification behaviour is ready to resume.
EOF
