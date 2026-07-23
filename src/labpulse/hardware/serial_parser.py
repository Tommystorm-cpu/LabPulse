"""Parse the standard LabPulse pipe-delimited Arduino serial format."""

import math
from typing import Optional


class SerialParser:
    """Convert one pipe-delimited serial line into finite measurements."""

    def parse(self, line: str) -> Optional[dict[str, float]]:
        """Return valid measurements, or ``None`` for an unusable line."""

        parsed: dict[str, float] = {}
        for part in line.strip().split("|"):
            if ":" not in part:
                continue

            label, raw_value = part.split(":", 1)
            name = self._measurement_name(label)
            value = self._finite_float(raw_value)
            if name is not None and value is not None:
                parsed[name] = value

        return parsed if parsed else None

    @staticmethod
    def _measurement_name(label: str) -> Optional[str]:
        """Normalize a non-empty measurement name to lowercase."""

        name = label.strip().lower()
        return name if name else None

    @staticmethod
    def _finite_float(raw_value: str) -> Optional[float]:
        """Parse one unit-free finite value; ``null`` is intentionally absent."""

        try:
            value = float(raw_value.strip())
        except ValueError:
            return None
        return value if math.isfinite(value) else None
