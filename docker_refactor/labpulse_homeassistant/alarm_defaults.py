"""Load and validate user-owned per-reading Home Assistant alarm defaults."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from labpulse_common.config import LabPulseConfig


class ReadingAlarmDefaults(BaseModel):
    """Initial editable threshold values for one ordinary sensor reading."""

    model_config = ConfigDict(extra="forbid")

    minimum: float
    maximum: float
    deadband: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "ReadingAlarmDefaults":
        """Require an ordered range with a non-overlapping recovery region."""

        if self.minimum >= self.maximum:
            raise ValueError("minimum must be less than maximum")
        if self.deadband * 2 > self.maximum - self.minimum:
            raise ValueError("deadband is too large for the minimum/maximum range")
        return self


class AlarmDefaultsFile(BaseModel):
    """Validated root shape of alarm_defaults.json."""

    model_config = ConfigDict(extra="forbid")

    services: dict[str, dict[str, ReadingAlarmDefaults]]


AlarmDefaults = dict[tuple[str, str], ReadingAlarmDefaults]


def load_alarm_defaults(path: Path, config: LabPulseConfig) -> AlarmDefaults:
    """Load defaults and require every enabled ordinary reading exactly once."""

    if not path.exists():
        raise FileNotFoundError(
            f"Alarm defaults file not found: {path}. "
            "Create it from the alarm_defaults.json starter template."
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {path}: {error}") from error

    parsed = AlarmDefaultsFile.model_validate(raw)
    result: AlarmDefaults = {}

    for service_name, readings in parsed.services.items():
        service = config.services.get(service_name)
        if service is None:
            raise ValueError(
                f"alarm_defaults.json references unknown service '{service_name}'"
            )
        if service.power_detection is not None:
            raise ValueError(
                f"alarm_defaults.json must not define dedicated power service "
                f"'{service_name}'"
            )
        known_readings = {reading.name for reading in service.readings}
        unknown = sorted(set(readings).difference(known_readings))
        if unknown:
            raise ValueError(
                f"alarm_defaults.json service '{service_name}' references unknown "
                f"readings: {', '.join(unknown)}"
            )
        result.update(
            ((service_name, reading_name), defaults)
            for reading_name, defaults in readings.items()
        )

    missing = [
        f"{service_name}.{reading.name}"
        for service_name, service in config.services.items()
        if service.enabled and service.power_detection is None
        for reading in service.readings
        if (service_name, reading.name) not in result
    ]
    if missing:
        raise ValueError(
            "alarm_defaults.json is missing enabled readings: "
            + ", ".join(sorted(missing))
        )

    return result
