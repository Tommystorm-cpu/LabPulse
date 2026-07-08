"""Reading, threshold, and reading-context helpers.

This module is the bridge between LabPulse's hardware-facing `config.yaml`
readings and Home Assistant's editable threshold helpers. It keeps all default
units/ranges in one place so adding a new sensor type does not require hunting
through dashboard or automation code.
"""

from .entities import sensor_entity_id
from .models import EntityRegistry, JsonDict, ReadingContext
from .naming import slug, title


THRESHOLD_DEFAULTS = {
    "temp": {
        "unit": "\u00b0C",
        "mode": "range",
        "min": 5,
        "max": 35,
        "range_min": -20,
        "range_max": 80,
        "step": 0.1,
    },
    "hum": {
        "unit": "%",
        "mode": "range",
        "min": 20,
        "max": 80,
        "range_min": 0,
        "range_max": 100,
        "step": 1,
    },
    "flow": {
        "unit": "L/min",
        "mode": "min",
        "min": 1,
        "range_min": 0,
        "range_max": 20,
        "step": 0.1,
    },
    "pressure": {
        "unit": "bar",
        "mode": "min",
        "min": 1,
        "range_min": 0,
        "range_max": 10,
        "step": 0.1,
    },
    "generic": {
        "unit": "",
        "mode": "min",
        "min": 0,
        "range_min": 0,
        "range_max": 100,
        "step": 1,
    },
}


def reading_defaults(reading_name: str) -> JsonDict:
    """Infer threshold style and units from a reading name.

    The match is intentionally simple because reading names come from Arduino
    parser labels such as `temp0`, `flow1`, and `pressure`. Explicit reading
    threshold config in `config.yaml` still wins over these defaults.
    """

    name = slug(reading_name)

    if "temp" in name:
        return THRESHOLD_DEFAULTS["temp"]

    if "hum" in name:
        return THRESHOLD_DEFAULTS["hum"]

    if "flow" in name:
        return THRESHOLD_DEFAULTS["flow"]

    if "press" in name or "pressure" in name:
        return THRESHOLD_DEFAULTS["pressure"]

    return THRESHOLD_DEFAULTS["generic"]


def configured_readings(service_config: JsonDict) -> list[JsonDict]:
    """Return explicit reading definitions from a service config.

    `readings` is required. The generator intentionally does not guess reading
    names from parser type because that made the system too lab-specific.
    """

    readings = service_config.get("readings")
    if isinstance(readings, list):
        return [reading for reading in readings if isinstance(reading, dict) and reading.get("name")]

    raise ValueError(
        f"Service {service_config.get('device_name', '<unnamed>')} is missing a readings list"
    )


def reading_threshold(reading: JsonDict) -> JsonDict:
    """Return a reading alarm config, ignoring malformed values."""

    threshold = reading.get("alarm", {})
    return threshold if isinstance(threshold, dict) else {}


def threshold_mode(reading_name: str, reading: JsonDict) -> str:
    """Return the threshold mode for one reading after config/default merging."""

    threshold = reading_threshold(reading)
    return str(threshold.get("mode", reading_defaults(reading_name)["mode"]))


def make_threshold_entities(reading_id: str, reading: JsonDict) -> list[tuple[str, JsonDict]]:
    """Build Home Assistant input_number helpers for min/max thresholds.

    Home Assistant cannot edit a paired min/max value as a single native helper,
    so range readings become two `input_number` helpers.
    """

    defaults = reading_defaults(reading_id)
    threshold = reading_threshold(reading)
    mode = threshold.get("mode", defaults["mode"])
    entities = []

    for kind, default_key in (("minimum", "min"), ("maximum", "max")):
        if kind == "minimum" and mode not in {"min", "range"}:
            continue
        if kind == "maximum" and mode not in {"max", "range"}:
            continue

        entities.append(
            (
                f"labpulse_{reading_id}_{kind}_threshold",
                threshold_entity_config(kind, default_key, reading_id, reading, threshold, defaults),
            )
        )

    return entities


def threshold_entity_config(
    kind: str,
    default_key: str,
    reading_id: str,
    reading: JsonDict,
    threshold: JsonDict,
    defaults: JsonDict,
) -> JsonDict:
    """Return the shared `input_number` config for one threshold helper."""

    return {
        "name": f"{reading.get('label', title(reading_id))} {title(kind)} Threshold",
        "min": threshold.get("range_min", defaults["range_min"]),
        "max": threshold.get("range_max", defaults["range_max"]),
        "step": threshold.get("step", defaults["step"]),
        "initial": threshold.get(default_key, defaults.get(default_key, defaults["range_max"])),
        "unit_of_measurement": threshold.get("unit", defaults["unit"]),
        "mode": "box",
    }


def build_reading_context(
    service_name: str,
    service_id: str,
    service_config: JsonDict,
    reading: JsonDict,
    entity_registry: EntityRegistry,
) -> ReadingContext:
    """Collect all generated ids and labels for one reading.

    The returned context is passed through the dashboard and automation modules
    so they do not need to know how MQTT unique IDs or Home Assistant entity IDs
    are derived.
    """

    reading_name = slug(str(reading["name"]))
    reading_key = f"{service_id}_{reading_name}"
    reading_label = str(reading.get("label") or title(reading_name))
    entity_id = str(
        reading.get("entity_id")
        or sensor_entity_id(
            service_name,
            service_config,
            reading_name,
            reading_key,
            reading_label,
            entity_registry,
        )
    )

    return ReadingContext(
        name=reading_name,
        key=reading_key,
        reading_id=reading_key,
        label=reading_label,
        mode=threshold_mode(reading_name, reading),
        entity_id=entity_id,
        active_entity=f"input_boolean.labpulse_{reading_key}_alert_active",
    )
