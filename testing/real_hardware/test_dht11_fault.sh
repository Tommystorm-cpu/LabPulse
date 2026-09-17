#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=testing/real_hardware/hardware_fault_common.sh
source "$SCRIPT_DIR/hardware_fault_common.sh"

usage() {
  cat <<'EOF'
Usage: ./test_dht11_fault.sh [--service SERVICE] COMMAND

Recreate one real DHT11 service with a deliberately unavailable test pin. This
exercises the driver/service fault lifecycle without touching the live GPIO
line or requiring live rewiring.

Commands:
  block    Block GPIO access and recreate the DHT11 service
  restore  Recreate the service with its normal generated Compose definition
  status   Show the service status and recent logs

The default service is room_environment. Do not run labpulse config/up while a
fault is active; finish the test with this script's restore command.
EOF
}

SERVICE_NAME="room_environment"
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
  block|restore|status) ;;
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
OVERRIDE_FILE="$PROJECT_DIR/.labpulse-dht11-fault.override.yaml"
FAULT_CONFIG="$PROJECT_DIR/.labpulse-dht11-fault.config.yaml"

readarray -t DHT11_METADATA < <(
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
if driver.get("type") != "labpulse.dht11":
    raise SystemExit(f"ERROR: service {service_name!r} is not a labpulse.dht11 service")

compose_service = "labpulse-" + re.sub(r"[^a-zA-Z0-9]+", "-", service_name).strip("-").lower()
compose = yaml.safe_load(compose_path.read_text()) or {}
runtime_service = (compose.get("services") or {}).get(compose_service)
if not isinstance(runtime_service, dict):
    raise SystemExit(f"ERROR: {compose_service!r} is missing from {compose_path}")

volumes = {str(item) for item in runtime_service.get("volumes", [])}
if runtime_service.get("privileged") is not True or "/dev:/dev" not in volumes:
    raise SystemExit(
        "ERROR: generated Compose does not describe a real DHT11 container. "
        "Regenerate the real-hardware installation before running this test."
    )

print(compose_service)
PY
)

[ "${#DHT11_METADATA[@]}" -eq 1 ] ||
  fault_die "Could not resolve the DHT11 service."
COMPOSE_SERVICE="${DHT11_METADATA[0]}"

case "$ACTION" in
  restore)
    fault_restore_service "$OVERRIDE_FILE" "$COMPOSE_SERVICE" 5
    rm -f "$FAULT_CONFIG"
    ;;
  status)
    if [ -f "$FAULT_CONFIG" ]; then
      echo "Fault configuration present: $FAULT_CONFIG"
    else
      echo "No DHT11 fault configuration is present."
    fi
    echo
    fault_show_status "$OVERRIDE_FILE" "$COMPOSE_SERVICE"
    ;;
  block)
    "$HOST_PYTHON" - "$LIVE_CONFIG" "$FAULT_CONFIG" "$SERVICE_NAME" <<'PY'
from pathlib import Path
import sys
import yaml

source_path = Path(sys.argv[1])
fault_path = Path(sys.argv[2])
service_name = sys.argv[3]
config = yaml.safe_load(source_path.read_text()) or {}
service = config["services"][service_name]

# Select a syntactically valid Blinka pin name that cannot exist. The DHT11
# driver then raises DriverUnavailable before constructing PulseIn or changing
# the real GPIO line.
service["driver"]["options"]["pin"] = "D999999"
fault_path.write_text(yaml.safe_dump(config, sort_keys=False))
PY

    cat >"$OVERRIDE_FILE" <<EOF
services:
  $COMPOSE_SERVICE:
    privileged: false
    volumes:
      - type: bind
        source: $FAULT_CONFIG
        target: /app/config.yaml
        read_only: true
EOF

    fault_apply_override "$OVERRIDE_FILE" "$COMPOSE_SERVICE"
    ;;
esac
