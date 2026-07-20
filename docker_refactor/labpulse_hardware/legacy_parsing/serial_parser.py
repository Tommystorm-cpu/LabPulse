"""Parse unified and temporary legacy Arduino serial formats."""

import json
import math
import re
from typing import Optional


class SerialParser:
    """
    Parser for Arduino serial lines.

    Unified firmware is detected from its JSON envelope independently of
    parser type. The configured parser type remains the compatibility path for
    Arduinos that still run an older human-readable sketch.
    """

    def __init__(self, name: str, parser_type: str) -> None:
        """
        Create a parser for one configured LabPulse service.

        name identifies the service in logs; parsed measurement keys come from the
        Arduino labels and must match `measurements[].name` in config.yaml.
        parser_type selects the expected Arduino output format.
        """
        self.name = name
        self.parser_type = parser_type or "pipe"

        # Restrict labels to the names emitted by the current Arduino sketches.
        # This prevents unit text such as "L/minTemp0" being mistaken for a label.
        self.label_pattern = re.compile(
            r"(FlowRate|TotalLitres|RoomTemp|RoomHum|Voltage|BatteryLevel|mains_present|"
            r"Flow[0-9]+|Temp[0-9]+|Press[0-9]+):"
        )

    def parse(self, line: str) -> Optional[dict[str, float]]:
        """
        Parse one raw serial line into measurement/value pairs.

        Returns None when the line is empty, malformed, or not relevant to the
        configured parser type.
        """
        line = line.strip()

        if not line:
            return None

        if line.startswith("{"):
            return self._parse_json_record(line)

        if self.parser_type == "pressure":
            return self._parse_pressure(line)

        if self.parser_type in {"pump_room", "water", "ups_simulator"}:
            return self._parse_labelled_values(line)

        return self._parse_pipe_delimited(line)

    def _parse_json_record(self, line: str) -> Optional[dict[str, float]]:
        """Parse one schema-1 LabPulse firmware JSON record."""

        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return None

        if not isinstance(payload, dict):
            return None
        schema = payload.get("schema")
        if isinstance(schema, bool) or schema != 1:
            return None
        if payload.get("device") != self.name or payload.get("type") != "sample":
            return None

        measurements = payload.get("measurements")
        if not isinstance(measurements, dict):
            # Startup hello and future status records intentionally contain no
            # measurements and must not become telemetry.
            return None

        parsed: dict[str, float] = {}
        for measurement_name, raw_value in measurements.items():
            if not isinstance(measurement_name, str):
                continue
            if isinstance(raw_value, bool) or not isinstance(
                raw_value, (int, float)
            ):
                # JSON null represents an invalid sensor channel. Metadata and
                # diagnostics live outside measurements and are ignored entirely.
                continue
            value = float(raw_value)
            if math.isfinite(value):
                parsed[measurement_name] = value

        return parsed if parsed else None

    def _parse_pressure(self, line: str) -> Optional[dict[str, float]]:
        """
        Parse the compressed-air Arduino format.

        The Arduino prints one pressure value in MPa. LabPulse publishes bar,
        so the parsed value is multiplied by 10.
        """
        try:
            pressure_bar = round(float(line) * 10.0, 2)
        except ValueError:
            return None

        return {self._key("pressure"): pressure_bar}

    def _parse_labelled_values(self, line: str) -> Optional[dict[str, float]]:
        """
        Parse labelled Arduino values such as Flow1, Temp0, and RoomHum.

        This handles both clean lines:
            Flow1: 2.45 L/min | Flow2: 3.10 L/min

        and the current full-water sketch's combined line:
            Flow2: 3.10 L/minTemp0: 20.11C
        """
        parsed_data = {}
        labels = list(self.label_pattern.finditer(line))

        for index, match in enumerate(labels):
            label = match.group(1)
            value_start = match.end()

            # Values run until the next recognized label, not just to a pipe
            # separator. This is what lets us recover from "L/minTemp0".
            value_end = labels[index + 1].start() if index + 1 < len(labels) else len(line)
            raw_value = line[value_start:value_end]
            value = self._clean_float(raw_value)

            if value is None:
                continue

            parsed_data[self._key(label)] = value

        return parsed_data if parsed_data else None

    def _parse_pipe_delimited(self, line: str) -> Optional[dict[str, float]]:
        """
        Parse generic pipe-delimited label/value chunks.
        """
        parsed_data = {}

        for part in line.split("|"):
            if ":" not in part:
                continue

            label, raw_value = part.split(":", 1)
            value = self._clean_float(raw_value)

            if value is None:
                continue

            parsed_data[self._key(label)] = value

        return parsed_data if parsed_data else None

    def _key(self, label: str) -> str:
        """
        Convert an Arduino label into the config measurement key.

        Example: label Flow1 becomes flow1.
        """
        normalized = label.strip().lower()
        return {"batterylevel": "battery_level"}.get(normalized, normalized)

    def _clean_float(self, raw_value: str) -> Optional[float]:
        """
        Extract the first finite float from a labelled value string.

        Units such as C, %, bar, and L/min are ignored.
        """
        match = re.search(r"[-+]?\d+(?:\.\d+)?", raw_value)

        if not match:
            return None

        value = float(match.group(0))

        if math.isnan(value) or math.isinf(value):
            return None

        return value
