"""Placeholder expansion and file-rendering helpers for Home Assistant templates."""

from pathlib import Path
from collections.abc import Mapping
from typing import Any
import re


PLACEHOLDER_PATTERN = re.compile(
    r"\[\[\s*(service|measurement|power|setup|model|sms)\.([a-zA-Z0-9_.]+)\s*\]\]"
)


def render_template_file(
    template_path: Path,
    destination: Path,
    context: dict[str, str],
) -> None:
    """Render a simple placeholder template to a destination file."""

    text = template_path.read_text(encoding="utf-8")
    for key, value in context.items():
        text = text.replace("[[ " + key + " ]]", value)
    destination.write_text(text.rstrip() + "\n", encoding="utf-8")


def expand_template(value: Any, context: dict[str, object]) -> Any:
    """Expand supported dotted placeholders in seed data."""

    if isinstance(value, dict):
        return {
            expand_template(key, context): expand_template(item, context)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [expand_template(item, context) for item in value]
    if isinstance(value, str):
        return expand_string(value, context)
    return value


def expand_string(value: str, context: dict[str, object]) -> object:
    """Expand one string while preserving non-string full-placeholder values."""

    full_match = PLACEHOLDER_PATTERN.fullmatch(value)
    if full_match:
        return expand_template(
            lookup(full_match.group(1), full_match.group(2), context), context
        )

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
    """Return a dotted attribute from the expansion context."""

    value = context[root_name]
    for part in dotted_path.split("."):
        value = value[part] if isinstance(value, Mapping) else getattr(value, part)
    return value
