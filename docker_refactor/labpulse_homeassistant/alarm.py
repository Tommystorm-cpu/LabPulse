"""Build generated Home Assistant alarm package sections from editable YAML."""

from pathlib import Path
from typing import Any

import yaml

from .model import RenderModel, ServiceModel
from .template_utils import expand_template


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def package_context(model: RenderModel) -> dict[str, str]:
    """Return rendered package sections from the alarm seed."""

    seed = load_alarm_seed()
    return {
        "input_numbers": indented_yaml(input_numbers(seed, model), 2),
        "input_booleans": indented_yaml(input_booleans(seed, model), 2),
        "binary_sensors": indented_yaml(binary_sensors(seed, model), 2),
        "automations": indented_yaml(automations(seed, model), 2),
    }


def load_alarm_seed() -> dict[str, Any]:
    """Load editable alarm logic seed rules."""

    return yaml.safe_load((TEMPLATE_DIR / "alarm_logic.yaml").read_text(encoding="utf-8"))


def input_numbers(seed: dict[str, Any], model: RenderModel) -> dict[str, object]:
    """Return generated input_number helpers."""

    helpers: dict[str, object] = {}
    rules = seed["input_numbers"]
    for service in model.services:
        if service.readings:
            helpers.update(expand_keyed_items(rules.get("service", []), {"service": service}))
        for reading in service.readings:
            helpers.update(expand_keyed_items(rules.get("reading", []), {"service": service, "reading": reading}))
    return helpers


def input_booleans(seed: dict[str, Any], model: RenderModel) -> dict[str, object]:
    """Return generated input_boolean helpers."""

    helpers: dict[str, object] = {}
    rules = seed["input_booleans"]
    for service, reading in model.readings:
        helpers.update(expand_keyed_items(rules.get("reading", []), {"service": service, "reading": reading}))
    return helpers


def binary_sensors(seed: dict[str, Any], model: RenderModel) -> list[dict[str, object]]:
    """Return generated template binary sensors."""

    sensors = []
    rules = seed["binary_sensors"]
    for service, reading in model.readings:
        context = {"service": service, "reading": reading}
        sensors.extend(expand_template(item, context) for item in rules.get("reading", []))

    if not sensors:
        return []
    return [{"binary_sensor": sensors}]


def automations(seed: dict[str, Any], model: RenderModel) -> list[dict[str, object]]:
    """Return generated alert and recovery automations."""

    result = []
    rules = seed["automations"]
    for service, reading in model.readings:
        context = {"service": service, "reading": reading, "model": model}
        result.extend(expand_template(item, context) for item in rules.get("reading", []))
    return result


def expand_keyed_items(items: list[dict[str, Any]], context: dict[str, object]) -> dict[str, object]:
    """Expand a list of `{id, config}` items into a Home Assistant helper map."""

    expanded = {}
    for item in items:
        helper_id = expand_template(item["id"], context)
        expanded[str(helper_id)] = expand_template(item["config"], context)
    return expanded


def indented_yaml(value: object, spaces: int) -> str:
    """Dump YAML and indent every line for insertion into package template."""

    dumped = yaml.safe_dump(value, sort_keys=False).rstrip()
    prefix = " " * spaces
    return "\n".join(prefix + line if line else line for line in dumped.splitlines())
