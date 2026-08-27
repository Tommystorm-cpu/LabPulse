"""Render the final Home Assistant alarm package from one template."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, pass_context
from jinja2.runtime import Context
import yaml

from labpulse.common.sms_templates import load_sms_templates
from labpulse.common.config import (
    CustomMeasurementConfig,
    LabPulseConfig,
    MeasurementConfig,
)
from labpulse.common.formula import compile_formula
from labpulse.common.identity import entity_id, slug, stable_id
from labpulse.common.mqtt_contracts import SMS_SEND_TOPIC

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "alarm"

# These are editor limits rather than validation limits. They keep Home
# Assistant controls useful while still allowing an explicitly configured unit
# to replace the familiar default for a measurement type.
THRESHOLD_RANGES = {
    "temp": {"unit": "°C", "range_min": -20, "range_max": 80, "step": 0.1},
    "hum": {"unit": "%", "range_min": 0, "range_max": 100, "step": 1},
    "flow": {"unit": "L/min", "range_min": 0, "range_max": 999, "step": 0.1},
    "pressure": {"unit": "bar", "range_min": 0, "range_max": 999, "step": 0.1},
    "generic": {"unit": "", "range_min": 0, "range_max": 999, "step": 1},
}


@dataclass(frozen=True)
class HomeAssistantRenderModel:
    """All data made available to the Home Assistant templates.

    Measurements, services, setups, and group-editing targets contain different
    fields, so their inner records remain dictionaries. This one top-level
    class still gives the templates a clear list of everything they can use,
    without adding a separate class for every small piece of generated YAML.
    """

    services: tuple[dict[str, Any], ...]
    dashboards: tuple[dict[str, Any], ...]
    setups: tuple[dict[str, Any], ...]
    monitor_setups: tuple[dict[str, Any], ...]
    custom_measurements: tuple[dict[str, Any], ...]
    custom_alarm_services: tuple[dict[str, Any], ...]
    alarm_measurements: tuple[tuple[dict[str, Any], dict[str, Any]], ...]
    power_alarm_services: tuple[dict[str, Any], ...]
    sms_send_topic: str
    bulk_alarm_targets: tuple[dict[str, Any], ...]
    bulk_alarm_target_options: tuple[str, ...]
    bulk_target_counts: dict[str, int]
    bulk_deadband_groups: tuple[dict[str, Any], ...]
    bulk_apply_entities: tuple[str, ...]


def _threshold(name: str, measurement: MeasurementConfig | CustomMeasurementConfig) -> dict[str, object]:
    """Return the threshold editor bounds used by Home Assistant."""

    # Measurement names are the only reliable hint available here. Device class
    # is optional and custom installations are allowed to omit it.
    name = slug(name)
    if "temp" in name:
        kind = "temp"
    elif "hum" in name:
        kind = "hum"
    elif "flow" in name:
        kind = "flow"
    elif "press" in name:
        kind = "pressure"
    else:
        kind = "generic"
    values = dict(THRESHOLD_RANGES[kind])
    values["unit"] = measurement.unit or values["unit"]
    return values


def build_template_context(config: LabPulseConfig) -> HomeAssistantRenderModel:
    """Build all values used by the Home Assistant templates."""

    # Sort once and reuse the same order everywhere. Otherwise a setup can move
    # between the monitor, alarm editor, and notification text after a render.
    setup_ids = sorted(config.setups, key=lambda setup_id: (config.setups[setup_id].order, setup_id))
    setup_order = {setup_id: index for index, setup_id in enumerate(setup_ids)}
    measurements_by_setup: dict[str, list[dict[str, Any]]] = {key: [] for key in setup_ids}
    alarmed_measurements_by_setup: dict[str, list[dict[str, Any]]] = {key: [] for key in setup_ids}
    services: list[dict[str, Any]] = []

    # Physical services and measurements
    for service_name, service_config in config.services.items():
        if not service_config.enabled:
            continue
        # Build each measurement once, then reuse it everywhere. This keeps its
        # name and entity ID the same on every page and in every alarm.
        service_measurements: list[dict[str, Any]] = []
        for measurement_name, measurement_config in service_config.measurements.items():
            name = slug(measurement_name)
            selected_setups = () if measurement_config.setups is None else tuple(
                sorted(measurement_config.setups, key=setup_order.__getitem__)
            )
            # A shared measurement stays audible while any affected setup is
            # unmuted. Muting one setup must not hide a fault from another lab.
            setup_mutes = tuple(
                entity_id("input_boolean", "setup", setup_id, "notifications_muted")
                for setup_id in selected_setups
            )
            checks = " or ".join(
                f"is_state('{mute}', 'off')" for mute in setup_mutes
            )
            labels = [config.setups[key].display_label(key) for key in selected_setups]
            if measurement_config.setups is None:
                # Power monitoring covers the whole installation, so it is not
                # assigned to one lab setup.
                notification_context = "Monitoring context: Dedicated power monitoring."
            else:
                prefix = "Affected setup" if len(labels) == 1 else "Affected setups"
                notification_context = f"{prefix}: {', '.join(labels)}."
            measurement = {
                "service_name": service_name,
                "name": name,
                "label": measurement_config.display_label(measurement_name),
                "short_label": measurement_config.display_short_label(measurement_name),
                "group": measurement_config.group,
                "device_class": measurement_config.device_class,
                "alarmed": measurement_config.alarmed,
                "config": measurement_config,
                "setup_ids": selected_setups,
                "notification_context": notification_context,
                "measurement_id": f"{slug(service_name)}_{name}",
                "entity_id": entity_id("sensor", service_name, name),
                "setup_notifications_unmuted_template": "{{ " + (checks or "true") + " }}",
                "threshold": _threshold(measurement_name, measurement_config),
            }
            service_measurements.append(measurement)
            for setup_id in selected_setups:
                measurements_by_setup[setup_id].append(measurement)
                if measurement_config.alarmed:
                    alarmed_measurements_by_setup[setup_id].append(measurement)

        service_id = slug(service_name)
        service = {
            "name": service_name,
            "label": service_config.label,
            "service_id": service_id,
            "config": service_config,
            "health_fault_confirm_seconds": config.service_health.fault_confirm_seconds,
            "health_recovery_confirm_seconds": config.service_health.recovery_confirm_seconds,
            "sensor_fault_confirm_seconds": min(15, service_config.maximum_measurement_age_seconds),
            "measurements": service_measurements,
            "power": None,
        }
        # Service health is separate from individual sensor health. This
        # template tells Home Assistant when every reading from a live process
        # is unusable, which is a stronger signal than one bad measurement.
        checks = [
            f"not is_number(states('{entity_id('sensor', service_name, item['name'])}'))"
            for item in service_measurements
        ]
        service["all_measurements_invalid_template"] = "(" + " and ".join(checks or ["true"]) + ")"
        if service_config.power_detection is None:
            alarmed_measurements = [
                item for item in service_measurements if item["alarmed"]
            ]
            service["subordinate_notification_ids"] = [
                f"labpulse_{item['measurement_id']}_status"
                for item in alarmed_measurements
            ]
            service["alarm_state_entities"] = [
                entity_id("input_select", service_name, item["name"], "alarm_state")
                for item in alarmed_measurements
            ]
        else:
            # Voltage, battery level, and mains presence describe one power
            # event. Separate alarms could send conflicting messages.
            by_name = {item["name"]: item for item in service_measurements}
            service["power"] = {
                "voltage": by_name["voltage"],
                "battery_level": by_name["battery_level"],
                "mains_present": by_name["mains_present"],
                "config": service_config.power_detection,
                "maximum_measurement_age_seconds": service_config.maximum_measurement_age_seconds,
                "alarmed": all(item["alarmed"] for item in service_measurements),
            }
            if service["power"]["alarmed"]:
                service["subordinate_notification_ids"] = [f"labpulse_{service_id}_power"]
                service["alarm_state_entities"] = [entity_id("input_select", service_name, "power", "state")]
            else:
                service["subordinate_notification_ids"] = []
                service["alarm_state_entities"] = []
        services.append(service)

    # Home Assistant-calculated measurements
    custom_measurements: list[dict[str, Any]] = []
    custom_alarm_services: list[dict[str, Any]] = []
    custom_alarm_measurements: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for custom_id, custom_config in config.custom_measurements.items():
        compiled = compile_formula(custom_config.formula, set(custom_config.inputs) | set(custom_config.constants))
        source_entities = {
            alias: entity_id("sensor", *reference.split(".", 1))
            for alias, reference in custom_config.inputs.items()
        }
        assignments = [
            f"{{% set {alias} = states('{source}') | float(0) %}}"
            for alias, source in source_entities.items()
        ]
        assignments.extend(f"{{% set {name} = {value!r} %}}" for name, value in custom_config.constants.items())
        numeric_checks = [f"is_number(states('{source}'))" for source in source_entities.values()]
        divisor_checks = [f"(({divisor}) | float(0)) != 0" for divisor in compiled.divisors]
        output_entity = entity_id("sensor", "custom", custom_id)
        availability_template = "\n".join(
            [*assignments, "{{ " + " and ".join([*numeric_checks, *divisor_checks] or ["true"]) + " }}"]
        )
        safe_expression = "(" + compiled.expression + f") | round({custom_config.precision})"
        if divisor_checks:
            safe_expression = (
                f"({safe_expression}) if " + " and ".join(divisor_checks) + " else none"
            )
        state_template = "\n".join([*assignments, "{{ " + safe_expression + " }}"])
        selected_setups = tuple(sorted(custom_config.setups, key=setup_order.__getitem__))
        setup_mutes = tuple(
            entity_id("input_boolean", "setup", setup_id, "notifications_muted")
            for setup_id in selected_setups
        )
        checks = " or ".join(f"is_state('{mute}', 'off')" for mute in setup_mutes)
        labels = [config.setups[key].display_label(key) for key in selected_setups]
        prefix = "Affected setup" if len(labels) == 1 else "Affected setups"
        virtual_name = f"custom_{custom_id}"
        measurement = {
            "service_name": virtual_name,
            "name": "value",
            "custom_id": custom_id,
            "label": custom_config.display_label(custom_id),
            "short_label": custom_config.display_short_label(custom_id),
            "group": custom_config.group,
            "device_class": custom_config.device_class,
            "alarmed": custom_config.alarmed,
            "config": custom_config,
            "setup_ids": selected_setups,
            "notification_context": f"{prefix}: {', '.join(labels)}. Calculated from physical LabPulse measurements.",
            "measurement_id": f"{virtual_name}_value",
            "entity_id": output_entity,
            "setup_notifications_unmuted_template": "{{ " + (checks or "true") + " }}",
            "threshold": _threshold(custom_id, custom_config),
            "source_entities": source_entities,
            "availability_template": availability_template,
            "state_template": state_template,
        }
        custom_measurements.append(measurement)
        for setup_id in selected_setups:
            measurements_by_setup[setup_id].append(measurement)
            if custom_config.alarmed:
                alarmed_measurements_by_setup[setup_id].append(measurement)

        if custom_config.alarmed:
            dependency_checks = [f"not is_number(states('{source}'))" for source in source_entities.values()]
            dependency_services = sorted({
                reference.split(".", 1)[0]
                for reference in custom_config.inputs.values()
            })
            dependency_checks.extend(
                check
                for service_name in dependency_services
                for check in (
                    f"is_state('{entity_id('binary_sensor', service_name, 'service_unhealthy')}', 'on')",
                    f"is_state('{entity_id('input_boolean', service_name, 'service_fault_active')}', 'on')",
                )
            )
            dependency_checks.append(f"not is_number(states('{output_entity}'))")
            virtual_service = {
                "name": virtual_name,
                "label": "Calculated Measurements",
                "service_id": virtual_name,
                "sensor_fault_confirm_seconds": 15,
                "unhealthy_template": "{{ " + " or ".join(dependency_checks) + " }}",
                "alarm_state_entities": [entity_id("input_select", virtual_name, "value", "alarm_state")],
                "subordinate_notification_ids": [f"labpulse_{measurement['measurement_id']}_status"],
                "measurement": measurement,
            }
            custom_alarm_services.append(virtual_service)
            custom_alarm_measurements.append((virtual_service, measurement))

    # Only setups with alarm-capable measurements need mute helpers. Empty
    # setups still appear in monitor_setups below so configured lab structure
    # remains visible even before sensors are assigned.
    setups = []
    for setup_id in setup_ids:
        items = alarmed_measurements_by_setup[setup_id]
        if not items:
            continue
        label = config.setups[setup_id].display_label(setup_id)
        shared_labels = tuple(
            item["short_label"] for item in items if len(item["setup_ids"]) > 1
        )
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
        for measurement in service["measurements"] if measurement["alarmed"]
    ]
    alarm_measurements.extend(custom_alarm_measurements)
    power_alarm_services = tuple(
        service
        for service in services
        if service["power"] is not None and service["power"]["alarmed"]
    )
    # Bulk controls only cover normal high/low alarms. Power alarms work
    # differently and have their own settings page.
    targets = _bulk_targets(config, alarm_measurements, measurements_by_setup)
    groups = targets[0]["deadband_groups"] if targets else ()
    monitor_setup_records: dict[str, dict[str, Any]] = {}
    for setup_id in setup_ids:
        setup_config = config.setups[setup_id]
        items = measurements_by_setup[setup_id]
        monitor_setup_records[setup_id] = {
            "setup_id": setup_id,
            "label": setup_config.display_label(setup_id),
            "icon": setup_config.icon,
            "measurements": tuple(items),
            "measurement_groups": _measurement_groups(items),
        }
    monitor_setups = tuple(
        monitor_setup_records[setup_id]
        for setup_id in setup_ids
        if config.setups[setup_id].dashboard == "main"
    )
    dashboard_records: list[dict[str, Any]] = []
    for dashboard_id, dashboard_config in sorted(
        config.dashboards.items(), key=lambda item: (item[1].order, item[0])
    ):
        dashboard_records.append({
            "dashboard_id": dashboard_id,
            "label": dashboard_config.display_label(dashboard_id),
            "icon": dashboard_config.icon,
            "path": f"dashboard-{dashboard_id}",
            "setups": tuple(
                monitor_setup_records[setup_id]
                for setup_id in setup_ids
                if config.setups[setup_id].dashboard == dashboard_id
            ),
        })
    return HomeAssistantRenderModel(
        services=tuple(services),
        dashboards=tuple(dashboard_records),
        setups=tuple(setups),
        monitor_setups=monitor_setups,
        custom_measurements=tuple(custom_measurements),
        custom_alarm_services=tuple(custom_alarm_services),
        alarm_measurements=tuple(alarm_measurements),
        power_alarm_services=power_alarm_services,
        sms_send_topic=SMS_SEND_TOPIC,
        bulk_alarm_targets=targets,
        bulk_alarm_target_options=tuple(target["option"] for target in targets),
        bulk_target_counts={
            target["option"]: len(target["measurement_keys"]) for target in targets
        },
        bulk_deadband_groups=groups,
        bulk_apply_entities=(
            entity_id("input_boolean", "bulk", "apply", "required_danger_percent"),
            entity_id("input_boolean", "bulk", "apply", "observation_window_seconds"),
            entity_id("input_boolean", "bulk", "apply", "required_recovery_seconds"),
            *(group["apply_entity"] for group in groups),
        ),
    )


def _measurement_groups(
    measurements: list[dict[str, Any]],
) -> tuple[tuple[str, tuple[dict[str, Any], ...]], ...]:
    """Group one setup's measurements by first-seen presentation group."""

    # Keep the order from config.yaml so the dashboard follows the order chosen
    # by the person who wrote the configuration.
    grouped: dict[str, list[dict[str, Any]]] = {}
    for measurement in measurements:
        grouped.setdefault(measurement["group"] or "Other Measurements", []).append(measurement)
    return tuple((name, tuple(items)) for name, items in grouped.items())


def _bulk_targets(
    config: LabPulseConfig,
    alarm_measurements: list[tuple[dict[str, Any], dict[str, Any]]],
    measurements_by_setup: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], ...]:
    """Build the targets and deadband groups used by the bulk editor."""

    # Power readings can appear on setup pages, but the bulk alarm editor must
    # not change them. This list contains only normal high/low alarms.
    by_key = {
        (service["name"], measurement["name"]): measurement
        for service, measurement in alarm_measurements
    }
    target_groups = [("all", "All measurements", list(by_key.values()))]
    target_groups.extend(
        (setup_id, f"{config.setups[setup_id].display_label(setup_id)} ({setup_id})", items)
        for setup_id, items in measurements_by_setup.items()
    )
    targets = []
    for target_id, option, candidates in target_groups:
        selected = [
            item for item in candidates
            if (item["service_name"], item["name"]) in by_key
        ]
        if not selected:
            continue
        # Share one deadband setting only when the readings mean the same thing
        # and use the same unit. A temperature setting must not change pressure.
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
            # Limit the editor to values accepted by every measurement in this
            # group.
            range_min = max(
                0, *(item["threshold"]["range_min"] for item in members)
            )
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

def render_alarm(render_model: HomeAssistantRenderModel) -> str:
    """Create and check the complete Home Assistant alarm package."""

    # Square brackets belong to the LabPulse render pass. Standard braces are
    # left untouched because Home Assistant evaluates those expressions later.
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
    environment.filters["yaml_scalar"] = yaml_scalar
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

    # Build these expressions now, but leave them for Home Assistant to run.
    # They depend on settings that a user can change from the dashboard.
    selected_expression = "{{ " + " or ".join(
        f"is_state('{entity}', 'on')"
        for entity in render_model.bulk_apply_entities
    ) + " }}"
    target_lines = [
        "{% set selected = states('"
        + entity_id("input_select", "bulk", "alarm", "timing", "target")
        + "') %}"
    ]
    for index, target in enumerate(render_model.bulk_alarm_targets):
        keyword = "if" if index == 0 else "elif"
        target_lines.append(
            f"{{% {keyword} selected == {json.dumps(target['option'])} %}}"
            f"{len(target['measurement_keys'])}"
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
    # Parse the generated YAML before saving it. This catches broken indentation
    # or invalid values, then writes the result in one consistent style.
    package = yaml.safe_load(rendered)
    if not isinstance(package, dict):
        raise ValueError("rendered Home Assistant alarm package must be a mapping")
    return (
        "# Generated by LabPulse. Edit config.yaml or generator templates.\n"
        + yaml.safe_dump(package, sort_keys=False, allow_unicode=True)
    )


def yaml_scalar(value: object) -> str:
    """Return one YAML-safe scalar or flow collection without a document marker."""

    dumped = yaml.safe_dump(
        value,
        default_flow_style=True,
        sort_keys=False,
        allow_unicode=True,
    ).strip()
    return dumped.removesuffix("\n...")
