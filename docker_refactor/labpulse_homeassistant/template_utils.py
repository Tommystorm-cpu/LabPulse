"""Small placeholder expansion helpers for editable Home Assistant seeds."""

from typing import Any
import re


PLACEHOLDER_PATTERN = re.compile(r"\{(service|reading|model)\.([a-zA-Z0-9_.]+)\}")


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
        return lookup(full_match.group(1), full_match.group(2), context)

    return PLACEHOLDER_PATTERN.sub(
        lambda match: str(lookup(match.group(1), match.group(2), context)),
        value,
    )


def lookup(root_name: str, dotted_path: str, context: dict[str, object]) -> object:
    """Return a dotted attribute from the expansion context."""

    value = context[root_name]
    for part in dotted_path.split("."):
        value = getattr(value, part)
    return value
