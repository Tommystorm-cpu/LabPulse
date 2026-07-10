"""File-backed fake DHT11 driver for test Raspberry Pi deployments."""

from pathlib import Path
from typing import Any, Optional
import time

from labpulse_hardware.drivers.base import BaseSensorDriver


class Driver(BaseSensorDriver):
    """Read fake DHT11 temperature and humidity values from an env-style file."""

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        """Create a fake DHT11 driver from a state file path."""

        super().__init__(name, config)
        self.state_file = Path(str(config["state_file"]))
        self.read_interval_seconds = float(config.get("read_interval_seconds", 2.0))
        self.last_read_at = 0.0
        self.sample_count = 0

    def setup(self) -> bool:
        """Create the fake state file if needed and mark the driver online."""

        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.state_file.exists():
            self.state_file.write_text("mode=live\ntemperature=21.5\nhumidity=48.0\n", encoding="utf-8")

        self.connected = True
        self.status = "online"
        self.logger.info("Fake DHT11 state file: %s", self.state_file)
        return True

    def read(self) -> Optional[dict[str, float]]:
        """Return fake temperature and humidity readings from the state file."""

        if not self.connected:
            return None

        now = time.monotonic()
        if now - self.last_read_at < self.read_interval_seconds:
            return None

        self.last_read_at = now

        try:
            values = self._read_state_file()
        except Exception as error:
            self.status = "error"
            self.logger.error("Could not read fake DHT11 state file %s: %s", self.state_file, error)
            return None

        try:
            temperature = float(values["temperature"])
            humidity = float(values["humidity"])
        except KeyError as error:
            self.status = "error"
            self.logger.error("Fake DHT11 state file is missing %s", error)
            return None
        except ValueError as error:
            self.status = "error"
            self.logger.error("Fake DHT11 state file has non-numeric values: %s", error)
            return None

        self.status = "online"
        if values.get("mode", "live").strip().lower() != "stale":
            # Home Assistant stale checks use last_updated, which only changes
            # when the sensor state changes. Nudge live fake values so ordinary
            # fake testing does not look stale.
            wobble = 0.1 if self.sample_count % 2 else 0.0
            temperature += wobble
            humidity += wobble
            self.sample_count += 1

        return {
            "temperature": round(temperature, 1),
            "humidity": round(humidity, 1),
        }

    def disconnect(self) -> None:
        """Mark the fake driver disconnected."""

        self.connected = False
        self.status = "disconnected"

    def _read_state_file(self) -> dict[str, str]:
        """Parse key=value lines from the fake state file."""

        result: dict[str, str] = {}
        for raw_line in self.state_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue

            if "=" not in line:
                raise ValueError(f"invalid line {raw_line!r}; expected key=value")

            key, value = line.split("=", 1)
            result[key.strip()] = value.strip()

        return result
