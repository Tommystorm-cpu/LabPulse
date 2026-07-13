#!/usr/bin/env bash
set -euo pipefail

# Generate compose.yaml from the live LabPulse config. This script is copied
# into ~/labpulse-ha and should be rerun there after config.yaml changes.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${LABPULSE_CONTAINER_DIR:-$SCRIPT_DIR}"
CONFIG_PATH="$PROJECT_DIR/config.yaml"
OUTPUT_PATH="$PROJECT_DIR/compose.yaml"
OUTPUT_SET=0
CONFIG_SET=0
FAKE_USB=0

# Print usage from one place so help text and invalid-option errors match.
usage() {
  cat <<'EOF'
Usage: ./generate_compose.sh [options]

Generates a Docker Compose file from the live LabPulse config.yaml.
Each enabled service in config.yaml becomes its own Python container.

Options:
  --config PATH       Config YAML to read. Default: ./config.yaml
  --output PATH       Compose YAML to write. Default: ./compose.yaml
  --project-dir PATH  LabPulse container folder. Default: script directory
  -fake_usb           Force socat fake USB serial mounts.
  -h, --help          Show this help text.

Service config:
  services:
    pump_room:
      enabled: true   # optional, defaults to true
      driver: serial
      ...
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --config)
      CONFIG_PATH="$2"
      CONFIG_SET=1
      shift 2
      ;;
    --output)
      OUTPUT_PATH="$2"
      OUTPUT_SET=1
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

# Resolve default paths after parsing options so --project-dir can change them.
if [ "$OUTPUT_SET" -eq 0 ]; then
  OUTPUT_PATH="$PROJECT_DIR/compose.yaml"
fi

if [ "$CONFIG_SET" -eq 0 ]; then
  CONFIG_PATH="$PROJECT_DIR/config.yaml"
fi

mkdir -p "$(dirname "$OUTPUT_PATH")"

# Use Python for the YAML/config logic. Bash is kept for CLI plumbing; Python is
# safer for parsing config.yaml and emitting predictable Compose YAML.
python3 - "$CONFIG_PATH" "$OUTPUT_PATH" "$PROJECT_DIR" "$FAKE_USB" <<'PY'
from pathlib import Path
import json
import re
import sys

try:
    import yaml
except ImportError:
    print(
        "ERROR: generate_compose.sh needs PyYAML on the host.\n"
        "Install it with: sudo apt install python3-yaml",
        file=sys.stderr,
    )
    sys.exit(1)


config_path = Path(sys.argv[1]).expanduser().resolve()
output_path = Path(sys.argv[2]).expanduser().resolve()
project_dir = Path(sys.argv[3]).expanduser().resolve()
fake_usb = sys.argv[4] == "1"


def service_slug(service_name: str) -> str:
    """Convert a service key into a Docker/Compose-friendly slug."""

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", service_name).strip("-").lower()
    return slug or "service"


def quoted_command(service_name: str) -> str:
    """Serialize the command as JSON so Compose receives clean list syntax."""

    command = ["python", "-m", "labpulse_hardware", "--service", service_name]
    return json.dumps(command)


def sms_command() -> str:
    """Serialize the SMS service command as JSON."""

    command = ["python", "-m", "labpulse_sms", "--config", "/app/config.yaml"]
    return json.dumps(command)


if not config_path.exists():
    print(f"ERROR: config file does not exist: {config_path}", file=sys.stderr)
    sys.exit(1)

data = yaml.safe_load(config_path.read_text()) or {}
services = data.get("services", {})
sms_config = data.get("sms", {}) or {}
sms_backend = str(sms_config.get("backend", "log")).lower()
sms_needs_modem = sms_backend == "mmcli"

enabled_services = [
    service_name
    for service_name, service_config in services.items()
    if service_config is None or service_config.get("enabled", True)
]

if not enabled_services:
    print("ERROR: config.yaml has no enabled services under services:", file=sys.stderr)
    sys.exit(1)

# Fake USB mode can be requested explicitly, or inferred from config.yaml when
# any enabled service points at /tmp/labpulse-fake-serial.
if not fake_usb:
    fake_usb = any(
        str((services.get(service_name) or {}).get("serial_port", "")).startswith(
            "/tmp/labpulse-fake-serial"
        )
        or str((services.get(service_name) or {}).get("fake_state_file", "")).startswith(
            "/tmp/labpulse-fake-dht11"
        )
        for service_name in enabled_services
    )

project_dir.mkdir(parents=True, exist_ok=True)
(project_dir / "logs").mkdir(parents=True, exist_ok=True)

# Shared mounts for every LabPulse Python service.
device_mounts = ["      - ./logs:/app/logs"]
device_mounts.append("      - ./config.yaml:/app/config.yaml:ro")

if fake_usb:
    # Simulator mode exposes fake serial links, fake DHT state, and /dev/pts.
    device_mounts.extend(
        [
            "      - /tmp/labpulse-fake-serial:/tmp/labpulse-fake-serial",
            "      - /tmp/labpulse-fake-dht11:/tmp/labpulse-fake-dht11",
            "      - /dev/pts:/dev/pts",
        ]
    )
else:
    # Real hardware mode exposes /dev so /dev/serial/by-id paths work inside
    # the containers. The base service also gets privileged: true below.
    device_mounts.append("      - /dev:/dev")

# Build the output line-by-line because this file is generated and should be
# simple to inspect on the Pi.
lines = [
    "# Generated by generate_compose.sh",
    "# Edit ./config.yaml in this Compose folder, then regenerate this file.",
    "# Do not edit this file by hand.",
    "",
    "x-labpulse-python-base: &labpulse-python-base",
    "  build: ./labpulse-python",
    "  depends_on:",
    "    - mosquitto",
    "  volumes:",
    *device_mounts,
]

if not fake_usb:
    lines.append("  privileged: true")

sms_service_lines = [
    "  labpulse-sms:",
]

if sms_needs_modem:
    sms_service_lines.extend(
        [
            "    build: ./labpulse-python",
            "    depends_on:",
            "      - mosquitto",
            "    volumes:",
            "      - ./logs:/app/logs",
            "      - ./config.yaml:/app/config.yaml:ro",
            "      - /run/dbus:/run/dbus:ro",
            "      - /dev:/dev",
            "    privileged: true",
            "    environment:",
            "      MQTT_BROKER: mosquitto",
            "      MQTT_PORT: 1883",
            "      LABPULSE_LOG_DIR: /app/logs",
            "    restart: unless-stopped",
            "    container_name: labpulse-sms",
            f"    command: {sms_command()}",
            "",
        ]
    )
else:
    sms_service_lines.extend(
        [
            "    <<: *labpulse-python-base",
            "    container_name: labpulse-sms",
            f"    command: {sms_command()}",
            "",
        ]
    )

# Home Assistant uses host networking so its MQTT integration can connect to
# Mosquitto at 127.0.0.1:1883. Python containers use the Compose service name.
lines.extend(
    [
        "  environment:",
        "    MQTT_BROKER: mosquitto",
        "    MQTT_PORT: 1883",
        "    LABPULSE_LOG_DIR: /app/logs",
        "  restart: unless-stopped",
        "",
        "services:",
        "  homeassistant:",
        "    container_name: labpulse-homeassistant",
        "    image: ghcr.io/home-assistant/home-assistant:stable",
        "    volumes:",
        "      - ./homeassistant/config:/config",
        "      - /etc/localtime:/etc/localtime:ro",
        "      - /run/dbus:/run/dbus:ro",
        "    restart: unless-stopped",
        "    privileged: true",
        "    network_mode: host",
        "    environment:",
        "      TZ: Europe/London",
        "",
        "  mosquitto:",
        "    container_name: labpulse-mqtt",
        "    image: eclipse-mosquitto:2",
        "    ports:",
        '      - "1883:1883"',
        "    volumes:",
        "      - ./mosquitto/config:/mosquitto/config",
        "      - ./mosquitto/data:/mosquitto/data",
        "      - ./mosquitto/log:/mosquitto/log",
        "    restart: unless-stopped",
        "",
        *sms_service_lines,
    ]
)

used_container_names = set()

# Each enabled service becomes one Python container. This keeps hub failures and
# restarts isolated.
for service_name in enabled_services:
    slug = service_slug(service_name)
    container_name = f"labpulse-{slug}"

    if container_name in used_container_names:
        print(
            f"ERROR: service name '{service_name}' creates duplicate container "
            f"name '{container_name}'",
            file=sys.stderr,
        )
        sys.exit(1)

    used_container_names.add(container_name)

    lines.extend(
        [
            f"  {container_name}:",
            "    <<: *labpulse-python-base",
            f"    container_name: {container_name}",
            f"    command: {quoted_command(service_name)}",
            "",
        ]
    )

output_path.write_text("\n".join(lines), encoding="utf-8")

print(f"Generated {output_path}")
print("LabPulse service containers:")
for service_name in enabled_services:
    print(f"  labpulse-{service_slug(service_name)} -> {service_name}")
PY
