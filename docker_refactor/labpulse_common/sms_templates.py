"""Load the single shared catalogue of user-facing SMS templates."""

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


TEMPLATE_PATH = Path(__file__).resolve().with_name("sms_templates.yaml")
CURRENT_READING_PLACEHOLDER = "{current_reading}"


@lru_cache(maxsize=1)
def load_sms_templates() -> dict[str, Any]:
    """Return the validated SMS template catalogue bundled with LabPulse."""

    payload = yaml.safe_load(TEMPLATE_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"SMS template catalogue must be a mapping: {TEMPLATE_PATH}")

    required_paths = (
        ("alerts", "reading_warning", "title"),
        ("alerts", "reading_warning", "message"),
        ("alerts", "reading_recovery", "title"),
        ("alerts", "reading_recovery", "message"),
        ("alerts", "reading_sensor_fault", "title"),
        ("alerts", "reading_sensor_fault", "message"),
        ("alerts", "reading_sensor_recovery", "title"),
        ("alerts", "reading_sensor_recovery", "message"),
        ("alerts", "power_warning", "title"),
        ("alerts", "power_warning", "message"),
        ("alerts", "power_recovery", "title"),
        ("alerts", "power_recovery", "message"),
        ("alerts", "power_sensor_fault", "title"),
        ("alerts", "power_sensor_fault", "message"),
        ("alerts", "power_sensor_recovery", "title"),
        ("alerts", "power_sensor_recovery", "message"),
        ("formatting", "test_prefix"),
        ("formatting", "unsubscribe_footer"),
        ("commands", "unsubscribe_confirmation"),
        ("commands", "subscribe_confirmation"),
    )
    for path in required_paths:
        value: object = payload
        for key in path:
            if not isinstance(value, dict) or key not in value:
                dotted_path = ".".join(path)
                raise ValueError(f"Missing SMS template: {dotted_path}")
            value = value[key]
        if not isinstance(value, str) or not value.strip():
            dotted_path = ".".join(path)
            raise ValueError(f"SMS template must be non-empty text: {dotted_path}")
    for name, alert in payload["alerts"].items():
        if CURRENT_READING_PLACEHOLDER not in alert["message"]:
            raise ValueError(
                f"SMS alert message must contain {CURRENT_READING_PLACEHOLDER}: {name}"
            )
    return payload


def sms_template(*path: str) -> str:
    """Return one text template from the validated catalogue."""

    value: object = load_sms_templates()
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise KeyError(f"Unknown SMS template: {'.'.join(path)}")
        value = value[key]
    if not isinstance(value, str):
        raise TypeError(f"SMS template is not text: {'.'.join(path)}")
    return value
