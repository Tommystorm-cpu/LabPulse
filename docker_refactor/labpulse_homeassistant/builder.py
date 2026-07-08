"""Main in-memory build recipe for generated Home Assistant config.

This module is the "join point" for the package. It takes service definitions
from `config.yaml` and asks the smaller modules to build reading contexts,
helpers, automations, and dashboard cards.
"""

from .automations import make_alert_automation, make_recovery_automation
from .dashboard import (
    alarm_settings_card,
    append_reading_alarm_rows,
    heading_card,
    initial_alarm_entities,
    make_delay_helpers,
    make_sensor_section,
    remove_trailing_divider,
    tile_card,
)
from .entities import status_entity_id
from .readings import build_reading_context, configured_readings, make_threshold_entities
from .models import EntityRegistry, GeneratedConfig, JsonDict, ReadingContext
from .naming import slug, title


def add_reading_alarm_config(
    generated: GeneratedConfig,
    reading: ReadingContext,
    reading_config: JsonDict,
    alert_delay: str,
    recovery_delay: str,
) -> None:
    """Add helper entities and automations for one reading.

    Every reading gets its own active-alert boolean so recovery automations only
    run after a matching alert has happened.
    """

    generated.input_booleans[f"labpulse_{reading.reading_id}_alert_active"] = {
        "name": f"{reading.label} Alert Active",
        "initial": False,
    }

    for helper_id, helper_config in make_threshold_entities(reading.reading_id, reading_config):
        generated.input_numbers[helper_id] = helper_config

    generated.automations.append(make_alert_automation(reading, alert_delay))
    generated.automations.append(make_recovery_automation(reading, recovery_delay))


def add_service_config(
    generated: GeneratedConfig,
    service_name: str,
    service_config: JsonDict,
    entity_registry: EntityRegistry,
) -> None:
    """Add dashboard cards, helpers, and automations for one enabled service.

    A service normally maps to one physical sensor hub. Hubs with several
    readings share alert/recovery delays but keep separate thresholds and active
    alert state per reading.
    """

    service_id = slug(service_name)
    service_label = str(service_config.get("device_name") or title(service_name))
    display_config = service_config.get("display", {})
    section_heading = str(display_config.get("section") or service_label)
    section_icon = str(display_config.get("icon") or "mdi:chip")
    readings_config = configured_readings(service_config)
    status_entity = status_entity_id(service_name, service_config, entity_registry)

    generated.system_health_cards.append(tile_card(status_entity))
    if not readings_config:
        return

    generated.input_numbers.update(make_delay_helpers(service_id, service_label))

    alert_delay = f"input_number.labpulse_{service_id}_alert_delay_seconds"
    recovery_delay = f"input_number.labpulse_{service_id}_recovery_delay_seconds"
    alarm_entities = initial_alarm_entities(service_id)
    reading_contexts = []

    for reading_config in readings_config:
        reading = build_reading_context(
            service_name,
            service_id,
            service_config,
            reading_config,
            entity_registry,
        )
        reading_contexts.append(reading)
        add_reading_alarm_config(
            generated,
            reading,
            reading_config,
            alert_delay,
            recovery_delay,
        )
        append_reading_alarm_rows(alarm_entities, reading)

    remove_trailing_divider(alarm_entities)
    generated.dashboard_cards.append(alarm_settings_card(service_label, alarm_entities))
    generated.dashboard_sections.append(
        make_sensor_section(
            section_heading,
            section_icon,
            service_label,
            status_entity,
            reading_contexts,
            alarm_entities,
        )
    )


def build_generated_config(config: JsonDict, entity_registry: EntityRegistry) -> GeneratedConfig:
    """Build all generated Home Assistant structures in memory.

    Nothing is written to disk here. Keeping this pure-ish makes it easier to
    test generation decisions separately from filesystem behavior.
    """

    generated = GeneratedConfig()
    generated.system_health_cards.append(heading_card("System Health", "mdi:heart-cog"))

    services = sorted(
        config.get("services", {}).items(),
        key=lambda item: item[1].get("display", {}).get("order", 100) if item[1] else 100,
    )

    for service_name, service_config in services:
        service_config = service_config or {}
        if service_config.get("enabled", True):
            add_service_config(generated, service_name, service_config, entity_registry)

    return generated
