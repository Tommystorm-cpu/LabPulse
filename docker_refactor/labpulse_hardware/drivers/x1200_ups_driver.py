"""Geekworm X1200 UPS driver combining fuel-gauge and mains GPIO measurements."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from labpulse_hardware.drivers.base import BaseSensorDriver
from labpulse_hardware.drivers.max17043_ups_driver import Driver as FuelGaugeDriver


CommandRunner = Callable[..., Any]


class GpiodLineReader:
    """Read one GPIO line with either libgpiod command-line generation."""

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

        chip_name = Path(self.chip).name
        result = self._run_gpioget(["gpioget", "-c", chip_name, str(self.line)])
        if result.returncode != 0:
            legacy_result = self._run_gpioget(
                ["gpioget", chip_name, str(self.line)]
            )
            if legacy_result.returncode != 0:
                modern_detail = (
                    result.stderr.strip() or f"gpioget exited {result.returncode}"
                )
                legacy_detail = (
                    legacy_result.stderr.strip()
                    or f"gpioget exited {legacy_result.returncode}"
                )
                raise OSError(
                    f"libgpiod 2.x read failed: {modern_detail}; "
                    f"libgpiod 1.x read failed: {legacy_detail}"
                )
            result = legacy_result

        raw = result.stdout.strip()
        value = raw.rsplit("=", 1)[-1].strip().lower()
        if value not in {"0", "1", "active", "inactive"}:
            raise ValueError(f"unexpected gpioget output: {raw!r}")

        asserted = value in {"1", "active"}
        mains_present = asserted if self.active_high else not asserted
        return 1.0 if mains_present else 0.0

    def _run_gpioget(self, command: list[str]) -> Any:
        """Run one bounded gpioget attempt with consistent process options."""

        return self._command_runner(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )


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

        measurements = self.fuel_gauge.read()
        self.connected = self.fuel_gauge.connected
        if measurements is None:
            self.status = self.fuel_gauge.get_status()
            return None

        try:
            measurements["mains_present"] = self.gpio_reader.read()
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            if not self._gpio_faulted:
                self.logger.error("X1200 mains GPIO read failed: %s", error)
            self._gpio_faulted = True
            self.status = "gpio_fault"
            return measurements

        if self._gpio_faulted:
            self.logger.info("X1200 mains GPIO measurement recovered")
        self._gpio_faulted = False
        self.status = "online"
        return measurements

    def disconnect(self) -> None:
        """Close the fuel-gauge connection and mark the composite offline."""

        self.fuel_gauge.disconnect()
        self.connected = False
        self.status = "disconnected"
