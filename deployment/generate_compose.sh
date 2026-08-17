#!/usr/bin/env bash
set -euo pipefail

# Thin packaged launcher for the authoritative Python configuration/generation
# pipeline. The live copy belongs in ~/labpulse-live.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${LABPULSE_LIVE_DIR:-$SCRIPT_DIR}"
CONFIG_PATH=""
OUTPUT_PATH=""
FAKE_USB=0

usage() {
  cat <<'EOF'
Usage: ./generate_compose.sh [options]

Generates Compose from the validated live LabPulse configuration.

Options:
  --config PATH       Config YAML to read. Default: PROJECT_DIR/config.yaml
  --output PATH       Compose YAML to write. Default: PROJECT_DIR/compose.yaml
  --project-dir PATH  LabPulse container folder. Default: script directory
  -fake_usb           Force pseudo-serial simulator mounts.
  -h, --help          Show this help text.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --config)
      CONFIG_PATH="$2"
      shift 2
      ;;
    --output)
      OUTPUT_PATH="$2"
      shift 2
      ;;
    --project-dir)
      PROJECT_DIR="$2"
      shift 2
      ;;
    -fake_usb|--fake-usb|--fake_usb)
      FAKE_USB=1
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

CONFIG_PATH="${CONFIG_PATH:-$PROJECT_DIR/config.yaml}"
OUTPUT_PATH="${OUTPUT_PATH:-$PROJECT_DIR/compose.yaml}"
HOST_PYTHON="${LABPULSE_PYTHON:-$PROJECT_DIR/.venv/bin/python}"
if [ ! -x "$HOST_PYTHON" ]; then
  echo "ERROR: LabPulse's managed Python environment is missing: $HOST_PYTHON" >&2
  echo "Run 'labpulse setup' to restore the managed environment." >&2
  exit 1
fi

ARGS=(
  --config "$CONFIG_PATH"
  --output "$OUTPUT_PATH"
  --project-dir "$PROJECT_DIR"
)
if [ "$FAKE_USB" -eq 1 ]; then
  ARGS+=(--fake-usb)
fi

"$HOST_PYTHON" -m labpulse.deployment "${ARGS[@]}"
