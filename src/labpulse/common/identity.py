"""Stable LabPulse identifiers shared across runtime and config generation."""

import re


def slug(value: str) -> str:
    """Return a Home Assistant-safe lowercase identifier."""

    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()


def title(value: str) -> str:
    """Turn a configuration identifier into a readable label."""

    return slug(value).replace("_", " ").title()


def stable_id(*parts: str) -> str:
    """Return a stable LabPulse ID built only from machine identifiers."""

    normalized = [slug(part) for part in parts if slug(part)]
    return "labpulse_" + "_".join(normalized)


def entity_id(domain: str, *parts: str) -> str:
    """Return a Home Assistant entity ID using the stable LabPulse ID."""

    return f"{domain}.{stable_id(*parts)}"
