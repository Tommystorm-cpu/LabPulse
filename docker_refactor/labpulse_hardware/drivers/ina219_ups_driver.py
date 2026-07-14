"""INA219-backed UPS telemetry driver for Raspberry Pi power monitoring."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from labpulse_hardware.drivers.base import BaseSensorDriver


REG_CONFIG = 0x00
REG_BUS_VOLTAGE = 0x02
REG_CURRENT = 0x04
REG_CALIBRATION = 0x05


def swap_word(value: int) -> int:
    """Swap a 16-bit register value for SMBus word byte order."""

    return ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)


def twos_complement(value: int, bits: int = 16) -> int:
    """Return the signed representation of an unsigned register value."""

    if value & (1 << (bits - 1)):
        return value - (1 << bits)
    return value


class Driver(BaseSensorDriver):
    """Read voltage/current from a configured INA219 UPS HAT."""

    def __init__(
        self,
        name: str,
        bus_number: int,
        address: int,
        empty_voltage: float,
        full_voltage: float,
        calibration_register: int,
        config_register: int,
        current_lsb_ma: float,
        read_interval_seconds: float = 1.0,
        reconnect_interval_seconds: float = 5.0,
        bus_factory: Callable[[int], Any] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Store verified HAT calibration and injectable I2C dependencies."""

        super().__init__(name)
        self.bus_number = bus_number
        self.address = address
        self.empty_voltage = empty_voltage
        self.full_voltage = full_voltage
        self.read_interval_seconds = read_interval_seconds
        self.reconnect_interval_seconds = reconnect_interval_seconds
        self.calibration_register = calibration_register
        self.config_register = config_register
        self.current_lsb_ma = current_lsb_ma
        self._bus_factory = bus_factory or self._default_bus_factory
        self._monotonic = monotonic
        self._sleep = sleep
        self.bus: Any | None = None
        self.last_reconnect_attempt = -reconnect_interval_seconds
        self.next_read_at = 0.0

    @staticmethod
    def _default_bus_factory(bus_number: int) -> Any:
        """Open an SMBus lazily so non-I2C tests do not require smbus2."""

        import smbus2

        return smbus2.SMBus(bus_number)

    def setup(self) -> bool:
        """Open and configure the INA219 device."""

        try:
            self.bus = self._bus_factory(self.bus_number)
            self._write_word(REG_CALIBRATION, self.calibration_register)
            self._write_word(REG_CONFIG, self.config_register)
        except (OSError, IOError, ImportError) as error:
            self.logger.error("Failed to configure INA219 at 0x%02X: %s", self.address, error)
            self._mark_disconnected()
            return False

        self.connected = True
        self.status = "online"
        self.next_read_at = self._monotonic()
        self.logger.info(
            "Connected to INA219 on I2C bus %s at 0x%02X",
            self.bus_number,
            self.address,
        )
        return True

    def read(self) -> dict[str, float] | None:
        """Return normalized UPS telemetry or reconnect after an I2C fault."""

        if not self.connected or self.bus is None:
            self._try_reconnect()
            return None

        now = self._monotonic()
        if now < self.next_read_at:
            self._sleep(self.next_read_at - now)

        try:
            raw_voltage = self._read_word(REG_BUS_VOLTAGE)
            raw_current = self._read_word(REG_CURRENT)
            voltage = ((raw_voltage >> 3) * 4) / 1000.0
            current_ma = twos_complement(raw_current) * self.current_lsb_ma
            self._validate_readings(voltage, current_ma)
        except (OSError, IOError, ValueError) as error:
            self.logger.error("INA219 read failed: %s", error)
            self._mark_disconnected()
            return None

        self.next_read_at = self._monotonic() + self.read_interval_seconds
        return {
            "voltage": round(voltage, 3),
            "current": round(current_ma, 1),
            "battery_level": self.battery_percentage(voltage),
        }

    def battery_percentage(self, voltage: float) -> float:
        """Return a clamped linear battery estimate from configured voltages."""

        percentage = (
            (voltage - self.empty_voltage)
            / (self.full_voltage - self.empty_voltage)
            * 100.0
        )
        return round(max(0.0, min(100.0, percentage)), 1)

    def disconnect(self) -> None:
        """Close the I2C handle and mark the device disconnected."""

        self._mark_disconnected(log_disconnect=True)

    def _read_word(self, register: int) -> int:
        """Read one INA219 register with correct SMBus byte order."""

        if self.bus is None:
            raise OSError("I2C bus is not open")
        return swap_word(int(self.bus.read_word_data(self.address, register)))

    def _write_word(self, register: int, value: int) -> None:
        """Write one INA219 register with correct SMBus byte order."""

        if self.bus is None:
            raise OSError("I2C bus is not open")
        self.bus.write_word_data(self.address, register, swap_word(value))

    @staticmethod
    def _validate_readings(voltage: float, current_ma: float) -> None:
        """Reject impossible values instead of publishing misleading telemetry."""

        if not 0.1 <= voltage <= 32.0:
            raise ValueError(f"impossible INA219 bus voltage: {voltage}")
        if not -10000.0 <= current_ma <= 10000.0:
            raise ValueError(f"impossible INA219 current: {current_ma}")

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
        """Close the current bus handle and update health state."""

        if self.bus is not None:
            try:
                self.bus.close()
            except (OSError, IOError, AttributeError) as error:
                self.logger.warning("Failed to close I2C bus: %s", error)
        self.bus = None
        self.connected = False
        self.status = "disconnected"
        if log_disconnect:
            self.logger.info("Disconnected from INA219")
