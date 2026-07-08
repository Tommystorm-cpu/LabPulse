#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${LABPULSE_CONTAINER_DIR:-$SCRIPT_DIR}"
CONFIG_PATH="$PROJECT_DIR/config.yaml"
HA_CONFIG_DIR="$PROJECT_DIR/homeassistant/config"
BACKUP_HOMEASSISTANT_UI=0
RESTORE_HOMEASSISTANT_UI=0
FRESH_HOMEASSISTANT=0
REFRESH_DASHBOARD=0

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

if [ "$FRESH_HOMEASSISTANT" -eq 1 ] && [ "$RESTORE_HOMEASSISTANT_UI" -eq 1 ]; then
  echo "ERROR: --fresh-homeassistant and --restore-homeassistant-ui cannot be used together." >&2
  exit 1
fi

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

mkdir -p "$HA_CONFIG_DIR"
backup_homeassistant_ui
restore_homeassistant_ui
fresh_homeassistant_config

python3 - "$CONFIG_PATH" "$HA_CONFIG_DIR" "$FRESH_HOMEASSISTANT" "$REFRESH_DASHBOARD" <<'PY'
from pathlib import Path
import json
import re
import sys

try:
    import yaml
except ImportError:
    print(
        "ERROR: generate_homeassistant_config.sh needs PyYAML on the host.\n"
        "Install it with: sudo apt install python3-yaml",
        file=sys.stderr,
    )
    sys.exit(1)


config_path = Path(sys.argv[1]).expanduser().resolve()
ha_config_dir = Path(sys.argv[2]).expanduser().resolve()
fresh_homeassistant = sys.argv[3] == "1"
refresh_dashboard = sys.argv[4] == "1"
packages_dir = ha_config_dir / "packages"
package_path = packages_dir / "labpulse_thresholds.yaml"
dashboard_cards_path = ha_config_dir / "labpulse_alarm_cards.yaml"
configuration_path = ha_config_dir / "configuration.yaml"
storage_dir = ha_config_dir / ".storage"
lovelace_path = storage_dir / "lovelace"
entity_registry_path = storage_dir / "core.entity_registry"


def slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()


def title(value: str) -> str:
    return slug(value).replace("_", " ").title()


def load_entity_registry() -> tuple[dict[str, str], list[dict]]:
    """Return Home Assistant MQTT entity registry mappings and entries."""

    if not entity_registry_path.exists():
        return {}, []

    try:
        registry = json.loads(entity_registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(
            f"WARNING: Could not parse Home Assistant entity registry: {entity_registry_path}",
            file=sys.stderr,
        )
        return {}, []

    entities = registry.get("data", {}).get("entities", [])
    mappings = {}

    for entity in entities:
        if entity.get("platform") != "mqtt":
            continue

        unique_id = entity.get("unique_id")
        entity_id = entity.get("entity_id")

        if unique_id and entity_id:
            mappings[str(unique_id)] = str(entity_id)

    return mappings, [
        entity
        for entity in entities
        if entity.get("platform") == "mqtt" and entity.get("entity_id")
    ]


def registry_entity_by_candidates(
    unique_id_candidates: list[str],
    suffix_candidates: list[str],
    entity_registry: dict[str, str],
    entity_registry_entries: list[dict],
) -> str | None:
    """Find a Home Assistant entity id from exact unique ids or suffix matches."""

    for unique_id in unique_id_candidates:
        if unique_id in entity_registry:
            return entity_registry[unique_id]

    normalized_suffixes = [slug(candidate) for candidate in suffix_candidates]

    for entity in entity_registry_entries:
        entity_id = str(entity.get("entity_id", ""))
        unique_id = slug(str(entity.get("unique_id", "")))
        entity_slug = slug(entity_id.removeprefix("sensor."))

        if any(unique_id.endswith(candidate) for candidate in normalized_suffixes):
            return entity_id

        if any(entity_slug.endswith(candidate) for candidate in normalized_suffixes):
            return entity_id

    return None


def sensor_entity_id(
    service_name: str,
    service_config: dict,
    metric_name: str,
    metric_key: str,
    entity_registry: dict[str, str],
    entity_registry_entries: list[dict],
) -> str:
    registry_entity = registry_entity_by_candidates(
        unique_id_candidates=[
            f"{service_name}_{metric_key}",
            metric_key,
            f"{service_name}_{metric_name}",
        ],
        suffix_candidates=[
            metric_key,
            f"{service_name}_{metric_name}",
            metric_name,
        ],
        entity_registry=entity_registry,
        entity_registry_entries=entity_registry_entries,
    )

    if registry_entity:
        return registry_entity

    explicit = service_config.get("entity_prefix")
    if explicit:
        prefix = slug(str(explicit))
    else:
        prefix = slug(str(service_config.get("device_name") or service_name))

    return f"sensor.{prefix}_{metric_key}"


def status_entity_id(
    service_name: str,
    service_config: dict,
    entity_registry: dict[str, str],
    entity_registry_entries: list[dict],
) -> str:
    registry_entity = registry_entity_by_candidates(
        unique_id_candidates=[f"{service_name}_status"],
        suffix_candidates=[f"{service_name}_status", "status"],
        entity_registry=entity_registry,
        entity_registry_entries=entity_registry_entries,
    )

    if registry_entity:
        return registry_entity

    prefix = slug(str(service_config.get("device_name") or service_name))
    return f"sensor.{prefix}_status"


def metric_defaults(metric_name: str) -> dict:
    name = slug(metric_name)

    if "temp" in name:
        return {
            "unit": "\u00b0C",
            "mode": "range",
            "min": 5,
            "max": 35,
            "range_min": -20,
            "range_max": 80,
            "step": 0.1,
        }

    if "hum" in name:
        return {
            "unit": "%",
            "mode": "range",
            "min": 20,
            "max": 80,
            "range_min": 0,
            "range_max": 100,
            "step": 1,
        }

    if "flow" in name:
        return {
            "unit": "L/min",
            "mode": "min",
            "min": 1,
            "range_min": 0,
            "range_max": 20,
            "step": 0.1,
        }

    if "press" in name or "pressure" in name:
        return {
            "unit": "bar",
            "mode": "min",
            "min": 1,
            "range_min": 0,
            "range_max": 10,
            "step": 0.1,
        }

    return {
        "unit": "",
        "mode": "min",
        "min": 0,
        "range_min": 0,
        "range_max": 100,
        "step": 1,
    }


def fallback_metrics(service_name: str, service_config: dict) -> list[dict]:
    parser = service_config.get("parser")

    if parser == "pressure":
        return [{"name": "pressure", "label": "Pressure"}]

    if parser == "pump_room":
        return [
            {"name": "flow1", "label": "Flow 1"},
            {"name": "flow2", "label": "Flow 2"},
            {"name": "temp0", "label": "Temp 0"},
            {"name": "temp1", "label": "Temp 1"},
            {"name": "temp2", "label": "Temp 2"},
            {"name": "temp3", "label": "Temp 3"},
        ]

    if parser == "water":
        return [
            {"name": "flow1", "label": "Flow 1"},
            {"name": "flow2", "label": "Flow 2"},
            {"name": "temp0", "label": "Temp 0"},
            {"name": "temp1", "label": "Temp 1"},
            {"name": "temp2", "label": "Temp 2"},
            {"name": "temp3", "label": "Temp 3"},
        ]

    return []


def configured_metrics(service_name: str, service_config: dict) -> list[dict]:
    metrics = service_config.get("metrics")
    if isinstance(metrics, list):
        return [metric for metric in metrics if isinstance(metric, dict) and metric.get("name")]

    return fallback_metrics(service_name, service_config)


def make_threshold_entities(metric_id: str, metric: dict) -> list[tuple[str, dict]]:
    defaults = metric_defaults(metric_id)
    threshold = metric.get("threshold", {}) if isinstance(metric.get("threshold"), dict) else {}
    mode = threshold.get("mode", defaults["mode"])
    entities = []

    if mode in {"min", "range"}:
        entities.append(
            (
                f"labpulse_{metric_id}_minimum_threshold",
                {
                    "name": f"{metric.get('label', title(metric_id))} Minimum Threshold",
                    "min": threshold.get("range_min", defaults["range_min"]),
                    "max": threshold.get("range_max", defaults["range_max"]),
                    "step": threshold.get("step", defaults["step"]),
                    "initial": threshold.get("min", defaults["min"]),
                    "unit_of_measurement": threshold.get("unit", defaults["unit"]),
                    "mode": "box",
                },
            )
        )

    if mode in {"max", "range"}:
        entities.append(
            (
                f"labpulse_{metric_id}_maximum_threshold",
                {
                    "name": f"{metric.get('label', title(metric_id))} Maximum Threshold",
                    "min": threshold.get("range_min", defaults["range_min"]),
                    "max": threshold.get("range_max", defaults["range_max"]),
                    "step": threshold.get("step", defaults["step"]),
                    "initial": threshold.get("max", defaults.get("max", defaults["range_max"])),
                    "unit_of_measurement": threshold.get("unit", defaults["unit"]),
                    "mode": "box",
                },
            )
        )

    return entities


def bad_condition(metric_id: str, mode: str, entity_id: str) -> str:
    current = f"states('{entity_id}') | float(0)"
    min_entity = f"input_number.labpulse_{metric_id}_minimum_threshold"
    max_entity = f"input_number.labpulse_{metric_id}_maximum_threshold"

    if mode == "range":
        return (
            f"{{{{ {current} < states('{min_entity}') | float(0)\n"
            f"   or {current} > states('{max_entity}') | float(0) }}}}"
        )

    if mode == "max":
        return f"{{{{ {current} > states('{max_entity}') | float(0) }}}}"

    return f"{{{{ {current} < states('{min_entity}') | float(0) }}}}"


def good_condition(metric_id: str, mode: str, entity_id: str) -> str:
    current = f"states('{entity_id}') | float(0)"
    min_entity = f"input_number.labpulse_{metric_id}_minimum_threshold"
    max_entity = f"input_number.labpulse_{metric_id}_maximum_threshold"

    if mode == "range":
        return (
            f"{{{{ {current} >= states('{min_entity}') | float(0)\n"
            f"   and {current} <= states('{max_entity}') | float(0) }}}}"
        )

    if mode == "max":
        return f"{{{{ {current} <= states('{max_entity}') | float(0) }}}}"

    return f"{{{{ {current} >= states('{min_entity}') | float(0) }}}}"


def threshold_summary(metric_id: str, mode: str) -> str:
    min_entity = f"input_number.labpulse_{metric_id}_minimum_threshold"
    max_entity = f"input_number.labpulse_{metric_id}_maximum_threshold"

    if mode == "range":
        return (
            f"Min: {{{{ states('{min_entity}') }}}}. "
            f"Max: {{{{ states('{max_entity}') }}}}."
        )

    if mode == "max":
        return f"Max: {{{{ states('{max_entity}') }}}}."

    return f"Min: {{{{ states('{min_entity}') }}}}."


def make_automation(
    alias: str,
    trigger_template: str,
    delay_entity: str,
    active_entity: str,
    active_state: str,
    actions: list[dict],
) -> dict:
    return {
        "alias": alias,
        "mode": "single",
        "trigger": [
            {
                "platform": "template",
                "value_template": trigger_template,
                "for": {"seconds": f"{{{{ states('{delay_entity}') | int(2) }}}}"},
            }
        ],
        "condition": [
            {
                "condition": "state",
                "entity_id": active_entity,
                "state": active_state,
            }
        ],
        "action": actions,
    }


def ensure_configuration_file() -> None:
    ha_config_dir.mkdir(parents=True, exist_ok=True)

    if not configuration_path.exists():
        configuration_path.write_text(
            "homeassistant:\n"
            "  packages: !include_dir_named packages\n"
            "\n"
            "default_config:\n"
            "\n"
            "frontend:\n"
            "\n"
            "history:\n"
            "\n"
            "logbook:\n"
            "\n"
            "my:\n"
            "\n"
            "mobile_app:\n"
            "\n"
            "system_health:\n",
            encoding="utf-8",
        )
        return

    text = configuration_path.read_text(encoding="utf-8")
    additions = []

    # MQTT broker settings are configured through Home Assistant's MQTT
    # integration UI/config entry, not via configuration.yaml.
    text = re.sub(
        r"(?ms)^mqtt:\n  broker: 127\.0\.0\.1\n  port: 1883\n?",
        "",
        text,
    )

    if "!include_dir_named packages" not in text:
        if re.search(r"(?m)^homeassistant:\s*$", text):
            text = re.sub(
                r"(?m)^homeassistant:\s*$",
                "homeassistant:\n  packages: !include_dir_named packages",
                text,
                count=1,
            )
        else:
            additions.append(
                "homeassistant:\n"
                "  packages: !include_dir_named packages\n"
            )

    if additions:
        separator = "\n" if text.endswith("\n") else "\n\n"
        text = text + separator + "\n".join(additions)

    configuration_path.write_text(text, encoding="utf-8")


def tile_card(entity_id: str, columns: str = "full") -> dict:
    return {
        "type": "tile",
        "entity": entity_id,
        "grid_options": {"columns": columns},
    }


def heading_card(heading: str, icon: str) -> dict:
    return {
        "type": "heading",
        "heading": heading,
        "heading_style": "title",
        "icon": icon,
    }


def write_lovelace_dashboard(sections: list[dict]) -> None:
    if lovelace_path.exists() and not fresh_homeassistant and not refresh_dashboard:
        print(f"Preserved existing editable dashboard: {lovelace_path}")
        return

    storage_dir.mkdir(parents=True, exist_ok=True)
    dashboard = {
        "version": 1,
        "minor_version": 1,
        "key": "lovelace",
        "data": {
            "config": {
                "views": [
                    {
                        "title": "LabPulse",
                        "path": "labpulse",
                        "type": "sections",
                        "sections": sections,
                    }
                ]
            }
        },
    }

    lovelace_path.write_text(json.dumps(dashboard, indent=2), encoding="utf-8")


if not config_path.exists():
    print(f"ERROR: config file does not exist: {config_path}", file=sys.stderr)
    sys.exit(1)

data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
services = data.get("services", {})
entity_registry, entity_registry_entries = load_entity_registry()

input_numbers = {}
input_booleans = {}
automations = []
dashboard_cards = []
dashboard_sections = []
system_health_cards = [heading_card("System Health", "mdi:heart-cog")]

for service_name, service_config in services.items():
    service_config = service_config or {}
    if not service_config.get("enabled", True):
        continue

    service_id = slug(service_name)
    service_label = str(service_config.get("device_name") or title(service_name))
    metrics = configured_metrics(service_name, service_config)
    status_entity = status_entity_id(
        service_name,
        service_config,
        entity_registry,
        entity_registry_entries,
    )

    system_health_cards.append(tile_card(status_entity))

    if not metrics:
        continue

    input_numbers[f"labpulse_{service_id}_alert_delay_seconds"] = {
        "name": f"{service_label} Alert Delay",
        "min": 0,
        "max": 300,
        "step": 1,
        "initial": 2,
        "unit_of_measurement": "s",
        "mode": "box",
    }
    input_numbers[f"labpulse_{service_id}_recovery_delay_seconds"] = {
        "name": f"{service_label} Recovery Delay",
        "min": 0,
        "max": 300,
        "step": 1,
        "initial": 2,
        "unit_of_measurement": "s",
        "mode": "box",
    }

    dashboard_entities = [
        {
            "entity": f"input_number.labpulse_{service_id}_alert_delay_seconds",
            "name": "Alert delay",
        },
        {
            "entity": f"input_number.labpulse_{service_id}_recovery_delay_seconds",
            "name": "Recovery delay",
        },
        {"type": "divider"},
    ]

    for metric in metrics:
        metric_name = slug(str(metric["name"]))
        metric_key = f"{service_id}_{metric_name}"
        metric_id = metric_key
        metric_label = str(metric.get("label") or title(metric_name))
        threshold = metric.get("threshold", {}) if isinstance(metric.get("threshold"), dict) else {}
        mode = threshold.get("mode", metric_defaults(metric_name)["mode"])
        entity_id = str(
            metric.get("entity_id")
            or sensor_entity_id(
                service_name,
                service_config,
                metric_name,
                metric_key,
                entity_registry,
                entity_registry_entries,
            )
        )
        active_entity = f"input_boolean.labpulse_{metric_id}_alert_active"

        input_booleans[f"labpulse_{metric_id}_alert_active"] = {
            "name": f"{metric_label} Alert Active",
            "initial": False,
        }

        for helper_id, helper_config in make_threshold_entities(metric_id, metric):
            input_numbers[helper_id] = helper_config

        alert_delay = f"input_number.labpulse_{service_id}_alert_delay_seconds"
        recovery_delay = f"input_number.labpulse_{service_id}_recovery_delay_seconds"

        automations.append(
            make_automation(
                f"LabPulse {metric_label} Alert",
                bad_condition(metric_id, mode, entity_id),
                alert_delay,
                active_entity,
                "off",
                [
                    {
                        "service": "input_boolean.turn_on",
                        "target": {"entity_id": active_entity},
                    },
                    {
                        "service": "persistent_notification.create",
                        "data": {
                            "title": f"LabPulse {metric_label} alert",
                            "message": (
                                f"{metric_label} is outside its threshold.\n\n"
                                f"Current reading: {{{{ states('{entity_id}') }}}}.\n"
                                f"{threshold_summary(metric_id, mode)}"
                            ),
                            "notification_id": f"labpulse_{metric_id}_status",
                        },
                    },
                ],
            )
        )

        automations.append(
            make_automation(
                f"LabPulse {metric_label} Recovery",
                good_condition(metric_id, mode, entity_id),
                recovery_delay,
                active_entity,
                "on",
                [
                    {
                        "service": "input_boolean.turn_off",
                        "target": {"entity_id": active_entity},
                    },
                    {
                        "service": "persistent_notification.create",
                        "data": {
                            "title": f"LabPulse {metric_label} recovered",
                            "message": (
                                f"{metric_label} has recovered.\n\n"
                                f"Current reading: {{{{ states('{entity_id}') }}}}.\n"
                                f"{threshold_summary(metric_id, mode)}"
                            ),
                            "notification_id": f"labpulse_{metric_id}_status",
                        },
                    },
                ],
            )
        )

        dashboard_entities.append({"entity": entity_id, "name": f"{metric_label} current"})

        if mode in {"min", "range"}:
            dashboard_entities.append(
                {
                    "entity": f"input_number.labpulse_{metric_id}_minimum_threshold",
                    "name": f"{metric_label} minimum",
                }
            )

        if mode in {"max", "range"}:
            dashboard_entities.append(
                {
                    "entity": f"input_number.labpulse_{metric_id}_maximum_threshold",
                    "name": f"{metric_label} maximum",
                }
            )

        dashboard_entities.append({"type": "divider"})

    if dashboard_entities and dashboard_entities[-1] == {"type": "divider"}:
        dashboard_entities.pop()

    dashboard_cards.append(
        {
            "type": "entities",
            "title": f"{service_label} Alarm Settings",
            "show_header_toggle": False,
            "entities": dashboard_entities,
        }
    )

    if "pressure" in service_id:
        section_heading = "Air Pressure"
        section_icon = "mdi:gauge"
    elif "turbo" in service_id:
        section_heading = "Cryogenics"
        section_icon = "mdi:snowflake-alert"
    elif "pump" in service_id:
        section_heading = "Pump Room"
        section_icon = "mdi:water-pump"
    else:
        section_heading = service_label
        section_icon = "mdi:chip"

    sensor_cards = [
        heading_card(section_heading, section_icon),
        tile_card(status_entity),
    ]

    for metric in metrics:
        metric_name = slug(str(metric["name"]))
        metric_key = f"{service_id}_{metric_name}"
        entity_id = str(
            metric.get("entity_id")
            or sensor_entity_id(
                service_name,
                service_config,
                metric_name,
                metric_key,
                entity_registry,
                entity_registry_entries,
            )
        )
        sensor_cards.append(tile_card(entity_id))

    sensor_cards.append(
        {
            "type": "entities",
            "title": f"{service_label} Alarm Settings",
            "show_header_toggle": False,
            "entities": dashboard_entities,
            "grid_options": {"columns": "full"},
        }
    )

    dashboard_sections.append({"type": "grid", "cards": sensor_cards})

packages_dir.mkdir(parents=True, exist_ok=True)

package = {
    "input_number": input_numbers,
    "input_boolean": input_booleans,
    "automation": automations,
}

package_path.write_text(yaml.safe_dump(package, sort_keys=False), encoding="utf-8")
dashboard_cards_path.write_text(yaml.safe_dump(dashboard_cards, sort_keys=False), encoding="utf-8")
ensure_configuration_file()
dashboard_sections.insert(0, {"type": "grid", "cards": system_health_cards})
write_lovelace_dashboard(dashboard_sections)

print(f"Generated {package_path}")
print(f"Generated {dashboard_cards_path}")
print(f"Updated {configuration_path}")
print(f"Generated or preserved editable dashboard {lovelace_path}")
PY
