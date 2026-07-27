#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=testing/real_hardware/hardware_fault_common.sh
source "$SCRIPT_DIR/hardware_fault_common.sh"

usage() {
  cat <<'EOF'
Usage: ./test_x1200_faults.sh [--service SERVICE] COMMAND

Recreate one real X1200 service with selected container device interfaces
masked by /dev/null. No host device permissions or kernel drivers are changed.

Commands:
  block-i2c   Make the X1200 I2C fuel-gauge interface unavailable
  block-gpio  Make the X1200 mains-detection GPIO interface unavailable
  block-all   Make both X1200 interfaces unavailable
  restore     Recreate the service with its normal generated Compose definition
  status      Show the service status and recent logs

The default service is ups_monitor. Do not run labpulse config/up while a fault
is active; finish the test with this script's restore command.
EOF
}

SERVICE_NAME="ups_monitor"
if [ "${1:-}" = "--service" ]; then
  [ "$#" -ge 3 ] || {
    usage >&2
    exit 2
  }
  SERVICE_NAME="$2"
  shift 2
fi

ACTION="${1:-}"
case "$ACTION" in
  block-i2c|block-gpio|block-all|restore|status) ;;
  -h|--help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

fault_require_live_install
OVERRIDE_FILE="$PROJECT_DIR/.labpulse-x1200-fault.override.yaml"

readarray -t X1200_METADATA < <(
  "$HOST_PYTHON" - "$LIVE_CONFIG" "$COMPOSE_FILE" "$SERVICE_NAME" <<'PY'
from pathlib import Path
import re
import sys
import yaml

config_path = Path(sys.argv[1])
compose_path = Path(sys.argv[2])
service_name = sys.argv[3]

if not re.fullmatch(r"[a-z0-9_]+", service_name):
    raise SystemExit("ERROR: service name must contain lowercase letters, numbers, and underscores")

config = yaml.safe_load(config_path.read_text()) or {}
service = (config.get("services") or {}).get(service_name)
if not isinstance(service, dict) or not service.get("enabled", True):
    raise SystemExit(f"ERROR: enabled service {service_name!r} is not present in {config_path}")

driver = service.get("driver") or {}
if driver.get("type") != "labpulse.x1200":
    raise SystemExit(f"ERROR: service {service_name!r} is not a labpulse.x1200 service")

options = driver.get("options") or {}
bus = int(options.get("bus", 1))
gpio_chip = str(options.get("gpio_chip", "/dev/gpiochip0"))
compose_service = "labpulse-" + re.sub(r"[^a-zA-Z0-9]+", "-", service_name).strip("-").lower()

compose = yaml.safe_load(compose_path.read_text()) or {}
runtime_service = (compose.get("services") or {}).get(compose_service)
if not isinstance(runtime_service, dict):
    raise SystemExit(f"ERROR: {compose_service!r} is missing from {compose_path}")

device_targets = {
    str(item).split(":", 1)[-1]
    for item in runtime_service.get("devices", [])
}
i2c_path = f"/dev/i2c-{bus}"
if i2c_path not in device_targets or gpio_chip not in device_targets:
    raise SystemExit(
        "ERROR: generated Compose does not expose the configured real X1200 devices. "
        "Regenerate the real-hardware installation before running this test."
    )

print(compose_service)
print(i2c_path)
print(gpio_chip)
PY
)

[ "${#X1200_METADATA[@]}" -eq 3 ] ||
  fault_die "Could not resolve the X1200 service and device paths."
COMPOSE_SERVICE="${X1200_METADATA[0]}"
I2C_PATH="${X1200_METADATA[1]}"
GPIO_PATH="${X1200_METADATA[2]}"

case "$ACTION" in
  restore)
    fault_restore_service "$OVERRIDE_FILE" "$COMPOSE_SERVICE"
    ;;
  status)
    fault_show_status "$OVERRIDE_FILE" "$COMPOSE_SERVICE"
    ;;
  block-i2c)
    cat >"$OVERRIDE_FILE" <<EOF
services:
  $COMPOSE_SERVICE:
    devices: !override
      - $GPIO_PATH:$GPIO_PATH
    volumes:
      - type: bind
        source: /dev/null
        target: $I2C_PATH
        read_only: true
EOF
    fault_apply_override "$OVERRIDE_FILE" "$COMPOSE_SERVICE"
    ;;
  block-gpio)
    cat >"$OVERRIDE_FILE" <<EOF
services:
  $COMPOSE_SERVICE:
    devices: !override
      - $I2C_PATH:$I2C_PATH
    volumes:
      - type: bind
        source: /dev/null
        target: $GPIO_PATH
        read_only: true
EOF
    fault_apply_override "$OVERRIDE_FILE" "$COMPOSE_SERVICE"
    ;;
  block-all)
    cat >"$OVERRIDE_FILE" <<EOF
services:
  $COMPOSE_SERVICE:
    devices: !reset []
    volumes:
      - type: bind
        source: /dev/null
        target: $I2C_PATH
        read_only: true
      - type: bind
        source: /dev/null
        target: $GPIO_PATH
        read_only: true
EOF
    fault_apply_override "$OVERRIDE_FILE" "$COMPOSE_SERVICE"
    ;;
esac
