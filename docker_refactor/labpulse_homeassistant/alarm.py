"""Build generated Home Assistant alarm package sections from editable YAML."""

from pathlib import Path
from typing import Any

import yaml

from .data_models import GeneratorPaths, RenderModel
from .template_utils import expand_template, render_template_file


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "alarm"


def render_alarm(paths: GeneratorPaths, model: RenderModel) -> None:
    """Write the generated Home Assistant alarm package."""

    paths.packages_dir.mkdir(parents=True, exist_ok=True)
    render_template_file(
        TEMPLATE_DIR / "package.yaml.j2",
        paths.package_path,
        package_context(model),
    )
    print(f"Generated {paths.package_path}")


def package_context(model: RenderModel) -> dict[str, str]:
    """Return rendered package sections from normal and power seeds."""

    seed = load_alarm_seed()
    power_seed = load_power_seed()
    return {
        "input_numbers": indented_yaml(input_numbers(seed, power_seed, model), 2),
        "input_selects": indented_yaml(input_selects(seed, power_seed, model), 2),
        "input_booleans": indented_yaml(input_booleans(seed, power_seed, model), 2),
        "input_datetimes": indented_yaml(input_datetimes(power_seed, model), 2),
        "sensors": indented_yaml(sensors(seed, model), 2),
        "templates": indented_yaml(templates(seed, power_seed, model), 2),
        "automations": indented_yaml(automations(seed, power_seed, model), 2),
    }


def load_alarm_seed() -> dict[str, Any]:
    """Load editable normal alarm logic seed rules."""

    return yaml.safe_load((TEMPLATE_DIR / "alarm_logic.yaml").read_text(encoding="utf-8"))


def load_power_seed() -> dict[str, Any]:
    """Load the isolated UPS low-voltage lifecycle seed rules."""

    return yaml.safe_load((TEMPLATE_DIR / "power_logic.yaml").read_text(encoding="utf-8"))


def input_numbers(seed: dict[str, Any], power_seed: dict[str, Any], model: RenderModel) -> dict[str, object]:
    """Return generated input_number helpers."""

    helpers: dict[str, object] = {}
    rules = seed["input_numbers"]
    for service in model.services:
        if service.readings and service.power is None:
            helpers.update(expand_keyed_items(rules.get("service", []), {"service": service}))
            for reading in service.readings:
                helpers.update(expand_keyed_items(rules.get("reading", []), {"service": service, "reading": reading}))
        if service.power is not None:
            helpers.update(expand_keyed_items(power_seed.get("input_numbers", []), {"service": service, "power": service.power}))
    return helpers


def input_booleans(seed: dict[str, Any], power_seed: dict[str, Any], model: RenderModel) -> dict[str, object]:
    """Return generated input_boolean helpers."""

    helpers: dict[str, object] = {}
    rules = seed["input_booleans"]
    for service in model.services:
        if service.readings and service.power is None:
            helpers.update(expand_keyed_items(rules.get("service", []), {"service": service}))
        if service.power is not None:
            helpers.update(expand_keyed_items(power_seed.get("input_booleans", []), {"service": service, "power": service.power}))
    for service, reading in model.alarm_readings:
        helpers.update(expand_keyed_items(rules.get("reading", []), {"service": service, "reading": reading}))
    return helpers


def input_selects(seed: dict[str, Any], power_seed: dict[str, Any], model: RenderModel) -> dict[str, object]:
    """Return generated input_select helpers."""

    helpers: dict[str, object] = {}
    for service, reading in model.alarm_readings:
        helpers.update(expand_keyed_items(seed["input_selects"].get("reading", []), {"service": service, "reading": reading}))
    for service in model.services:
        if service.power is not None:
            helpers.update(expand_keyed_items(power_seed.get("input_selects", []), {"service": service, "power": service.power}))
    return helpers


def input_datetimes(power_seed: dict[str, Any], model: RenderModel) -> dict[str, object]:
    """Return restart-persistent power candidate and outage timestamps."""

    helpers: dict[str, object] = {}
    for service in model.services:
        if service.power is not None:
            helpers.update(expand_keyed_items(power_seed.get("input_datetimes", []), {"service": service, "power": service.power}))
    return helpers


def sensors(seed: dict[str, Any], model: RenderModel) -> list[dict[str, object]]:
    """Return normal alarm history-stat sensor platform entries."""

    result = []
    for service, reading in model.alarm_readings:
        result.extend(expand_template(item, {"service": service, "reading": reading}) for item in seed["sensors"].get("reading", []))
    return result


def templates(seed: dict[str, Any], power_seed: dict[str, Any], model: RenderModel) -> list[dict[str, object]]:
    """Return normal alarm and dedicated power template entity blocks."""

    normal = []
    for service, reading in model.alarm_readings:
        context = {"service": service, "reading": reading}
        normal.extend(expand_template(item, context) for item in seed["binary_sensors"].get("reading", []))
    result: list[dict[str, object]] = [{"binary_sensor": normal}] if normal else []
    for service in model.services:
        if service.power is not None:
            context = {"service": service, "power": service.power}
            result.extend(expand_template(item, context) for item in power_seed.get("templates", []))
    return result


def automations(seed: dict[str, Any], power_seed: dict[str, Any], model: RenderModel) -> list[dict[str, object]]:
    """Return normal alarms and the dedicated power lifecycle automations."""

    result = []
    for service in model.services:
        if service.readings and service.power is None:
            context = {"service": service, "model": model}
            result.extend(expand_template(item, context) for item in seed["automations"].get("service", []))
    for service, reading in model.alarm_readings:
        context = {"service": service, "reading": reading, "model": model}
        result.extend(expand_template(item, context) for item in seed["automations"].get("reading", []))
    for service in model.services:
        if service.power is not None:
            context = {"service": service, "power": service.power, "model": model}
            result.extend(expand_template(item, context) for item in power_seed.get("automations", []))
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
