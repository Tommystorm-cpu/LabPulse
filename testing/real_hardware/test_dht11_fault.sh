#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=testing/real_hardware/hardware_fault_common.sh
source "$SCRIPT_DIR/hardware_fault_common.sh"

usage() {
  cat <<'EOF'
Usage: ./test_dht11_fault.sh [--service SERVICE] COMMAND

Recreate one real DHT11 service without usable GPIO device interfaces. GPIO
devices are masked only inside that container; no live rewiring is required.

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
    fault_restore_service "$OVERRIDE_FILE" "$COMPOSE_SERVICE"
    ;;
  status)
    fault_show_status "$OVERRIDE_FILE" "$COMPOSE_SERVICE"
    ;;
  block)
    GPIO_MASKS=()
    while IFS= read -r gpio_path; do
      [ -n "$gpio_path" ] && GPIO_MASKS+=("$gpio_path")
    done < <(
      {
        find /dev -maxdepth 1 -type c -name 'gpiochip*' -print 2>/dev/null || true
        [ ! -e /dev/gpiomem ] || echo /dev/gpiomem
        [ ! -e /dev/mem ] || echo /dev/mem
      } | sort -u
    )
    [ "${#GPIO_MASKS[@]}" -gt 0 ] ||
      fault_die "No GPIO device interfaces were found under /dev."

    {
      echo "services:"
      echo "  $COMPOSE_SERVICE:"
      echo "    privileged: false"
      echo "    volumes:"
      for gpio_path in "${GPIO_MASKS[@]}"; do
        cat <<EOF
      - type: bind
        source: /dev/null
        target: $gpio_path
        read_only: true
EOF
      done
    } >"$OVERRIDE_FILE"

    fault_apply_override "$OVERRIDE_FILE" "$COMPOSE_SERVICE"
    ;;
esac
