"""Naming helpers shared by Home Assistant generator modules.

Home Assistant entity IDs, helper IDs, and dashboard labels all start from the
same config strings. These helpers keep the generated names predictable.
"""

import re


def slug(value: str) -> str:
    """Return a Home Assistant/Docker-safe lowercase identifier."""

    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()


def title(value: str) -> str:
    """Turn a config identifier into a readable label for dashboard text."""

    return slug(value).replace("_", " ").title()
