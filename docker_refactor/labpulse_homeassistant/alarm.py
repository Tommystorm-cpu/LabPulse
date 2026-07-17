"""Build generated Home Assistant alarm package sections from editable YAML."""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import yaml

from labpulse_common.sms_templates import load_sms_templates

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
        "input_datetimes": indented_yaml(input_datetimes(seed, power_seed, model), 2),
        "sensors": indented_yaml(sensors(seed, power_seed, model), 2),
        "templates": indented_yaml(templates(seed, power_seed, model), 2),
        "scripts": indented_yaml(scripts(seed, model), 2),
        "automations": indented_yaml(automations(seed, power_seed, model), 2),
    }


def load_alarm_seed() -> dict[str, Any]:
    """Load editable normal alarm logic seed rules."""

    return yaml.safe_load((TEMPLATE_DIR / "alarm_logic.yaml").read_text(encoding="utf-8"))


def load_power_seed() -> dict[str, Any]:
    """Load the isolated direct-GPIO UPS lifecycle seed rules."""

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

    helpers: dict[str, object] = expand_keyed_items(
        seed["input_booleans"].get("global", []), {"model": model}
    )
    rules = seed["input_booleans"]
    for service in model.services:
        helpers.update(expand_keyed_items(rules.get("service", []), {"service": service}))
        if service.readings and service.power is None:
            helpers.update(expand_keyed_items(rules.get("alarm_service", []), {"service": service}))
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


def input_datetimes(
    seed: dict[str, Any],
    power_seed: dict[str, Any],
    model: RenderModel,
) -> dict[str, object]:
    """Return restart-persistent service-fault and power timestamps."""

    helpers: dict[str, object] = {}
    for service in model.services:
        helpers.update(
            expand_keyed_items(
                seed.get("input_datetimes", {}).get("service", []),
                {"service": service},
            )
        )
        if service.power is not None:
            helpers.update(expand_keyed_items(power_seed.get("input_datetimes", []), {"service": service, "power": service.power}))
    return helpers


def sensors(
    seed: dict[str, Any],
    power_seed: dict[str, Any],
    model: RenderModel,
) -> list[dict[str, object]]:
    """Return normal history and UPS rolling-change sensor entries."""

    result = []
    for service, reading in model.alarm_readings:
        result.extend(expand_template(item, {"service": service, "reading": reading}) for item in seed["sensors"].get("reading", []))
    for service in model.services:
        if service.power is not None:
            context = {"service": service, "power": service.power}
            result.extend(
                expand_template(item, context)
                for item in power_seed.get("sensors", [])
            )
    return result


def scripts(seed: dict[str, Any], model: RenderModel) -> dict[str, object]:
    """Return generated global dashboard action scripts."""

    return expand_keyed_items(
        seed.get("scripts", {}).get("global", []),
        {"model": model, "sms": sms_template_context(model)},
    )


def templates(seed: dict[str, Any], power_seed: dict[str, Any], model: RenderModel) -> list[dict[str, object]]:
    """Return normal alarm and dedicated power template entity blocks."""

    normal = []
    for service in model.services:
        normal.extend(
            expand_template(item, {"service": service})
            for item in seed["binary_sensors"].get("service", [])
        )
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
    sms = sms_template_context(model)
    global_context = {"model": model, "sms": sms}
    result.extend(
        expand_template(item, global_context)
        for item in seed["automations"].get("global", [])
    )
    for service in model.services:
        context = {"service": service, "model": model, "sms": sms}
        result.extend(
            expand_template(item, context)
            for item in seed["automations"].get("service_health", [])
        )
        if service.readings and service.power is None:
            result.extend(expand_template(item, context) for item in seed["automations"].get("service", []))
    for service, reading in model.alarm_readings:
        context = {"service": service, "reading": reading, "model": model, "sms": sms}
        result.extend(expand_template(item, context) for item in seed["automations"].get("reading", []))
    for service in model.services:
        if service.power is not None:
            context = {"service": service, "power": service.power, "model": model, "sms": sms}
            result.extend(expand_template(item, context) for item in power_seed.get("automations", []))
    return result


def sms_template_context(model: RenderModel) -> dict[str, Any]:
    """Add the conditional test prefix to every generated SMS alert title."""

    sms = deepcopy(load_sms_templates())
    test_prefix = json.dumps(f"{sms['formatting']['test_prefix']} ")
    test_entity = json.dumps(model.test_mode_entity)
    for category in ("alerts", "notifications"):
        for item in sms.get(category, {}).values():
            title = item["title"]
            item["title"] = (
                f"({test_prefix} if is_state({test_entity}, 'on') else \"\") "
                f"~ ({title})"
            )
    return sms


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
