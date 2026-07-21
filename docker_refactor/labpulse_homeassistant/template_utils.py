"""Placeholder expansion and file-rendering helpers for Home Assistant templates."""

from pathlib import Path
from collections.abc import Mapping
from typing import Any
import re


# Match the LabPulse placeholders that may be expanded in YAML rules.
PLACEHOLDER_PATTERN = re.compile(
    r"\[\[\s*(service|measurement|power|setup|model|sms)\.([a-zA-Z0-9_.]+)\s*\]\]"
)


def render_template_file(
    template_path: Path,
    destination: Path,
    context: dict[str, str],
) -> None:
    """Render a simple placeholder template to a destination file.

    Example template::

        input_number:
        [[ helpers ]]

    With ``context = {"helpers": "  delay: {}"}``, the written file is::

        input_number:
          delay: {}
    """

    # Replace each outer-file placeholder with its completed YAML section.
    text = template_path.read_text(encoding="utf-8")
    for key, value in context.items():
        text = text.replace("[[ " + key + " ]]", value)
    destination.write_text(text.rstrip() + "\n", encoding="utf-8")


def expand_template(value: Any, context: dict[str, object]) -> Any:
    """Expand placeholders throughout a nested YAML rule.

    Example input::

        {
            "name": "[[ measurement.label ]]",
            "settings": {
                "unit": "[[ measurement.threshold.unit ]]",
                "modes": ["Low Only", "High Only"],
            },
        }

    Example output::

        {
            "name": "Temperature",
            "settings": {
                "unit": "°C",
                "modes": ["Low Only", "High Only"],
            },
        }
    """

    # Rebuild dictionaries while expanding both their keys and values.
    if isinstance(value, dict):
        return {
            expand_template(key, context): expand_template(item, context)
            for key, item in value.items()
        }
    # Rebuild lists while expanding every item.
    if isinstance(value, list):
        return [expand_template(item, context) for item in value]

    # Expand placeholders inside strings and preserve all other value types.
    if isinstance(value, str):
        return expand_string(value, context)
    return value


def expand_string(value: str, context: dict[str, object]) -> object:
    """Expand one string while preserving a full placeholder's original type.

    A placeholder inside other text becomes part of a string::

        "Options: [[ model.options ]]"
        -> "Options: ['Freezer', 'Fridge']"

    A placeholder occupying the whole value keeps the original list type::

        "[[ model.options ]]"
        -> ["Freezer", "Fridge"]
    """

    # Preserve the original type when the whole value is one placeholder.
    full_match = PLACEHOLDER_PATTERN.fullmatch(value)
    if full_match:
        return expand_template(
            lookup(full_match.group(1), full_match.group(2), context), context
        )

    # Repeat substitution so a replacement may contain another placeholder.
    expanded = value
    for _iteration in range(10):
        updated = PLACEHOLDER_PATTERN.sub(
            lambda match: str(lookup(match.group(1), match.group(2), context)),
            expanded,
        )
        if updated == expanded:
            return updated
        expanded = updated
    raise ValueError(f"Recursive or excessively nested placeholder: {value}")


def lookup(root_name: str, dotted_path: str, context: dict[str, object]) -> object:
    """Return a value reached through dictionary keys or object attributes.

    Example context::

        {
            "measurement": {
                "threshold": {
                    "unit": "°C",
                },
            },
        }

    ``lookup("measurement", "threshold.unit", context)`` returns ``"°C"``.
    """

    # Walk dictionary keys or object attributes along the dotted path.
    value = context[root_name]
    for part in dotted_path.split("."):
        value = value[part] if isinstance(value, Mapping) else getattr(value, part)
    return value
