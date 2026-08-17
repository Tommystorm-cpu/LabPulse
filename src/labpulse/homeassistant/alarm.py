"""Render the final Home Assistant alarm package from one template."""

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, pass_context
from jinja2.runtime import Context
import yaml

from labpulse.common.sms_templates import load_sms_templates
from labpulse.common.config import LabPulseConfig, MeasurementConfig
from labpulse.common.identity import entity_id, slug, stable_id
from labpulse.common.mqtt_contracts import SMS_SEND_TOPIC

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "alarm"

THRESHOLD_RANGES = {
    "temp": {"unit": "°C", "range_min": -20, "range_max": 80, "step": 0.1},
    "hum": {"unit": "%", "range_min": 0, "range_max": 100, "step": 1},
    "flow": {"unit": "L/min", "range_min": 0, "range_max": 999, "step": 0.1},
    "pressure": {"unit": "bar", "range_min": 0, "range_max": 999, "step": 0.1},
    "generic": {"unit": "", "range_min": 0, "range_max": 999, "step": 1},
}


def _threshold(measurement: MeasurementConfig) -> dict[str, object]:
    """Return the threshold editor bounds used by Home Assistant."""

    name = slug(measurement.name)
    kind = (
        "temp" if "temp" in name else
        "hum" if "hum" in name else
        "flow" if "flow" in name else
        "pressure" if "press" in name else
        "generic"
    )
    values = dict(THRESHOLD_RANGES[kind])
    values["unit"] = measurement.unit or values["unit"]
    return values


def build_template_context(config: LabPulseConfig) -> dict[str, Any]:
    """Project validated config once into the few relationships templates need."""

    setup_ids = [
        setup_id for setup_id, _setup in sorted(
            config.setups.items(), key=lambda item: (item[1].order, item[0])
        )
    ]
    setup_order = {setup_id: index for index, setup_id in enumerate(setup_ids)}
    by_setup: dict[str, list[dict[str, Any]]] = {key: [] for key in setup_ids}
    services: list[dict[str, Any]] = []
    measurements: list[dict[str, Any]] = []

    for service_name, service_config in config.services.items():
        if not service_config.enabled:
            continue
        service_measurements: list[dict[str, Any]] = []
        for measurement_config in service_config.measurements:
            name = slug(measurement_config.name)
            selected_setups = () if measurement_config.setups is None else tuple(
                sorted(measurement_config.setups.setup_ids, key=setup_order.__getitem__)
            )
            setup_mutes = tuple(
                entity_id("input_boolean", "setup", setup_id, "notifications_muted")
                for setup_id in selected_setups
            )
            checks = " or ".join(
                f"is_state('{mute}', 'off')" for mute in setup_mutes
            )
            labels = [config.setups[key].display_label(key) for key in selected_setups]
            if measurement_config.setups is None:
                notification_context = "Monitoring context: Dedicated power monitoring."
            else:
                prefix = "Affected setup" if len(labels) == 1 else "Affected setups"
                notification_context = f"{prefix}: {', '.join(labels)}."
            measurement = {
                "service_name": service_name,
                "name": name,
                "label": measurement_config.display_label,
                "subcategory": measurement_config.subcategory,
                "device_class": measurement_config.device_class,
                "config": measurement_config,
                "setup_ids": selected_setups,
                "notification_context": notification_context,
                "measurement_id": f"{slug(service_name)}_{name}",
                "setup_notifications_unmuted_template": "{{ " + (checks or "true") + " }}",
                "threshold": _threshold(measurement_config),
            }
            measurements.append(measurement)
            service_measurements.append(measurement)
            for setup_id in selected_setups:
                by_setup[setup_id].append(measurement)

        service_id = slug(service_name)
        service = {
            "name": service_name,
            "label": service_config.device_name,
            "service_id": service_id,
            "config": service_config,
            "health_fault_confirm_seconds": config.service_health.fault_confirm_seconds,
            "health_recovery_confirm_seconds": config.service_health.recovery_confirm_seconds,
            "sensor_fault_confirm_seconds": min(15, service_config.maximum_measurement_age_seconds),
            "measurements": service_measurements,
            "power": None,
        }
        checks = [
            f"not is_number(states('{entity_id('sensor', service_name, item['name'])}'))"
            for item in service_measurements
        ]
        service["all_measurements_invalid_template"] = "(" + " and ".join(checks or ["true"]) + ")"
        service["subordinate_notification_ids"] = [
            f"labpulse_{item['measurement_id']}_status" for item in service_measurements
        ]
        if service_config.power_detection is None:
            service["alarm_state_entities"] = [
                entity_id("input_select", service_name, item["name"], "alarm_state")
                for item in service_measurements
            ]
        else:
            by_name = {item["name"]: item for item in service_measurements}
            service["power"] = {
                "voltage": by_name["voltage"],
                "battery_level": by_name["battery_level"],
                "mains_present": by_name["mains_present"],
                "config": service_config.power_detection,
                "maximum_measurement_age_seconds": service_config.maximum_measurement_age_seconds,
            }
            service["alarm_state_entities"] = [
                entity_id("input_select", service_name, "power", "state")
            ]
        services.append(service)

    setups = []
    for setup_id in setup_ids:
        items = by_setup[setup_id]
        if not items:
            continue
        label = config.setups[setup_id].display_label(setup_id)
        shared_labels = tuple(item["label"] for item in items if len(item["setup_ids"]) > 1)
        muted = entity_id("input_boolean", "setup", setup_id, "notifications_muted")
        setups.append({
            "setup_id": setup_id,
            "label": label,
            "icon": config.setups[setup_id].icon,
            "muted_entity": muted,
            "muted_helper_id": muted.split(".", 1)[1],
            "measurement_count": len(items),
            "shared_measurement_labels": shared_labels,
            "shared_measurement_warning": (
                f"{label} contains measurements shared with other setups: {', '.join(shared_labels)}. "
                "These measurements will remain unmuted while another setup using them "
                "remains unmuted. Continue?"
            ),
            "measurements": items,
            "measurement_groups": _measurement_groups(items),
        })

    alarm_measurements = [
        (service, measurement)
        for service in services if service["power"] is None
        for measurement in service["measurements"]
    ]
    targets = _bulk_targets(config, alarm_measurements, by_setup)
    groups = targets[0]["deadband_groups"] if targets else ()
    active_setups = {setup["setup_id"]: setup for setup in setups}
    monitor_setups = []
    for setup_id in setup_ids:
        if setup_id in active_setups:
            monitor_setups.append(active_setups[setup_id])
            continue
        setup_config = config.setups[setup_id]
        monitor_setups.append({
            "setup_id": setup_id,
            "label": setup_config.display_label(setup_id),
            "icon": setup_config.icon,
            "measurements": (),
            "measurement_groups": (),
        })
    context = {
        "config": config,
        "services": services,
        "setups": tuple(setups),
        "monitor_setups": tuple(monitor_setups),
        "measurements": measurements,
        "alarm_measurements": alarm_measurements,
        "measurements_by_setup": by_setup,
        "sms_send_topic": SMS_SEND_TOPIC,
        "bulk_alarm_targets": targets,
        "bulk_alarm_target_options": [target["option"] for target in targets],
        "bulk_target_counts": {
            target["option"]: len(target["measurement_keys"]) for target in targets
        },
        "bulk_deadband_groups": groups,
    }
    context["bulk_apply_entities"] = (
        entity_id("input_boolean", "bulk", "apply", "required_danger_percent"),
        entity_id("input_boolean", "bulk", "apply", "observation_window_seconds"),
        entity_id("input_boolean", "bulk", "apply", "required_recovery_seconds"),
        *(group["apply_entity"] for group in groups),
    )
    return context


def _measurement_groups(
    measurements: list[dict[str, Any]],
) -> tuple[tuple[str, tuple[dict[str, Any], ...]], ...]:
    """Group one setup's measurements by first-seen subcategory."""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for measurement in measurements:
        grouped.setdefault(measurement["subcategory"] or "Other Measurements", []).append(measurement)
    return tuple((name, tuple(items)) for name, items in grouped.items())


def _bulk_targets(
    config: LabPulseConfig,
    alarm_measurements: list[tuple[dict[str, Any], dict[str, Any]]],
    by_setup: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], ...]:
    """Calculate the genuinely derived bulk target and deadband relationships."""

    by_key = {
        (service["name"], measurement["name"]): measurement
        for service, measurement in alarm_measurements
    }
    projections = [("all", "All measurements", list(by_key.values()))]
    projections.extend(
        (setup_id, f"{config.setups[setup_id].display_label(setup_id)} ({setup_id})", items)
        for setup_id, items in by_setup.items()
    )
    targets = []
    for target_id, option, candidates in projections:
        selected = [
            item for item in candidates
            if (item["service_name"], item["name"]) in by_key
        ]
        if not selected:
            continue
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for item in selected:
            device_class = item["device_class"] or f"measurement:{stable_id(item['service_name'], item['name'])}"
            grouped.setdefault((device_class, item["threshold"]["unit"]), []).append(item)
        deadbands = []
        for (device_class, unit), members in grouped.items():
            if device_class.startswith("measurement:"):
                helper_slug = slug(stable_id(members[0]["service_name"], members[0]["name"]))
                label = members[0]["label"]
            else:
                helper_slug = slug(f"{device_class}_{unit or 'unitless'}")
                label = device_class.replace("_", " ").title()
            range_min = max(0, *(item["threshold"]["range_min"] for item in members))
            range_max = min(item["threshold"]["range_max"] for item in members)
            if range_min > range_max:
                raise ValueError(f"empty deadband range for {device_class} ({unit})")
            deadbands.append({
                "device_class": device_class,
                "label": label,
                "helper_slug": helper_slug,
                "unit": unit,
                "measurement_keys": tuple((item["service_name"], item["name"]) for item in members),
                "recovery_deadband_entities": tuple(
                    entity_id("input_number", item["service_name"], item["name"], "recovery_deadband")
                    for item in members
                ),
                "value_entity": entity_id("input_number", "bulk", "deadband", helper_slug),
                "apply_entity": entity_id("input_boolean", "bulk", "apply", "deadband", helper_slug),
                "range_min": range_min,
                "range_max": range_max,
                "step": max(item["threshold"]["step"] for item in members),
            })
        targets.append({
            "target_id": target_id,
            "option": option,
            "measurement_keys": tuple((item["service_name"], item["name"]) for item in selected),
            "required_danger_percent_entities": tuple(
                entity_id("input_number", item["service_name"], item["name"], "required_danger_percent")
                for item in selected
            ),
            "observation_window_seconds_entities": tuple(
                entity_id("input_number", item["service_name"], item["name"], "observation_window_seconds")
                for item in selected
            ),
            "required_recovery_seconds_entities": tuple(
                entity_id("input_number", item["service_name"], item["name"], "required_recovery_seconds")
                for item in selected
            ),
            "deadband_groups": tuple(deadbands),
        })
    return tuple(targets)

def render_alarm(render_model: dict[str, Any]) -> str:
    """Render and validate the final-shaped Home Assistant alarm template."""

    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        undefined=StrictUndefined,
        autoescape=False,
        block_start_string="[%",
        block_end_string="%]",
        variable_start_string="[[",
        variable_end_string="]]",
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    environment.filters["yaml_scalar"] = _yaml_scalar
    environment.filters["json"] = json.dumps
    environment.globals.update(entity_id=entity_id, stable_id=stable_id, slug=slug)

    @pass_context
    def render_fragment(
        context: Context,
        value: str,
        **explicit: object,
    ) -> str:
        """Render one SMS expression against the active service context."""

        variables = context.get_all()
        variables.update(explicit)
        return environment.from_string(value).render(variables)

    environment.filters["render_fragment"] = render_fragment

    selected_expression = "{{ " + " or ".join(
        f"is_state('{entity}', 'on')"
        for entity in render_model["bulk_apply_entities"]
    ) + " }}"
    target_lines = [
        "{% set selected = states('"
        + entity_id("input_select", "bulk", "alarm", "timing", "target")
        + "') %}"
    ]
    for index, target in enumerate(render_model["bulk_alarm_targets"]):
        keyword = "if" if index == 0 else "elif"
        target_lines.append(
            f"{{% {keyword} selected == {json.dumps(target["option"])} %}}"
            f"{len(target["measurement_keys"])}"
        )
    target_lines.extend(["{% else %}0", "{% endif %}"])
    rendered = environment.get_template("alarm_package.yaml.j2").render(
        model=render_model,
        sms=load_sms_templates(),
        bulk_common_flags=(
            ("Required Danger", entity_id("input_boolean", "bulk", "apply", "required_danger_percent")),
            ("Observation Window", entity_id("input_boolean", "bulk", "apply", "observation_window_seconds")),
            ("Required Recovery", entity_id("input_boolean", "bulk", "apply", "required_recovery_seconds")),
        ),
        bulk_selected_expression=selected_expression,
        bulk_target_count_template="\n".join(target_lines),
    )
    package = yaml.safe_load(rendered)
    if not isinstance(package, dict):
        raise ValueError("rendered Home Assistant alarm package must be a mapping")
    return (
        "# Generated by LabPulse. Edit config.yaml or generator templates.\n"
        + yaml.safe_dump(package, sort_keys=False, allow_unicode=True)
    )


def _yaml_scalar(value: object) -> str:
    """Return one YAML-safe scalar or flow collection without a document marker."""

    dumped = yaml.safe_dump(
        value,
        default_flow_style=True,
        sort_keys=False,
        allow_unicode=True,
    ).strip()
    return dumped.removesuffix("\n...")
