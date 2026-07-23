"""Geekworm X1200 UPS driver for battery-gauge and mains measurements."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from labpulse.hardware.drivers.base import BaseSensorDriver


REG_VCELL = 0x02
REG_SOC = 0x04
CommandRunner = Callable[..., Any]


def register_word(data: list[int]) -> int:
    """Decode one big-endian two-byte MAX17043 register response."""

    if len(data) != 2 or any(not 0 <= value <= 0xFF for value in data):
        raise ValueError(f"invalid MAX17043 register response: {data!r}")
    return (data[0] << 8) | data[1]


def decode_voltage(raw: int) -> float:
    """Decode the X1200 MAX17043 VCELL register using its 1.25 mV scale."""

    return (raw >> 4) * 0.00125


def decode_state_of_charge(raw: int) -> float:
    """Decode the X1200 MAX17043 8.8 fixed-point SOC register."""

    return raw / 256.0


class GpiodLineReader:
    """Read the X1200 mains-detection GPIO with either libgpiod CLI version."""

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
            legacy_result = self._run_gpioget(["gpioget", chip_name, str(self.line)])
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
        bus_factory: Callable[[int], Any] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        gpio_reader: GpiodLineReader | None = None,
    ) -> None:
        """Store the verified X1200 identities and injectable dependencies."""

        super().__init__(name)
        if address != 0x36:
            raise ValueError("X1200 MAX17043 fuel gauge must use address 0x36")
        self.bus_number = bus_number
        self.address = address
        self.read_interval_seconds = read_interval_seconds
        self.reconnect_interval_seconds = reconnect_interval_seconds
        self._bus_factory = bus_factory or self._default_bus_factory
        self._monotonic = monotonic
        self._sleep = sleep
        self.gpio_reader = gpio_reader or GpiodLineReader(
            gpio_chip,
            gpio_line,
            mains_present_active_high,
        )
        self.bus: Any | None = None
        self.last_reconnect_attempt = -reconnect_interval_seconds
        self.next_read_at = 0.0
        self._gpio_faulted = False

    @staticmethod
    def _default_bus_factory(bus_number: int) -> Any:
        """Open SMBus lazily so hardware-free tests do not require smbus2."""

        import smbus2

        return smbus2.SMBus(bus_number)

    def setup(self) -> bool:
        """Open the X1200 fuel-gauge connection without writing registers."""

        try:
            self.bus = self._bus_factory(self.bus_number)
        except (OSError, IOError, ImportError) as error:
            self.logger.error(
                "Failed to open X1200 MAX17043 at 0x%02X: %s",
                self.address,
                error,
            )
            self._mark_disconnected()
            return False

        self.connected = True
        self.status = "online"
        self.next_read_at = self._monotonic()
        self.logger.info(
            "Connected to X1200 on I2C bus %s at 0x%02X",
            self.bus_number,
            self.address,
        )
        return True

    def read(self) -> dict[str, float] | None:
        """Return battery and mains telemetry or reconnect after an I2C fault."""

        if not self.connected or self.bus is None:
            self._try_reconnect()
            return None

        now = self._monotonic()
        if now < self.next_read_at:
            self._sleep(self.next_read_at - now)

        try:
            voltage = decode_voltage(self._read_register(REG_VCELL))
            battery_level = min(
                decode_state_of_charge(self._read_register(REG_SOC)),
                100.0,
            )
            self._validate_measurements(voltage, battery_level)
        except (OSError, IOError, ValueError) as error:
            self.logger.error("X1200 fuel-gauge read failed: %s", error)
            self._mark_disconnected()
            return None

        self.next_read_at = self._monotonic() + self.read_interval_seconds
        measurements = {
            "voltage": round(voltage, 3),
            "battery_level": round(battery_level, 1),
        }

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
        """Close the I2C handle and mark the X1200 disconnected."""

        self._mark_disconnected(log_disconnect=True)

    def _read_register(self, register: int) -> int:
        """Read one MAX17043 register from the X1200."""

        if self.bus is None:
            raise OSError("I2C bus is not open")
        data = self.bus.read_i2c_block_data(self.address, register, 2)
        return register_word([int(value) for value in data])

    @staticmethod
    def _validate_measurements(voltage: float, battery_level: float) -> None:
        """Reject values outside the physical cell and fuel-gauge range."""

        if not 2.0 <= voltage <= 5.0:
            raise ValueError(f"impossible X1200 battery voltage: {voltage}")
        if not 0.0 <= battery_level <= 100.0:
            raise ValueError(f"impossible X1200 state of charge: {battery_level}")

    def _try_reconnect(self) -> bool:
        """Attempt I2C reconnection at the configured interval."""

        now = self._monotonic()
        if now - self.last_reconnect_attempt < self.reconnect_interval_seconds:
            return False
        self.last_reconnect_attempt = now
        self.status = "reconnecting"
        reconnected = self.setup()
        if not reconnected:
            self.status = "reconnecting"
        return reconnected

    def _mark_disconnected(self, log_disconnect: bool = False) -> None:
        """Close the current I2C handle and update health state."""

        if self.bus is not None:
            try:
                self.bus.close()
            except (OSError, IOError, AttributeError) as error:
                self.logger.warning("Failed to close X1200 I2C bus: %s", error)
        self.bus = None
        self.connected = False
        self.status = "disconnected"
        if log_disconnect:
            self.logger.info("Disconnected from X1200")
