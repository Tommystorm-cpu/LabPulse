"""Dashboard card builders for LabPulse's editable Home Assistant UI.

The generator writes Home Assistant's UI-storage dashboard format rather than
YAML-mode Lovelace. These helpers keep that JSON-shaped card structure in one
place so the build logic can talk in terms of services and readings.
"""

from .models import JsonDict, ReadingContext


def tile_card(entity_id: str, columns: str = "full") -> JsonDict:
    """Return a compact tile card for a sections dashboard.

    `grid_options.columns = full` makes each sensor reading span the available
    card width in a section, which is easier to scan on the Pi dashboard.
    """

    return {"type": "tile", "entity": entity_id, "grid_options": {"columns": columns}}


def heading_card(heading: str, icon: str) -> JsonDict:
    """Return a section heading card for Home Assistant's sections layout."""

    return {
        "type": "heading",
        "heading": heading,
        "heading_style": "title",
        "icon": icon,
    }


def alarm_settings_card(service_label: str, alarm_entities: list[JsonDict]) -> JsonDict:
    """Return the dashboard card used to edit one service's alarm settings.

    The generated dashboard remains editable in Home Assistant's UI; this card
    simply seeds a sensible starting point with all helpers in one place.
    """

    return {
        "type": "entities",
        "title": f"{service_label} Alarm Settings",
        "show_header_toggle": False,
        "entities": alarm_entities,
    }


def make_delay_helpers(service_id: str, service_label: str) -> JsonDict:
    """Build the shared alert/recovery delay helpers for a service.

    Delays are per hub rather than per reading to keep the dashboard compact
    when a single Arduino publishes several readings.
    """

    return {
        f"labpulse_{service_id}_{kind}_delay_seconds": delay_helper_config(service_label, kind)
        for kind in ("alert", "recovery")
    }


def delay_helper_config(service_label: str, kind: str) -> JsonDict:
    """Return one editable delay helper definition."""

    return {
        "name": f"{service_label} {kind.title()} Delay",
        "min": 0,
        "max": 300,
        "step": 1,
        "initial": 2,
        "unit_of_measurement": "s",
        "mode": "box",
    }


def initial_alarm_entities(service_id: str) -> list[JsonDict]:
    """Return the shared delay rows at the top of an alarm settings card."""

    return [
        entity_row(f"input_number.labpulse_{service_id}_alert_delay_seconds", "Alert delay"),
        entity_row(f"input_number.labpulse_{service_id}_recovery_delay_seconds", "Recovery delay"),
        {"type": "divider"},
    ]


def entity_row(entity_id: str, name: str) -> JsonDict:
    """Return one row for a Home Assistant entities card."""

    return {"entity": entity_id, "name": name}


def append_reading_alarm_rows(alarm_entities: list[JsonDict], reading: ReadingContext) -> None:
    """Add one reading's current value and threshold rows to the alarm card."""

    alarm_entities.append(entity_row(reading.entity_id, f"{reading.label} current"))

    if reading.mode in {"min", "range"}:
        alarm_entities.append(threshold_row(reading, "minimum"))

    if reading.mode in {"max", "range"}:
        alarm_entities.append(threshold_row(reading, "maximum"))

    alarm_entities.append({"type": "divider"})


def threshold_row(reading: ReadingContext, kind: str) -> JsonDict:
    """Return the dashboard row for one reading threshold helper."""

    return entity_row(
        f"input_number.labpulse_{reading.reading_id}_{kind}_threshold",
        f"{reading.label} {kind}",
    )


def remove_trailing_divider(entities: list[JsonDict]) -> None:
    """Remove a final divider row from an entities card in place."""

    if entities and entities[-1] == {"type": "divider"}:
        entities.pop()


def make_sensor_section(
    section_heading: str,
    section_icon: str,
    service_label: str,
    status_entity: str,
    readings: list[ReadingContext],
    alarm_entities: list[JsonDict],
) -> JsonDict:
    """Build one Home Assistant dashboard section for a service.

    A section contains the status tile, one tile per sensor reading, and a full
    width alarm settings card for editing thresholds/delays.
    """

    sensor_cards = [heading_card(section_heading, section_icon), tile_card(status_entity)]

    sensor_cards.extend(tile_card(reading.entity_id) for reading in readings)

    card = alarm_settings_card(service_label, alarm_entities)
    card["grid_options"] = {"columns": "full"}
    sensor_cards.append(card)

    return {"type": "grid", "cards": sensor_cards}
