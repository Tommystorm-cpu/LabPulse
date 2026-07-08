"""Home Assistant automation builders for LabPulse alarms.

These functions return plain dictionaries because Home Assistant packages are
ultimately YAML. Keeping the YAML shape here avoids spreading Jinja templates
and service-call dictionaries through the rest of the generator.
"""

from .models import JsonDict, ReadingContext


def bad_condition(reading: ReadingContext) -> str:
    """Return the template that means a reading is outside its threshold."""

    return threshold_condition(reading, recovered=False)


def good_condition(reading: ReadingContext) -> str:
    """Return the template that means a reading has recovered."""

    return threshold_condition(reading, recovered=True)


def threshold_condition(reading: ReadingContext, recovered: bool) -> str:
    """Return the Jinja condition for either alert or recovery state.

    `recovered=False` means "outside the threshold". `recovered=True` means
    "back inside the threshold". Home Assistant evaluates this template on
    state changes and then applies the configured delay.
    """

    current = f"states('{reading.entity_id}') | float(0)"
    min_entity = f"input_number.labpulse_{reading.reading_id}_minimum_threshold"
    max_entity = f"input_number.labpulse_{reading.reading_id}_maximum_threshold"

    if reading.mode == "range":
        lower_op, upper_op, joiner = (">=", "<=", "and") if recovered else ("<", ">", "or")
        return (
            f"{{{{ {current} {lower_op} states('{min_entity}') | float(0)\n"
            f"   {joiner} {current} {upper_op} states('{max_entity}') | float(0) }}}}"
        )

    if reading.mode == "max":
        return comparison_template(current, "<=" if recovered else ">", max_entity)

    return comparison_template(current, ">=" if recovered else "<", min_entity)


def comparison_template(current: str, operator: str, threshold_entity: str) -> str:
    """Return a one-sided Home Assistant Jinja comparison template."""

    return f"{{{{ {current} {operator} states('{threshold_entity}') | float(0) }}}}"


def threshold_summary(reading: ReadingContext) -> str:
    """Return notification text describing the active threshold values."""

    min_entity = f"input_number.labpulse_{reading.reading_id}_minimum_threshold"
    max_entity = f"input_number.labpulse_{reading.reading_id}_maximum_threshold"

    if reading.mode == "range":
        return (
            f"Min: {{{{ states('{min_entity}') }}}}. "
            f"Max: {{{{ states('{max_entity}') }}}}."
        )

    if reading.mode == "max":
        return f"Max: {{{{ states('{max_entity}') }}}}."

    return f"Min: {{{{ states('{min_entity}') }}}}."


def make_automation(
    alias: str,
    trigger_template: str,
    delay_entity: str,
    active_entity: str,
    active_state: str,
    actions: list[JsonDict],
) -> JsonDict:
    """Build one Home Assistant automation dictionary.

    `active_state` prevents repeated notifications: alert automations only run
    while the reading is inactive, and recovery automations only run while it is
    active.
    """

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
            {"condition": "state", "entity_id": active_entity, "state": active_state}
        ],
        "action": actions,
    }


def notification_action(title_text: str, message_text: str, notification_id: str) -> JsonDict:
    """Return a persistent notification action for Home Assistant."""

    return {
        "service": "persistent_notification.create",
        "data": {
            "title": title_text,
            "message": message_text,
            "notification_id": notification_id,
        },
    }


def make_alert_automation(reading: ReadingContext, alert_delay: str) -> JsonDict:
    """Build the automation that marks a reading as alarming."""

    return make_reading_automation(reading, alert_delay, recovered=False)


def make_recovery_automation(reading: ReadingContext, recovery_delay: str) -> JsonDict:
    """Build the automation that clears an active alarm."""

    return make_reading_automation(reading, recovery_delay, recovered=True)


def make_reading_automation(
    reading: ReadingContext,
    delay_entity: str,
    recovered: bool,
) -> JsonDict:
    """Build either the alert or recovery automation for one reading."""

    action_word = "recovered" if recovered else "alert"
    alias_suffix = "Recovery" if recovered else "Alert"
    active_state = "on" if recovered else "off"
    toggle_service = "input_boolean.turn_off" if recovered else "input_boolean.turn_on"
    trigger_template = good_condition(reading) if recovered else bad_condition(reading)
    message = reading_message(reading, recovered)

    return make_automation(
        f"LabPulse {reading.label} {alias_suffix}",
        trigger_template,
        delay_entity,
        reading.active_entity,
        active_state,
        [
            {"service": toggle_service, "target": {"entity_id": reading.active_entity}},
            notification_action(
                f"LabPulse {reading.label} {action_word}",
                message,
                f"labpulse_{reading.reading_id}_status",
            ),
        ],
    )


def reading_message(reading: ReadingContext, recovered: bool) -> str:
    """Return the notification message for one alert or recovery event."""

    state_text = (
        f"{reading.label} has recovered."
        if recovered
        else f"{reading.label} is outside its threshold."
    )
    return (
        f"{state_text}\n\n"
        f"Current reading: {{{{ states('{reading.entity_id}') }}}}.\n"
        f"{threshold_summary(reading)}"
    )
