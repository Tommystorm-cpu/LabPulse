"""Safe in-memory hardware used by the complete fake-hardware deployment."""

from __future__ import annotations

from collections.abc import Mapping
import math

from labpulse.common.measurement_config import MeasurementConfig
from labpulse.hardware.driver import ConnectionLost, HardwareDriver, HardwareOutputDriver, HardwareReadings


def sensible_measurement_value(
    measurement_name: str,
    config: MeasurementConfig,
    sample_number: int,
) -> float:
    """Return a plausible, gently changing value from display metadata."""

    identity = f"{measurement_name} {config.device_class or ''} {config.unit or ''}".lower()
    if config.gpio_line is not None or any(
        word in identity for word in ("present", "active", "enabled", "switch", "contact")
    ):
        return 1.0

    if "battery" in identity or config.unit == "%" and "humid" not in identity:
        base, variation = 95.0, 0.2
    elif "humid" in identity:
        base, variation = 50.0, 1.0
    elif "temp" in identity or config.device_class == "temperature":
        base, variation = 20.0, 0.3
    elif "press" in identity or config.device_class == "pressure":
        if config.unit == "Pa":
            base, variation = 101325.0, 50.0
        elif config.unit == "kPa":
            base, variation = 101.3, 0.2
        elif config.unit == "MPa":
            base, variation = 0.12, 0.003
        else:
            base, variation = 1.2, 0.03
    elif "flow" in identity:
        base, variation = 3.0, 0.1
    elif "voltage" in identity or config.device_class == "voltage":
        base, variation = 4.1, 0.02
    elif "current" in identity or config.device_class == "current":
        base, variation = 1.0, 0.03
    elif "power" in identity or config.device_class == "power":
        base, variation = 100.0, 2.0
    elif "frequency" in identity or config.unit == "Hz":
        base, variation = 50.0, 0.05
    else:
        base, variation = 10.0, 0.2

    phase = sum(ord(character) for character in measurement_name) % 23
    value = base + variation * math.sin((sample_number + phase) / 5)
    precision = config.precision if config.precision is not None else 3
    return round(value, precision)


class SimulatedHardwareDriver(HardwareDriver):
    """Publish every configured measurement without accessing its real driver."""

    def __init__(
        self,
        service_name: str,
        measurements: Mapping[str, MeasurementConfig],
    ) -> None:
        """Retain the complete configured measurement set for this service."""

        super().__init__(service_name)
        self.measurements = dict(measurements)
        self._connected = False
        self._sample_number = 0

    def connect(self) -> None:
        """Open the in-memory source without touching host hardware."""

        self._connected = True
        self._sample_number = 0

    def read(self) -> HardwareReadings:
        """Return one value for every configured physical measurement."""

        if not self._connected:
            raise ConnectionLost("simulated hardware is not connected")
        self._sample_number += 1
        return HardwareReadings(
            {
                name: sensible_measurement_value(name, config, self._sample_number)
                for name, config in self.measurements.items()
            }
        )

    def close(self) -> None:
        """Close the in-memory source idempotently."""

        self._connected = False


class SimulatedOutputDriver(HardwareOutputDriver):
    """Retain output state in memory without changing Raspberry Pi hardware."""

    def __init__(self, output_name: str, safe_state: bool) -> None:
        """Create a disconnected output initialized to its configured safe state."""

        super().__init__(output_name)
        self._safe_state = safe_state
        self._state = safe_state
        self._connected = False

    @property
    def safe_state(self) -> bool:
        """Return the logical state used on startup and shutdown."""

        return self._safe_state

    def connect(self) -> None:
        """Connect the in-memory output in its safe state."""

        self._connected = True
        self._state = self._safe_state

    def set_state(self, active: bool) -> None:
        """Store one logical state without accessing a physical device."""

        if not self._connected:
            raise ConnectionLost("simulated output is not connected")
        self._state = active

    def read(self) -> HardwareReadings:
        """Return the current in-memory logical state."""

        if not self._connected:
            raise ConnectionLost("simulated output is not connected")
        return HardwareReadings({"state": 1.0 if self._state else 0.0})

    def close(self) -> None:
        """Return to the safe state and close the in-memory output."""

        self._state = self._safe_state
        self._connected = False
