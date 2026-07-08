"""Home Assistant MQTT entity registry lookup helpers.

MQTT discovery gives LabPulse stable `unique_id` values, but Home Assistant may
choose or rename the visible `entity_id`. This module reads Home Assistant's
entity registry so generated dashboard cards point at the real entities when
they already exist.
"""

import json
import sys

from .models import EntityRegistry, GeneratorPaths, JsonDict
from .naming import slug


def load_entity_registry(paths: GeneratorPaths) -> EntityRegistry:
    """Return Home Assistant MQTT entity registry mappings and entries.

    Missing or unreadable registry data is non-fatal. On a first boot, MQTT
    discovery may not have created entities yet, so callers fall back to the
    expected generated entity names.
    """

    registry_path = paths.entity_registry_path
    if not registry_path.exists():
        return EntityRegistry(by_unique_id={}, mqtt_entries=[])

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(
            f"WARNING: Could not parse Home Assistant entity registry: {registry_path}",
            file=sys.stderr,
        )
        return EntityRegistry(by_unique_id={}, mqtt_entries=[])

    entries = registry.get("data", {}).get("entities", [])
    mqtt_entries = [
        entity
        for entity in entries
        if entity.get("platform") == "mqtt" and entity.get("entity_id")
    ]
    by_unique_id = {
        str(entity["unique_id"]): str(entity["entity_id"])
        for entity in mqtt_entries
        if entity.get("unique_id")
    }
    return EntityRegistry(by_unique_id=by_unique_id, mqtt_entries=mqtt_entries)


def sensor_entity_id(
    service_name: str,
    service_config: JsonDict,
    reading_name: str,
    reading_key: str,
    reading_label: str,
    entity_registry: EntityRegistry,
) -> str:
    """Return the best dashboard entity ID for one reading.

    The lookup uses the exact unique ID published by MQTT discovery. If Home
    Assistant has not discovered the entity yet, the fallback mirrors the
    publisher's object ID.
    """

    registry_entity = entity_registry.by_unique_id.get(f"{service_name}_{reading_name}")

    if registry_entity:
        return registry_entity

    return f"sensor.{fallback_entity_prefix(service_config)}_{slug(reading_label)}"


def status_entity_id(
    service_name: str,
    service_config: JsonDict,
    entity_registry: EntityRegistry,
) -> str:
    """Return the best dashboard entity ID for a service status sensor."""

    registry_entity = entity_registry.by_unique_id.get(f"{service_name}_status")

    if registry_entity:
        return registry_entity

    return f"sensor.{fallback_entity_prefix(service_config)}_status"


def fallback_entity_prefix(service_config: JsonDict) -> str:
    """Return the entity prefix Home Assistant creates from the device name."""

    explicit = service_config.get("entity_prefix")
    return slug(str(explicit or service_config.get("device_name")))
