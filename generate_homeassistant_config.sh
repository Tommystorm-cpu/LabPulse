#!/usr/bin/env bash
set -euo pipefail

# Generate supported Home Assistant YAML from the live LabPulse configuration.
# This wrapper never reads or writes Home Assistant's private state directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${LABPULSE_LIVE_DIR:-$SCRIPT_DIR}"
CONFIG_PATH="$PROJECT_DIR/config.yaml"
HA_CONFIG_DIR="$PROJECT_DIR/homeassistant/config"

usage() {
  cat <<'EOF'
Usage: ./generate_homeassistant_config.sh [options]

Generates Home Assistant config from the live config.yaml.

Options:
  --config PATH                 Config YAML to read. Default: ./config.yaml
  --ha-config-dir DIR           Home Assistant config folder. Default: ./homeassistant/config
  --project-dir DIR             LabPulse container folder. Default: script directory
  -h, --help                    Show this help text.

Generated files:
  homeassistant/config/configuration.yaml
  homeassistant/config/packages/labpulse_generated.yaml
  homeassistant/config/labpulse-dashboard.yaml

Generation is offline and uses deterministic entity IDs.
EOF
}

require_value() {
  local option="$1"
  local value="${2:-}"
  if [ -z "$value" ]; then
    echo "ERROR: $option requires a value." >&2
    usage >&2
    exit 1
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --config)
      require_value "$1" "${2:-}"
      CONFIG_PATH="$2"
      shift 2
      ;;
    --ha-config-dir)
      require_value "$1" "${2:-}"
      HA_CONFIG_DIR="$2"
      shift 2
      ;;
    --project-dir)
      require_value "$1" "${2:-}"
      PROJECT_DIR="$2"
      if [ "$CONFIG_PATH" = "$SCRIPT_DIR/config.yaml" ]; then
        CONFIG_PATH="$PROJECT_DIR/config.yaml"
      fi
      if [ "$HA_CONFIG_DIR" = "$SCRIPT_DIR/homeassistant/config" ]; then
        HA_CONFIG_DIR="$PROJECT_DIR/homeassistant/config"
      fi
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

check_homeassistant_config_writable() {
  local package_dir="$HA_CONFIG_DIR/packages"
  local package_file="$package_dir/labpulse_generated.yaml"

  mkdir -p "$package_dir"
  if [ -e "$package_file" ] && [ ! -w "$package_file" ]; then
    echo "ERROR: Cannot write generated Home Assistant file: $package_file" >&2
    echo "Fix the ownership of the LabPulse project directory, then rerun." >&2
    exit 1
  fi
  if [ ! -w "$package_dir" ]; then
    echo "ERROR: Cannot write Home Assistant package directory: $package_dir" >&2
    echo "Fix the ownership of the LabPulse project directory, then rerun." >&2
    exit 1
  fi
}

mkdir -p "$HA_CONFIG_DIR"
check_homeassistant_config_writable

if [ -d "$SCRIPT_DIR/src/labpulse" ]; then
  PYTHON_PACKAGE_DIR="$SCRIPT_DIR/src"
else
  PYTHON_PACKAGE_DIR="$SCRIPT_DIR/labpulse-python"
fi

GENERATOR_PACKAGE="$PYTHON_PACKAGE_DIR/labpulse/homeassistant"
if [ ! -f "$GENERATOR_PACKAGE/__main__.py" ]; then
  echo "ERROR: Home Assistant Python generator package not found: $GENERATOR_PACKAGE" >&2
  exit 1
fi

HOST_PYTHON="${LABPULSE_PYTHON:-$PROJECT_DIR/.venv/bin/python}"
if [ ! -x "$HOST_PYTHON" ]; then
  echo "ERROR: LabPulse's managed Python environment is missing: $HOST_PYTHON" >&2
  echo "Run setup_container_fs.sh from the LabPulse repository." >&2
  exit 1
fi

PYTHONPATH="$PYTHON_PACKAGE_DIR${PYTHONPATH:+:$PYTHONPATH}" \
  "$HOST_PYTHON" -m labpulse.homeassistant \
  "$CONFIG_PATH" "$HA_CONFIG_DIR"
