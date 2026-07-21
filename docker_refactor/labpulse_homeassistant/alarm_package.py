"""Build the Home Assistant alarm package from editable YAML rules."""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import yaml

from labpulse_common.sms_templates import load_sms_templates

from .render_model import RenderModel
from .paths import GeneratorPaths
from .template_utils import expand_template, render_template_file


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "alarm"


def load_alarm_seed() -> dict[str, Any]:
    """Load the editable ordinary-alarm YAML rules."""

    return yaml.safe_load(
        (TEMPLATE_DIR / "alarm_logic.yaml").read_text(encoding="utf-8")
    )


def load_power_seed() -> dict[str, Any]:
    """Load the editable dedicated-power YAML rules."""

    return yaml.safe_load(
        (TEMPLATE_DIR / "power_logic.yaml").read_text(encoding="utf-8")
    )


def render_alarm(paths: GeneratorPaths, render_model: RenderModel) -> None:
    """Write the generated Home Assistant alarm package."""

    # Create the package directory before expanding the outer YAML template.
    paths.packages_dir.mkdir(parents=True, exist_ok=True)
    render_template_file(
        TEMPLATE_DIR / "package.yaml.j2",
        paths.package_path,
        package_context(render_model),
    )
    print(f"Generated {paths.package_path}")


def package_context(render_model: RenderModel) -> dict[str, str]:
    """Return the indented YAML sections inserted into ``package.yaml.j2``.

    For example, the returned ``input_numbers`` string is inserted as::

        input_number:
          labpulse_freezer_temperature_minimum_threshold:
            name: Temperature Minimum Threshold
            min: -40
            max: 100
    """

    # Load the editable ordinary-alarm and power-lifecycle rules.
    alarm_rules = load_alarm_seed()
    power_rules = load_power_seed()

    # Render and indent every top-level Home Assistant package section.
    return {
        "input_numbers": indented_yaml(
            input_numbers(alarm_rules, power_rules, render_model), 2
        ),
        "input_selects": indented_yaml(
            input_selects(alarm_rules, power_rules, render_model), 2
        ),
        "input_booleans": indented_yaml(
            input_booleans(alarm_rules, power_rules, render_model), 2
        ),
        "input_datetimes": indented_yaml(
            input_datetimes(alarm_rules, power_rules, render_model), 2
        ),
        "sensors": indented_yaml(
            sensors(alarm_rules, power_rules, render_model), 2
        ),
        "templates": indented_yaml(
            templates(alarm_rules, power_rules, render_model), 2
        ),
        "scripts": indented_yaml(
            scripts(alarm_rules, render_model), 2
        ),
        "automations": indented_yaml(
            automations(alarm_rules, power_rules, render_model), 2
        ),
    }

def indented_yaml(value: object, spaces: int) -> str:
    """Dump YAML and indent every line for insertion into the package template.

    Example input::

        {
            "delay": {
                "min": 0,
                "max": 300,
            },
        }

    With ``spaces=2``, the returned string is::

          delay:
            min: 0
            max: 300
    """

    # Serialize the section and indent it for the outer package template.
    dumped = yaml.safe_dump(value, sort_keys=False).rstrip()
    prefix = " " * spaces
    return "\n".join(prefix + line if line else line for line in dumped.splitlines())


def expand_keyed_items(
    rule_items: list[dict[str, Any]], context: dict[str, object]
) -> dict[str, object]:
    """Turn template rules into a Home Assistant dictionary keyed by item ID.

    Example input for a setup whose ID is ``room_1``::

        [
            {
                "id": "alarm_[[ setup.setup_id ]]",
                "config": {
                    "name": "[[ setup.label ]] Notifications Muted",
                    "initial": False,
                },
            },
        ]

    Example output::

        {
            "alarm_room_1": {
                "name": "Room 1 Notifications Muted",
                "initial": False,
            },
        }
    """

    # Build the dictionary that will become one section of the Home Assistant YAML.
    generated_items: dict[str, object] = {}

    # Each rule contains a templated ID and the configuration stored under that ID.
    for rule in rule_items:
        # Replace placeholders in the ID using the supplied model, service, or measurement.
        helper_id = expand_template(rule["id"], context)
        # Use the finished ID as the YAML key and expand placeholders throughout its config.
        generated_items[str(helper_id)] = expand_template(rule["config"], context)

    # Return entries shaped like "labpulse_temperature_muted: {name: ...}".
    return generated_items


def input_numbers(
    alarm_rules: dict[str, Any],
    power_rules: dict[str, Any],
    render_model: RenderModel,
) -> dict[str, object]:
    """Return the generated input_number section keyed by helper ID.

    Example output::

        {
            "labpulse_freezer_temperature_minimum_threshold": {
                "name": "Temperature Minimum Threshold",
                "min": -40,
                "max": 100,
                "step": 0.1,
                "unit_of_measurement": "°C",
            },
        }
    """

    # Add global bulk-timing numbers only when bulk targets exist.
    helpers: dict[str, object] = (
        expand_keyed_items(
            alarm_rules["input_numbers"].get("global", []),
            {"model": render_model},
        )
        if render_model.bulk_alarm_targets
        else {}
    )
    # Add one reusable deadband value for every compatible measurement family.
    for group in render_model.bulk_deadband_groups:
        helpers[group.value_entity.split(".", 1)[1]] = {
            "name": f"Bulk {group.label} Recovery Deadband",
            "min": group.range_min,
            "max": group.range_max,
            "step": group.step,
            "unit_of_measurement": group.unit,
            "mode": "box",
        }
    number_rules = alarm_rules["input_numbers"]

    # Add ordinary measurement numbers and dedicated power numbers.
    for service in render_model.services:
        if service.measurements and service.power is None:
            for measurement in service.measurements:
                helpers.update(
                    expand_keyed_items(
                        number_rules.get("measurement", []),
                        {"service": service, "measurement": measurement},
                    )
                )
        if service.power is not None:
            helpers.update(
                expand_keyed_items(
                    power_rules.get("input_numbers", []),
                    {"service": service, "power": service.power},
                )
            )
    return helpers


def input_booleans(
    alarm_rules: dict[str, Any],
    power_rules: dict[str, Any],
    render_model: RenderModel,
) -> dict[str, object]:
    """Return the generated input_boolean section keyed by helper ID.

    Example output::

        {
            "labpulse_setup_room_1_notifications_muted": {
                "name": "Room 1 Notifications Muted",
            },
        }
    """

    # Start with global notification and initialization booleans.
    helpers: dict[str, object] = expand_keyed_items(
        alarm_rules["input_booleans"].get("global", []),
        {"model": render_model},
    )
    # Add opt-in flags so displayed bulk values are never applied implicitly.
    if render_model.bulk_alarm_targets:
        editor_id = render_model.entities["bulk_editor_expanded"].split(".", 1)[1]
        helpers[editor_id] = {
            "name": "Bulk Alarm Editor Expanded",
            "initial": False,
        }
        common_flags = (
            ("bulk_apply_required_danger_percent", "Required Danger"),
            ("bulk_apply_observation_window_seconds", "Observation Window"),
            ("bulk_apply_required_recovery_seconds", "Required Recovery"),
        )
        for role, label in common_flags:
            helper_id = render_model.entities[role].split(".", 1)[1]
            helpers[helper_id] = {
                "name": f"Bulk Apply {label}",
                "initial": False,
            }
        for group in render_model.bulk_deadband_groups:
            helpers[group.apply_entity.split(".", 1)[1]] = {
                "name": f"Bulk Apply {group.label} Recovery Deadband",
                "initial": False,
            }
    boolean_rules = alarm_rules["input_booleans"]

    # Add one notification-mute boolean for every active setup.
    for setup in render_model.setups:
        helpers.update(
            expand_keyed_items(boolean_rules.get("setup", []), {"setup": setup})
        )
    # Add service-health booleans and optional power-lifecycle booleans.
    for service in render_model.services:
        helpers.update(
            expand_keyed_items(
                boolean_rules.get("service", []), {"service": service}
            )
        )
        if service.power is not None:
            helpers.update(
                expand_keyed_items(
                    power_rules.get("input_booleans", []),
                    {"service": service, "power": service.power},
                )
            )
    # Add the individual mute and UI-state booleans for ordinary measurements.
    for service, measurement in render_model.alarm_measurements:
        helpers.update(
            expand_keyed_items(
                boolean_rules.get("measurement", []),
                {"service": service, "measurement": measurement},
            )
        )
    return helpers


def input_selects(
    alarm_rules: dict[str, Any],
    power_rules: dict[str, Any],
    render_model: RenderModel,
) -> dict[str, object]:
    """Return the generated input_select section keyed by helper ID.

    Example output::

        {
            "labpulse_freezer_temperature_alarm_mode": {
                "name": "Temperature Alarm Mode",
                "options": [
                    "Disabled",
                    "Low Only",
                    "High Only",
                    "Range",
                ],
            },
        }
    """

    # Add the global bulk target selector only when targets exist.
    helpers: dict[str, object] = (
        expand_keyed_items(
            alarm_rules["input_selects"].get("global", []),
            {"model": render_model},
        )
        if render_model.bulk_alarm_targets
        else {}
    )

    # Add alarm state and mode selectors for ordinary measurements.
    for service, measurement in render_model.alarm_measurements:
        helpers.update(
            expand_keyed_items(
                alarm_rules["input_selects"].get("measurement", []),
                {"service": service, "measurement": measurement},
            )
        )
    # Add the dedicated power lifecycle selector.
    for service in render_model.services:
        if service.power is not None:
            helpers.update(
                expand_keyed_items(
                    power_rules.get("input_selects", []),
                    {"service": service, "power": service.power},
                )
            )
    return helpers


def input_datetimes(
    alarm_rules: dict[str, Any],
    power_rules: dict[str, Any],
    render_model: RenderModel,
) -> dict[str, object]:
    """Return restart-persistent timestamps keyed by input_datetime helper ID.

    Example output::

        {
            "labpulse_ups_power_outage_started": {
                "name": "UPS Outage Started",
                "has_date": True,
                "has_time": True,
            },
        }
    """

    helpers: dict[str, object] = {}

    # Add service-fault timestamps and optional power-lifecycle timestamps.
    for service in render_model.services:
        helpers.update(
            expand_keyed_items(
                alarm_rules.get("input_datetimes", {}).get("service", []),
                {"service": service},
            )
        )
        if service.power is not None:
            helpers.update(
                expand_keyed_items(
                    power_rules.get("input_datetimes", []),
                    {"service": service, "power": service.power},
                )
            )
    return helpers


def sensors(
    alarm_rules: dict[str, Any],
    power_rules: dict[str, Any],
    render_model: RenderModel,
) -> list[dict[str, object]]:
    """Return the sensor entries inserted beneath Home Assistant's sensor key.

    Example output::

        [
            {
                "platform": "history_stats",
                "name": "labpulse_freezer_temperature_observed_danger_percent",
                "entity_id": "binary_sensor.labpulse_freezer_temperature_danger_zone",
                "state": "on",
                "type": "ratio",
                "start": "{{ now() - timedelta(seconds=120) }}",
                "end": "{{ now() }}",
            },
        ]
    """

    generated_sensors: list[dict[str, object]] = []

    # Expand history sensors for every ordinary measurement.
    for service, measurement in render_model.alarm_measurements:
        context = {"service": service, "measurement": measurement}
        generated_sensors.extend(
            expand_template(rule, context)
            for rule in alarm_rules["sensors"].get("measurement", [])
        )
    # Expand rolling-change sensors for each dedicated power service.
    for service in render_model.services:
        if service.power is not None:
            context = {"service": service, "power": service.power}
            generated_sensors.extend(
                expand_template(rule, context)
                for rule in power_rules.get("sensors", [])
            )
    return generated_sensors


def templates(
    alarm_rules: dict[str, Any],
    power_rules: dict[str, Any],
    render_model: RenderModel,
) -> list[dict[str, object]]:
    """Return the entity blocks inserted beneath Home Assistant's template key.

    Example output::

        [
            {
                "binary_sensor": [
                    {
                        "name": "labpulse_freezer_temperature_danger_zone",
                        "unique_id": "labpulse_freezer_temperature_danger_zone",
                        "state": "{{ states('sensor.freezer_temperature') | float > 8 }}",
                    },
                ],
            },
        ]
    """

    # Expand service-health and measurement template entities.
    ordinary_template_entities: list[dict[str, object]] = []
    for service in render_model.services:
        ordinary_template_entities.extend(
            expand_template(rule, {"service": service})
            for rule in alarm_rules["binary_sensors"].get("service", [])
        )
    for service, measurement in render_model.alarm_measurements:
        context = {"service": service, "measurement": measurement}
        ordinary_template_entities.extend(
            expand_template(rule, context)
            for rule in alarm_rules["binary_sensors"].get("measurement", [])
        )

    # Wrap ordinary entities in one Home Assistant binary-sensor block.
    generated_templates: list[dict[str, object]] = []
    if ordinary_template_entities:
        generated_templates.append(
            {"binary_sensor": ordinary_template_entities}
        )

    # Add native-dashboard state for selection gating and target measurement count.
    if render_model.bulk_alarm_targets:
        selected_expression = " or ".join(
            f"is_state('{entity}', 'on')"
            for entity in render_model.bulk_apply_entities
        )
        target_lines = [
            "{% set selected = states('"
            + render_model.entities["bulk_timing_target"]
            + "') %}"
        ]
        for index, target in enumerate(render_model.bulk_alarm_targets):
            keyword = "if" if index == 0 else "elif"
            target_lines.append(
                f"{{% {keyword} selected == {json.dumps(target.option)} %}}"
                f"{len(target.measurement_keys)}"
            )
        target_lines.extend(["{% else %}0", "{% endif %}"])
        generated_templates.append(
            {
                "binary_sensor": [
                    {
                        "name": "LabPulse Bulk Alarm Changes Selected",
                        "unique_id": "labpulse_bulk_alarm_changes_selected",
                        "state": "{{ " + selected_expression + " }}",
                    }
                ],
                "sensor": [
                    {
                        "name": "LabPulse Bulk Alarm Target Count",
                        "unique_id": "labpulse_bulk_alarm_target_count",
                        "state": "\n".join(target_lines),
                        "unit_of_measurement": "measurements",
                    }
                ],
            }
        )

    # Append the template blocks belonging to each power service.
    for service in render_model.services:
        if service.power is not None:
            context = {"service": service, "power": service.power}
            generated_templates.extend(
                expand_template(rule, context)
                for rule in power_rules.get("templates", [])
            )
    return generated_templates


def scripts(
    alarm_rules: dict[str, Any], render_model: RenderModel
) -> dict[str, object]:
    """Return the generated script section keyed by script ID.

    Example output::

        {
            "labpulse_send_phone_book_notification": {
                "alias": "Send LabPulse Phone Book Notification",
                "mode": "single",
                "sequence": [
                    {
                        "condition": "state",
                        "entity_id": "input_boolean.labpulse_global_notifications_muted",
                        "state": "off",
                    },
                    {
                        "service": "mqtt.publish",
                        "data": {
                            "topic": "labpulse/sms/send",
                            "qos": 1,
                            "retain": False,
                        },
                    },
                ],
            },
        }
    """

    # Expand the global action scripts with render and SMS context.
    generated_scripts = expand_keyed_items(
        alarm_rules.get("scripts", {}).get("global", []),
        {
            "model": render_model,
            "sms": sms_template_context(render_model),
        },
    )
    # Add selective bulk apply and reset scripts only when targets exist.
    if render_model.bulk_alarm_targets:
        generated_scripts["labpulse_clear_bulk_alarm_selection"] = {
            "alias": "Clear LabPulse Bulk Alarm Selection",
            "mode": "restart",
            "sequence": [
                {
                    "service": "input_boolean.turn_off",
                    "target": {"entity_id": list(render_model.bulk_apply_entities)},
                }
            ],
        }
        generated_scripts["labpulse_apply_bulk_alarm_settings"] = (
            bulk_alarm_settings_script(render_model)
        )
    return generated_scripts


def automations(
    alarm_rules: dict[str, Any],
    power_rules: dict[str, Any],
    render_model: RenderModel,
) -> list[dict[str, object]]:
    """Return the entries inserted beneath Home Assistant's automation key.

    Example output::

        [
            {
                "alias": "LabPulse Freezer Temperature Danger",
                "mode": "single",
                "trigger": [
                    {
                        "platform": "template",
                        "value_template": (
                            "{{ states('sensor.labpulse_freezer_temperature_"
                            "observed_danger_percent') | float(0) >= 70 }}"
                        ),
                    },
                ],
                "action": [
                    {
                        "service": "input_select.select_option",
                        "target": {
                            "entity_id": "input_select.labpulse_freezer_temperature_alarm_state",
                        },
                        "data": {"option": "Danger"},
                    },
                ],
            },
        ]
    """

    # Prepare shared SMS wording and the global template context.
    generated_automations: list[dict[str, object]] = []
    sms_rules = sms_template_context(render_model)
    global_context = {"model": render_model, "sms": sms_rules}
    # Expand global initialization and notification automations.
    generated_automations.extend(
        expand_template(rule, global_context)
        for rule in alarm_rules["automations"].get("global", [])
    )
    # Clear hidden apply flags whenever the operator selects another target.
    if render_model.bulk_alarm_targets:
        generated_automations.append(
            {
                "id": "labpulse_clear_bulk_alarm_selection_on_target_change",
                "alias": "LabPulse Clear Bulk Alarm Selection On Target Change",
                "mode": "restart",
                "trigger": [
                    {
                        "platform": "state",
                        "entity_id": render_model.entities["bulk_timing_target"],
                    }
                ],
                "action": [
                    {
                        "service": render_model.entities[
                            "bulk_clear_selection_script"
                        ]
                    }
                ],
            }
        )
    # Expand service-health fault and recovery automations.
    for service in render_model.services:
        context = {
            "service": service,
            "model": render_model,
            "sms": sms_rules,
        }
        generated_automations.extend(
            expand_template(rule, context)
            for rule in alarm_rules["automations"].get("service_health", [])
        )
    # Expand alarm transitions for every ordinary measurement.
    for service, measurement in render_model.alarm_measurements:
        context = {
            "service": service,
            "measurement": measurement,
            "model": render_model,
            "sms": sms_rules,
        }
        generated_automations.extend(
            expand_template(rule, context)
            for rule in alarm_rules["automations"].get("measurement", [])
        )
    # Expand the dedicated power lifecycle automations.
    for service in render_model.services:
        if service.power is not None:
            context = {
                "service": service,
                "power": service.power,
                "model": render_model,
                "sms": sms_rules,
            }
            generated_automations.extend(
                expand_template(rule, context)
                for rule in power_rules.get("automations", [])
            )
    return generated_automations


def bulk_alarm_settings_script(render_model: RenderModel) -> dict[str, object]:
    """Return the script that applies only explicitly selected bulk settings.

    Example output::

        {
            "alias": "Apply LabPulse Bulk Alarm Timing",
            "icon": "mdi:timer-sync-outline",
            "mode": "single",
            "sequence": [
                {
                    "variables": {
                        "selected_target": (
                            "{{ states('input_select.labpulse_bulk_alarm_timing_target') }}"
                        ),
                    },
                },
                {
                    "choose": [
                        {
                            "conditions": [
                                {
                                    "condition": "template",
                                    "value_template": "{{ selected_target == 'Room 1' }}",
                                },
                            ],
                            "sequence": [
                                {
                                    "service": "input_number.set_value",
                                    "target": {
                                        "entity_id": [
                                            "input_number.labpulse_freezer_temperature_required_danger_percent",
                                        ],
                                    },
                                    "data": {
                                        "value": (
                                            "{{ states('input_number.labpulse_bulk_"
                                            "required_danger_percent') | float(70) }}"
                                        ),
                                    },
                                },
                            ],
                        },
                    ],
                },
            ],
        }
    """

    # Snapshot target, flags, and values before running any helper writes.
    variables: dict[str, object] = {
        "selected_target": (
            "{{ states('" + render_model.entities["bulk_timing_target"] + "') }}"
        ),
        "apply_required_danger": (
            "{{ is_state('"
            + render_model.entities["bulk_apply_required_danger_percent"]
            + "', 'on') }}"
        ),
        "apply_observation_window": (
            "{{ is_state('"
            + render_model.entities["bulk_apply_observation_window_seconds"]
            + "', 'on') }}"
        ),
        "apply_required_recovery": (
            "{{ is_state('"
            + render_model.entities["bulk_apply_required_recovery_seconds"]
            + "', 'on') }}"
        ),
        "required_danger_value": (
            "{{ states('"
            + render_model.entities["bulk_required_danger_percent"]
            + "') | float(70) }}"
        ),
        "observation_window_value": (
            "{{ states('"
            + render_model.entities["bulk_observation_window_seconds"]
            + "') | int(120) }}"
        ),
        "required_recovery_value": (
            "{{ states('"
            + render_model.entities["bulk_required_recovery_seconds"]
            + "') | int(120) }}"
        ),
    }
    for group in render_model.bulk_deadband_groups:
        variables[f"apply_deadband_{group.helper_slug}"] = (
            "{{ is_state('" + group.apply_entity + "', 'on') }}"
        )
        variables[f"deadband_{group.helper_slug}_value"] = (
            "{{ states('" + group.value_entity + "') | float(0) }}"
        )

    # Build the exact success message from the same snapshotted values and target.
    target_counts = {
        target.option: len(target.measurement_keys)
        for target in render_model.bulk_alarm_targets
    }
    result_lines = [
        "{% set measurement_count = "
        + json.dumps(target_counts)
        + ".get(selected_target, 0) %}",
        "Applied bulk alarm settings to {{ selected_target }}:",
    ]
    result_lines.extend(
        [
            "{% if apply_required_danger %}- Required danger: {{ required_danger_value }}% → {{ measurement_count }} measurements{% endif %}",
            "{% if apply_observation_window %}- Observation window: {{ observation_window_value }} s → {{ measurement_count }} measurements{% endif %}",
            "{% if apply_required_recovery %}- Required recovery: {{ required_recovery_value }} s → {{ measurement_count }} measurements{% endif %}",
        ]
    )
    for target in render_model.bulk_alarm_targets:
        for group in target.deadband_groups:
            unit = f" {group.unit}" if group.unit else ""
            result_lines.append(
                "{% if selected_target == "
                + json.dumps(target.option)
                + " and apply_deadband_"
                + group.helper_slug
                + " %}- "
                + group.label
                + " deadband: {{ deadband_"
                + group.helper_slug
                + "_value }}"
                + unit
                + " → "
                + str(len(group.measurement_keys))
                + " measurements{% endif %}"
            )

    # Build one Home Assistant choose branch for every bulk target.
    choices: list[dict[str, object]] = []
    for target in render_model.bulk_alarm_targets:
        actions = [
            conditional_bulk_action(
                "apply_required_danger",
                target.required_danger_percent_entities,
                "{{ required_danger_value }}",
            ),
            conditional_bulk_action(
                "apply_observation_window",
                target.observation_window_seconds_entities,
                "{{ observation_window_value }}",
            ),
            conditional_bulk_action(
                "apply_required_recovery",
                target.required_recovery_seconds_entities,
                "{{ required_recovery_value }}",
            ),
        ]
        actions.extend(
            conditional_bulk_action(
                f"apply_deadband_{group.helper_slug}",
                group.recovery_deadband_entities,
                "{{ deadband_" + group.helper_slug + "_value }}",
            )
            for group in target.deadband_groups
        )
        choices.append(
            {
                "conditions": [
                    {
                        "condition": "template",
                        "value_template": (
                            "{{ selected_target == " + json.dumps(target.option) + " }}"
                        ),
                    }
                ],
                "sequence": actions,
            }
        )
    # Reject empty selections, apply the selected target branch, then clear flags.
    return {
        "alias": "Apply LabPulse Bulk Alarm Settings",
        "icon": "mdi:timer-sync-outline",
        "mode": "single",
        "sequence": [
            {"variables": variables},
            {
                "condition": "template",
                "value_template": "{{ "
                + " or ".join(
                    [
                        "apply_required_danger",
                        "apply_observation_window",
                        "apply_required_recovery",
                    ]
                    + [
                        f"apply_deadband_{group.helper_slug}"
                        for group in render_model.bulk_deadband_groups
                    ]
                )
                + " }}",
            },
            {"choose": choices},
            {
                "service": "persistent_notification.create",
                "data": {
                    "title": "LabPulse group settings applied",
                    "message": "\n".join(result_lines),
                    "notification_id": "labpulse_bulk_alarm_settings_result",
                },
            },
            {"service": render_model.entities["bulk_clear_selection_script"]},
        ],
    }


def conditional_bulk_action(
    apply_variable: str,
    entity_ids: tuple[str, ...],
    value_template: str,
) -> dict[str, object]:
    """Return one guarded helper write for a snapshotted apply flag."""

    return {
        "if": [
            {
                "condition": "template",
                "value_template": "{{ " + apply_variable + " }}",
            }
        ],
        "then": [
            {
                "service": "input_number.set_value",
                "target": {"entity_id": list(entity_ids)},
                "data": {"value": value_template},
            }
        ],
    }


def sms_template_context(render_model: RenderModel) -> dict[str, Any]:
    """Add the conditional test prefix to every generated SMS alert title."""

    # Copy the shared wording so generation never mutates the source rules.
    sms_rules = deepcopy(load_sms_templates())

    # Resolve the test prefix and Home Assistant test-mode entity.
    test_prefix = json.dumps(f"{sms_rules['formatting']['test_prefix']} ")
    test_entity = json.dumps(render_model.entities["test_mode"])
    # Add the runtime test-mode prefix to every generated title expression.
    for category in ("alerts", "notifications"):
        for message_rules in sms_rules.get(category, {}).values():
            title = message_rules["title"]
            message_rules["title"] = (
                f"({test_prefix} if is_state({test_entity}, 'on') else \"\") "
                f"~ ({title})"
            )
    return sms_rules
