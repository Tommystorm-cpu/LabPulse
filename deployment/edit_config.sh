#!/usr/bin/env bash
set -euo pipefail

# Edit, validate, and apply the operator-owned LabPulse configuration bundle.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${LABPULSE_LIVE_DIR:-$SCRIPT_DIR}"
CONFIG_PATH="$PROJECT_DIR/config.yaml"
CONFIG_DIR="$PROJECT_DIR/config.d"
RESOLVED_CONFIG_PATH="$PROJECT_DIR/config.resolved.yaml"
FAKE_CONFIG_PATH="$PROJECT_DIR/config.fake.yaml"
BACKUP_DIR="$PROJECT_DIR/backups"
SOURCE_BACKUP="$BACKUP_DIR/config-source.edit-backup"
COMPOSE_PATH="$PROJECT_DIR/compose.yaml"
HOST_PYTHON="${LABPULSE_PYTHON:-$PROJECT_DIR/.venv/bin/python}"

cleanup() {
  if [ -n "${WORK_ROOT:-}" ] && [ -d "$WORK_ROOT" ]; then
    rm -rf -- "$WORK_ROOT"
  fi
  if [ -n "${CHECK_DIR:-}" ] && [ -d "$CHECK_DIR" ]; then
    rm -rf -- "$CHECK_DIR"
  fi
  if [ -n "${BACKUP_STAGING:-}" ] && [ -d "$BACKUP_STAGING" ]; then
    rm -rf -- "$BACKUP_STAGING"
  fi
}
trap cleanup EXIT

if [ ! -f "$CONFIG_PATH" ]; then
  echo "ERROR: Required LabPulse file is missing: $CONFIG_PATH" >&2
  exit 1
fi
if [ ! -x "$HOST_PYTHON" ]; then
  echo "ERROR: LabPulse's managed Python environment is missing: $HOST_PYTHON" >&2
  echo "Run 'labpulse setup' to restore the managed environment." >&2
  exit 1
fi

DOCKER_COMMAND_TEXT="${LABPULSE_DOCKER_COMMAND:-sudo docker}"
read -r -a DOCKER_PARTS <<< "$DOCKER_COMMAND_TEXT"
if [ "${#DOCKER_PARTS[@]}" -eq 0 ]; then
  echo "ERROR: LABPULSE_DOCKER_COMMAND resolved to an empty command." >&2
  exit 1
fi

ACTIVE_FAKE_USB=0
if [ -f "$COMPOSE_PATH" ] && \
  grep -Eq 'config\.fake\.yaml:/app/config\.yaml(:ro)?' "$COMPOSE_PATH"; then
  ACTIVE_FAKE_USB=1
fi
COMPOSE_MODE_ARGS=()
if [ "$ACTIVE_FAKE_USB" -eq 1 ]; then
  COMPOSE_MODE_ARGS+=("--fake-usb")
fi

WORK_ROOT="$(mktemp -d "$PROJECT_DIR/.config-source.editing.XXXXXX")"
CHECK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/labpulse-config-check.XXXXXX")"
BACKUP_STAGING=""
cp -p "$CONFIG_PATH" "$WORK_ROOT/config.yaml"
mkdir -p "$WORK_ROOT/config.d"
if [ -d "$CONFIG_DIR" ]; then
  if find "$CONFIG_DIR" -type l -print -quit | grep -q .; then
    echo "ERROR: config.d must not contain symbolic links." >&2
    exit 1
  fi
  cp -a "$CONFIG_DIR/." "$WORK_ROOT/config.d/"
fi

if [ -n "${VISUAL:-}" ]; then
  EDITOR_COMMAND="$VISUAL"
elif [ -n "${EDITOR:-}" ]; then
  EDITOR_COMMAND="$EDITOR"
elif command -v micro >/dev/null 2>&1; then
  EDITOR_COMMAND="micro"
elif command -v nano >/dev/null 2>&1; then
  EDITOR_COMMAND="nano"
else
  echo "ERROR: No supported editor found. Install micro or nano, or set VISUAL/EDITOR." >&2
  exit 1
fi
read -r -a EDITOR_PARTS <<< "$EDITOR_COMMAND"
if [ "${#EDITOR_PARTS[@]}" -eq 0 ]; then
  echo "ERROR: VISUAL or EDITOR resolved to an empty command." >&2
  exit 1
fi

REQUESTED_FILES=("$@")
if [ "${#REQUESTED_FILES[@]}" -eq 0 ]; then
  REQUESTED_FILES=("config.yaml")
  echo "Configured measurement files:"
  "$HOST_PYTHON" - "$CONFIG_PATH" <<'PY' || true
from pathlib import Path
import sys

from labpulse.common.config import ConfigError, load_config

master = Path(sys.argv[1]).resolve()
try:
    document = load_config(master)
except ConfigError as error:
    print(f"  unavailable until the current source validates: {error}")
else:
    fragments = [path.relative_to(master.parent) for path in document.source_paths[1:]]
    if fragments:
        for path in fragments:
            print(f"  {path.as_posix()}")
    else:
        print("  none")
PY
fi

if ! EDIT_PATH_OUTPUT="$(
  "$HOST_PYTHON" - "$PROJECT_DIR" "$WORK_ROOT" "${REQUESTED_FILES[@]}" <<'PY'
from pathlib import Path, PureWindowsPath
import sys

live_root = Path(sys.argv[1]).resolve()
work_root = Path(sys.argv[2]).resolve()
for raw in sys.argv[3:]:
    relative = Path(raw)
    allowed = relative == Path("config.yaml") or (
        len(relative.parts) >= 2
        and relative.parts[0] == "config.d"
        and relative.suffix.lower() in {".yaml", ".yml"}
    )
    if (
        not allowed
        or relative.is_absolute()
        or PureWindowsPath(raw).is_absolute()
        or raw.startswith(("/", "\\"))
        or ".." in relative.parts
    ):
        raise SystemExit(
            f"ERROR: Config edit target must be config.yaml or YAML beneath config.d: {raw}"
        )
    current = live_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise SystemExit(f"ERROR: Config edit target must not use symlinks: {raw}")
    staged = work_root.joinpath(*relative.parts)
    staged.parent.mkdir(parents=True, exist_ok=True)
    if not staged.exists():
        staged.write_text("{}\n", encoding="utf-8")
    print(staged)
PY
)"; then
  exit 1
fi
mapfile -t EDIT_PATHS <<< "$EDIT_PATH_OUTPUT"

echo "Editing staged LabPulse source files:"
printf '  %s\n' "${REQUESTED_FILES[@]}"
if ! "${EDITOR_PARTS[@]}" "${EDIT_PATHS[@]}"; then
  echo "Editor exited with an error; no changes were applied." >&2
  exit 1
fi

echo "Validating the complete source bundle and generated outputs..."
"$HOST_PYTHON" -m labpulse.deployment \
  --config "$WORK_ROOT/config.yaml" \
  --compose-output "$CHECK_DIR/compose.yaml" \
  --project-dir "$CHECK_DIR" \
  --external-files-dir "$PROJECT_DIR" \
  --ha-config-dir "$CHECK_DIR/homeassistant/config" \
  "${COMPOSE_MODE_ARGS[@]}"

SOURCE_CHANGED=0
if ! cmp -s "$CONFIG_PATH" "$WORK_ROOT/config.yaml"; then
  SOURCE_CHANGED=1
elif [ ! -d "$CONFIG_DIR" ] || ! diff -qr "$CONFIG_DIR" "$WORK_ROOT/config.d" >/dev/null; then
  SOURCE_CHANGED=1
fi
RESOLVED_CHANGED=0
if [ ! -f "$RESOLVED_CONFIG_PATH" ] || \
  ! cmp -s "$RESOLVED_CONFIG_PATH" "$CHECK_DIR/config.resolved.yaml"; then
  RESOLVED_CHANGED=1
fi
if [ "$SOURCE_CHANGED" -eq 0 ] && [ "$RESOLVED_CHANGED" -eq 0 ]; then
  echo "No configuration changes detected; generated runtime is current. Nothing was restarted."
  exit 0
fi

# Keep one complete rolling source rollback rather than independent file copies.
mkdir -p "$BACKUP_DIR"
BACKUP_STAGING="$(mktemp -d "$BACKUP_DIR/.config-source.edit-backup.XXXXXX")"
cp -p "$CONFIG_PATH" "$BACKUP_STAGING/config.yaml"
mkdir -p "$BACKUP_STAGING/config.d"
if [ -d "$CONFIG_DIR" ]; then
  cp -a "$CONFIG_DIR/." "$BACKUP_STAGING/config.d/"
fi
rm -rf -- "$SOURCE_BACKUP"
mv "$BACKUP_STAGING" "$SOURCE_BACKUP"
BACKUP_STAGING=""

install_source_bundle() {
  local source_root="$1"
  cp -p "$source_root/config.yaml" "$CONFIG_PATH"
  rm -rf -- "$CONFIG_DIR"
  mkdir -p "$CONFIG_DIR"
  cp -a "$source_root/config.d/." "$CONFIG_DIR/"
}

generate_live_outputs() {
  "$HOST_PYTHON" -m labpulse.deployment \
    --config "$CONFIG_PATH" \
    --compose-output "$PROJECT_DIR/compose.yaml" \
    --project-dir "$PROJECT_DIR" \
    --external-files-dir "$PROJECT_DIR" \
    --ha-config-dir "$PROJECT_DIR/homeassistant/config" \
    "${COMPOSE_MODE_ARGS[@]}"
}

restore_previous_config() {
  echo "Restoring the previous validated configuration source bundle..." >&2
  install_source_bundle "$SOURCE_BACKUP"
  generate_live_outputs
}

install_source_bundle "$WORK_ROOT"
echo "Generating live runtime configuration and projections..."
if ! generate_live_outputs; then
  restore_previous_config
  exit 1
fi

cd "$PROJECT_DIR"
if ! "${DOCKER_PARTS[@]}" compose config --quiet; then
  echo "Docker Compose rejected the generated configuration." >&2
  restore_previous_config
  exit 1
fi

echo "Checking the generated YAML with Home Assistant..."
if ! RUNNING_SERVICES="$("${DOCKER_PARTS[@]}" compose ps --status running --services)"; then
  echo "Could not inspect the running Compose services." >&2
  restore_previous_config
  exit 1
fi
if grep -qx "homeassistant" <<< "$RUNNING_SERVICES"; then
  HA_CHECK=("${DOCKER_PARTS[@]}" compose exec -T homeassistant)
else
  HA_CHECK=("${DOCKER_PARTS[@]}" compose run --rm --no-deps homeassistant)
fi
if ! "${HA_CHECK[@]}" python -m homeassistant --script check_config --config /config; then
  echo "Home Assistant rejected the generated configuration." >&2
  restore_previous_config
  exit 1
fi

echo "Refreshing LabPulse and Home Assistant..."
if ! "${DOCKER_PARTS[@]}" compose up -d --remove-orphans --force-recreate; then
  echo "Service recreation failed; restoring the previous source bundle." >&2
  restore_previous_config
  "${DOCKER_PARTS[@]}" compose up -d --remove-orphans --force-recreate || true
  exit 1
fi
"${DOCKER_PARTS[@]}" compose ps

RUNTIME_CONFIG="$RESOLVED_CONFIG_PATH"
if [ "$ACTIVE_FAKE_USB" -eq 1 ]; then
  RUNTIME_CONFIG="$FAKE_CONFIG_PATH"
fi
cat <<EOF

Configuration applied successfully.
Master config: $CONFIG_PATH
Measurement config directory: $CONFIG_DIR
Resolved config: $RESOLVED_CONFIG_PATH
Runtime config: $RUNTIME_CONFIG
Source rollback copy: $SOURCE_BACKUP

SAFETY REMINDER
Home Assistant has been refreshed. Check Monitor for "Global Mute Applied" and
"Test Mode Applied", review the new configuration, and only disable either
safeguard when its notification behaviour is ready to resume.
EOF
