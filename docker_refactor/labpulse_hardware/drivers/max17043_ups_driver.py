"""MAX17043-compatible UPS fuel-gauge driver for the installed live HAT."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from labpulse_hardware.drivers.base import BaseSensorDriver


REG_VCELL = 0x02
REG_SOC = 0x04


def register_word(data: list[int]) -> int:
    """Decode one big-endian two-byte MAX17043 register response."""

    if len(data) != 2 or any(not 0 <= value <= 0xFF for value in data):
        raise ValueError(f"invalid MAX17043 register response: {data!r}")
    return (data[0] << 8) | data[1]


def decode_voltage(raw: int) -> float:
    """Decode the MAX17043 VCELL register using its 1.25 mV scale."""

    return (raw >> 4) * 0.00125


def decode_state_of_charge(raw: int) -> float:
    """Decode the MAX17043 8.8 fixed-point state-of-charge register."""

    return raw / 256.0


class Driver(BaseSensorDriver):
    """Read real battery voltage and state of charge from the UPS fuel gauge."""

    def __init__(
        self,
        name: str,
        bus_number: int,
        address: int = 0x36,
        read_interval_seconds: float = 1.0,
        reconnect_interval_seconds: float = 5.0,
        bus_factory: Callable[[int], Any] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Store the verified bus identity and injectable I2C dependencies."""

        super().__init__(name)
        if address != 0x36:
            raise ValueError("MAX17043-compatible UPS gauge must use address 0x36")
        self.bus_number = bus_number
        self.address = address
        self.read_interval_seconds = read_interval_seconds
        self.reconnect_interval_seconds = reconnect_interval_seconds
        self._bus_factory = bus_factory or self._default_bus_factory
        self._monotonic = monotonic
        self._sleep = sleep
        self.bus: Any | None = None
        self.last_reconnect_attempt = -reconnect_interval_seconds
        self.next_read_at = 0.0

    @staticmethod
    def _default_bus_factory(bus_number: int) -> Any:
        """Open SMBus lazily so hardware-free tests do not require smbus2."""

        import smbus2

        return smbus2.SMBus(bus_number)

    def setup(self) -> bool:
        """Open the read-only fuel-gauge connection without writing registers."""

        try:
            self.bus = self._bus_factory(self.bus_number)
        except (OSError, IOError, ImportError) as error:
            self.logger.error(
                "Failed to open MAX17043 at 0x%02X: %s", self.address, error
            )
            self._mark_disconnected()
            return False

        self.connected = True
        self.status = "online"
        self.next_read_at = self._monotonic()
        self.logger.info(
            "Connected to MAX17043-compatible gauge on I2C bus %s at 0x%02X",
            self.bus_number,
            self.address,
        )
        return True

    def read(self) -> dict[str, float] | None:
        """Return voltage/SOC telemetry or enter reconnect mode after a fault."""

        if not self.connected or self.bus is None:
            self._try_reconnect()
            return None

        now = self._monotonic()
        if now < self.next_read_at:
            self._sleep(self.next_read_at - now)

        try:
            voltage = decode_voltage(self._read_register(REG_VCELL))
            # The 8.8 fixed-point SOC register can report slightly above 100%
            # at the top of charge. That is valid gauge telemetry, but the
            # user-facing percentage must remain bounded.
            battery_level = min(
                decode_state_of_charge(self._read_register(REG_SOC)),
                100.0,
            )
            self._validate_measurements(voltage, battery_level)
        except (OSError, IOError, ValueError) as error:
            self.logger.error("MAX17043 read failed: %s", error)
            self._mark_disconnected()
            return None

        self.next_read_at = self._monotonic() + self.read_interval_seconds
        return {
            "voltage": round(voltage, 3),
            "battery_level": round(battery_level, 1),
        }

    def disconnect(self) -> None:
        """Close the I2C handle and mark the gauge disconnected."""

        self._mark_disconnected(log_disconnect=True)

    def _read_register(self, register: int) -> int:
        """Read one register using the same transaction as the live service."""

        if self.bus is None:
            raise OSError("I2C bus is not open")
        data = self.bus.read_i2c_block_data(self.address, register, 2)
        return register_word([int(value) for value in data])

    @staticmethod
    def _validate_measurements(voltage: float, battery_level: float) -> None:
        """Reject values outside the physical single-cell/fuel-gauge range."""

        if not 2.0 <= voltage <= 5.0:
            raise ValueError(f"impossible MAX17043 battery voltage: {voltage}")
        if not 0.0 <= battery_level <= 100.0:
            raise ValueError(f"impossible MAX17043 state of charge: {battery_level}")

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
            self.logger.info("Disconnected from MAX17043-compatible gauge")
