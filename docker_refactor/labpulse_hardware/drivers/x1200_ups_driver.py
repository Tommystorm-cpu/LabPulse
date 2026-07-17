"""Geekworm X1200 UPS driver combining fuel-gauge and mains GPIO readings."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from labpulse_hardware.drivers.base import BaseSensorDriver
from labpulse_hardware.drivers.max17043_ups_driver import Driver as FuelGaugeDriver


CommandRunner = Callable[..., Any]


class GpiodLineReader:
    """Read one GPIO line with the libgpiod 1.x command-line interface."""

    def __init__(
        self,
        chip: str,
        line: int,
        active_high: bool = True,
        command_runner: CommandRunner = subprocess.run,
    ) -> None:
        """Store the configured GPIO identity and injectable process runner."""

        self.chip = chip
        self.line = line
        self.active_high = active_high
        self._command_runner = command_runner

    def read(self) -> float:
        """Return normalized mains presence as 1.0 or 0.0."""

        result = self._command_runner(
            ["gpioget", Path(self.chip).name, str(self.line)],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or f"gpioget exited {result.returncode}"
            raise OSError(detail)

        raw = result.stdout.strip()
        if raw not in {"0", "1"}:
            raise ValueError(f"unexpected gpioget output: {raw!r}")

        asserted = raw == "1"
        mains_present = asserted if self.active_high else not asserted
        return 1.0 if mains_present else 0.0


class Driver(BaseSensorDriver):
    """Publish X1200 battery telemetry and direct external-power state."""

    def __init__(
        self,
        name: str,
        bus_number: int,
        address: int,
        gpio_chip: str,
        gpio_line: int,
        mains_present_active_high: bool,
        read_interval_seconds: float = 1.0,
        reconnect_interval_seconds: float = 5.0,
        fuel_gauge: BaseSensorDriver | None = None,
        gpio_reader: GpiodLineReader | None = None,
    ) -> None:
        """Create the composite driver with injectable hardware components."""

        super().__init__(name)
        self.fuel_gauge = fuel_gauge or FuelGaugeDriver(
            name=name,
            bus_number=bus_number,
            address=address,
            read_interval_seconds=read_interval_seconds,
            reconnect_interval_seconds=reconnect_interval_seconds,
        )
        self.gpio_reader = gpio_reader or GpiodLineReader(
            gpio_chip,
            gpio_line,
            mains_present_active_high,
        )
        self._gpio_faulted = False

    def setup(self) -> bool:
        """Connect the fuel gauge; GPIO health is evaluated on every sample."""

        connected = self.fuel_gauge.setup()
        self.connected = connected
        self.status = self.fuel_gauge.get_status()
        return connected

    def read(self) -> dict[str, float] | None:
        """Return battery telemetry plus mains state when GPIO6 is readable."""

        readings = self.fuel_gauge.read()
        self.connected = self.fuel_gauge.connected
        if readings is None:
            self.status = self.fuel_gauge.get_status()
            return None

        try:
            readings["mains_present"] = self.gpio_reader.read()
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            if not self._gpio_faulted:
                self.logger.error("X1200 mains GPIO read failed: %s", error)
            self._gpio_faulted = True
            self.status = "gpio_fault"
            return readings

        if self._gpio_faulted:
            self.logger.info("X1200 mains GPIO reading recovered")
        self._gpio_faulted = False
        self.status = "online"
        return readings

    def disconnect(self) -> None:
        """Close the fuel-gauge connection and mark the composite offline."""

        self.fuel_gauge.disconnect()
        self.connected = False
        self.status = "disconnected"
