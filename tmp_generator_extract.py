from pathlib import Path
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
packages_dir = ha_config_dir / "packages"
dashboards_dir = ha_config_dir / "dashboards"
package_path = packages_dir / "labpulse_thresholds.yaml"
dashboard_path = dashboards_dir / "labpulse.yaml"
configuration_path = ha_config_dir / "configuration.yaml"


def slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()


def title(value: str) -> str:
    return slug(value).replace("_", " ").title()


def sensor_entity_id(service_name: str, service_config: dict, metric_key: str) -> str:
    explicit = service_config.get("entity_prefix")
    if explicit:
        prefix = slug(str(explicit))
    else:
        prefix = slug(str(service_config.get("device_name") or service_name))
    return f"sensor.{prefix}_{metric_key}"


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
            "lovelace:\n"
            "  dashboards:\n"
            "    labpulse:\n"
            "      mode: yaml\n"
            "      title: LabPulse\n"
            "      icon: mdi:flask\n"
            "      show_in_sidebar: true\n"
            "      filename: dashboards/labpulse.yaml\n",
            encoding="utf-8",
        )
        return

    text = configuration_path.read_text(encoding="utf-8")
    additions = []

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

    if "dashboards/labpulse.yaml" not in text:
        if re.search(r"(?m)^lovelace:\s*$", text):
            print(
                "NOTICE: configuration.yaml already has a lovelace: section; "
                "not editing it automatically. Add dashboards/labpulse.yaml there if needed.",
                file=sys.stderr,
            )
        else:
            additions.append(
                "lovelace:\n"
                "  dashboards:\n"
                "    labpulse:\n"
                "      mode: yaml\n"
                "      title: LabPulse\n"
                "      icon: mdi:flask\n"
                "      show_in_sidebar: true\n"
                "      filename: dashboards/labpulse.yaml\n"
            )

    if additions:
        separator = "\n" if text.endswith("\n") else "\n\n"
        text = text + separator + "\n".join(additions)

    configuration_path.write_text(text, encoding="utf-8")


if not config_path.exists():
    print(f"ERROR: config file does not exist: {config_path}", file=sys.stderr)
    sys.exit(1)

data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
services = data.get("services", {})

input_numbers = {}
input_booleans = {}
automations = []
dashboard_sections = []

for service_name, service_config in services.items():
    service_config = service_config or {}
    if not service_config.get("enabled", True):
        continue

    service_id = slug(service_name)
    service_label = str(service_config.get("device_name") or title(service_name))
    metrics = configured_metrics(service_name, service_config)

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
        entity_id = str(metric.get("entity_id") or sensor_entity_id(service_name, service_config, metric_key))
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

    dashboard_sections.append(
        {
            "type": "grid",
            "cards": [
                {
                    "type": "heading",
                    "heading": f"{service_label} Alarms",
                    "heading_style": "title",
                    "icon": "mdi:alarm-light-outline",
                },
                {
                    "type": "entities",
                    "title": f"{service_label} Alarm Settings",
                    "show_header_toggle": False,
                    "entities": dashboard_entities,
                    "grid_options": {"columns": "full"},
                },
            ],
        }
    )

packages_dir.mkdir(parents=True, exist_ok=True)
dashboards_dir.mkdir(parents=True, exist_ok=True)

package = {
    "input_number": input_numbers,
    "input_boolean": input_booleans,
    "automation": automations,
}

dashboard = {
    "title": "LabPulse",
    "views": [
        {
            "title": "Alarms",
            "path": "alarms",
            "type": "sections",
            "sections": dashboard_sections,
        }
    ],
}

package_path.write_text(yaml.safe_dump(package, sort_keys=False), encoding="utf-8")
dashboard_path.write_text(yaml.safe_dump(dashboard, sort_keys=False), encoding="utf-8")
ensure_configuration_file()

print(f"Generated {package_path}")
print(f"Generated {dashboard_path}")
print(f"Updated {configuration_path}")