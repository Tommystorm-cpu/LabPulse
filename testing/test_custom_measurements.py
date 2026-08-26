"""Contracts for validated Home Assistant-calculated custom measurements."""

from __future__ import annotations

from copy import deepcopy

from pydantic import ValidationError
import yaml

from labpulse.common.config import LabPulseConfig
from labpulse.homeassistant.alarm import build_template_context, render_alarm
from labpulse.homeassistant.generator import _render_dashboard


def custom_config() -> dict[str, object]:
    """Return a small config with physical inputs and one calculation."""

    return {
        "mqtt": {"broker": "mosquitto"},
        "setups": {"water_loop": {"label": "Water Loop"}},
        "services": {
            "water_hub": {
                "driver": {
                    "type": "labpulse.serial_pipe",
                    "options": {"port": "/tmp/water-hub"},
                },
                "device_name": "Water Hub",
                "measurements": [
                    {"name": "supply", "setups": ["water_loop"], "unit": "°C"},
                    {"name": "return_temp", "setups": ["water_loop"], "unit": "°C"},
                ],
            }
        },
        "custom_measurements": {
            "temperature_difference": {
                "label": "Temperature Difference",
                "short_label": "Delta T",
                "subcategory": "Calculated",
                "setups": ["water_loop"],
                "inputs": {
                    "supply": "water_hub.supply",
                    "return_temp": "water_hub.return_temp",
                },
                "constants": {"scale": 1.5},
                "formula": "(return_temp - supply) * scale",
                "precision": 2,
                "unit": "°C",
                "device_class": "temperature",
                "icon": "mdi:delta",
            }
        },
    }


def test_custom_measurement_renders_sensor_dashboard_and_alarm() -> None:
    """Project one validated formula through every Home Assistant surface."""

    config = LabPulseConfig.model_validate(custom_config())
    context = build_template_context(config)
    custom = context.custom_measurements[0]
    if custom["entity_id"] != "sensor.labpulse_custom_temperature_difference":
        raise AssertionError(f"unexpected calculated entity: {custom['entity_id']}")
    if custom not in context.measurements_by_setup["water_loop"]:
        raise AssertionError("custom measurement was not assigned to its setup")
    if len(context.custom_alarm_services) != 1:
        raise AssertionError("alarmed custom measurement lacks dependency guard")

    package = render_alarm(context)
    dashboard = _render_dashboard(context)
    yaml.safe_load(package)
    yaml.safe_load(dashboard)
    required_fragments = (
        "sensor.labpulse_water_hub_supply",
        "sensor.labpulse_water_hub_return_temp",
        "labpulse_custom_temperature_difference",
        "(return_temp - supply) * scale",
        "labpulse_custom_temperature_difference_value_alarm_state",
    )
    for fragment in required_fragments:
        if fragment not in package:
            raise AssertionError(f"generated package is missing {fragment}")
    if "sensor.labpulse_custom_temperature_difference" not in dashboard:
        raise AssertionError("calculated entity is missing from the dashboard")


def test_unalarmed_custom_measurement_stays_visible_without_alarm_helpers() -> None:
    """Retain calculation and dashboard output when custom alarms are disabled."""

    data = custom_config()
    data["custom_measurements"]["temperature_difference"]["alarmed"] = False  # type: ignore[index]
    context = build_template_context(LabPulseConfig.model_validate(data))
    if context.custom_alarm_services:
        raise AssertionError("unalarmed calculation created alarm dependencies")
    if any(measurement.get("custom_id") for _, measurement in context.alarm_measurements):
        raise AssertionError("unalarmed calculation entered the alarm model")
    if "sensor.labpulse_custom_temperature_difference" not in _render_dashboard(context):
        raise AssertionError("unalarmed calculation disappeared from dashboards")


def test_custom_measurement_rejects_unknown_or_custom_inputs() -> None:
    """Resolve inputs exclusively against configured physical service readings."""

    unknown = custom_config()
    unknown["custom_measurements"]["temperature_difference"]["inputs"]["supply"] = "water_hub.missing"  # type: ignore[index]
    try:
        LabPulseConfig.model_validate(unknown)
    except ValidationError as error:
        if "unknown physical measurement" not in str(error):
            raise AssertionError(str(error)) from error
    else:
        raise AssertionError("unknown physical measurement was accepted")

    chained = custom_config()
    chained["custom_measurements"]["temperature_difference"]["inputs"]["supply"] = "custom.previous_result"  # type: ignore[index]
    try:
        LabPulseConfig.model_validate(chained)
    except ValidationError as error:
        if "unknown physical service: custom" not in str(error):
            raise AssertionError(str(error)) from error
    else:
        raise AssertionError("custom-on-custom input was accepted")


def test_formula_language_is_small_and_requires_every_input() -> None:
    """Reject executable syntax, unknown names, and misleading unused inputs."""

    cases = (
        ("__import__('os')", "only use names, numbers"),
        ("return_temp - unknown", "unknown name: unknown"),
        ("return_temp + 1", "does not use inputs: supply"),
    )
    for formula, expected in cases:
        data = deepcopy(custom_config())
        data["custom_measurements"]["temperature_difference"]["formula"] = formula  # type: ignore[index]
        try:
            LabPulseConfig.model_validate(data)
        except ValidationError as error:
            if expected not in str(error):
                raise AssertionError(str(error)) from error
        else:
            raise AssertionError(f"unsafe or incomplete formula was accepted: {formula}")


def test_formula_division_adds_a_runtime_zero_guard() -> None:
    """Make dynamic division unavailable instead of producing an invalid value."""

    data = custom_config()
    custom = data["custom_measurements"]["temperature_difference"]  # type: ignore[index]
    custom["formula"] = "(return_temp - supply) / scale"
    context = build_template_context(LabPulseConfig.model_validate(data))
    availability = context.custom_measurements[0]["availability_template"]
    if "((scale) | float(0)) != 0" not in availability:
        raise AssertionError(f"division guard missing from {availability}")


def test_single_input_conversion_is_valid() -> None:
    """Allow scaling or offsetting one physical measurement."""

    data = custom_config()
    custom = data["custom_measurements"]["temperature_difference"]  # type: ignore[index]
    custom["inputs"] = {"celsius": "water_hub.supply"}
    custom["constants"] = {"scale": 1.8, "offset": 32.0}
    custom["formula"] = "celsius * scale + offset"
    custom["unit"] = "°F"
    config = LabPulseConfig.model_validate(data)
    context = build_template_context(config)
    state = context.custom_measurements[0]["state_template"]
    if "celsius * scale" not in state or "+ offset" not in state:
        raise AssertionError(f"single-input conversion was not compiled: {state}")


def test_custom_measurement_still_requires_one_input() -> None:
    """Reject a constant-only expression because it is not a measurement conversion."""

    data = custom_config()
    custom = data["custom_measurements"]["temperature_difference"]  # type: ignore[index]
    custom["inputs"] = {}
    custom["constants"] = {"fixed": 10.0}
    custom["formula"] = "fixed"
    try:
        LabPulseConfig.model_validate(data)
    except ValidationError as error:
        if "require at least one input" not in str(error):
            raise AssertionError(str(error)) from error
    else:
        raise AssertionError("constant-only custom measurement was accepted")
