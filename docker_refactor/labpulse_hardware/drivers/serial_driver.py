from typing import Optional
import time

import serial

from labpulse_hardware.drivers.base import BaseSensorDriver
from labpulse_hardware.serial_parser import SerialParser

class Driver(BaseSensorDriver):
    """
    USB serial driver for Arduino-backed LabPulse services.

    The driver reads standard pipe-delimited serial lines through SerialParser.
    """

    def __init__(
        self,
        name: str,
        port: str,
        baud_rate: int,
        reconnect_interval_seconds: float,
    ) -> None:
        """Store serial settings and create the parser for this service."""

        super().__init__(name)
        self.port = port
        self.baud_rate = baud_rate
        self.ser = None
        self.parser = SerialParser()
        self.reconnect_interval_seconds = reconnect_interval_seconds
        self.last_reconnect_attempt = 0.0

    def setup(self) -> bool:
        """Attempts to open the USB serial port."""
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=2)
            self.logger.info(f"Connected to {self.port} at {self.baud_rate} baud.")
            self.connected = True
            self.status = "online"
            return True
        except (serial.SerialException, OSError) as e:
            self.logger.error(f"Failed to connect to {self.port}: {e}")
            self._mark_disconnected()
            return False

    def read(self) -> Optional[dict[str, float]]:
        """Reads one line of data and parses it into a dictionary."""
        if not self.connected or not self.ser:
            self._try_reconnect()
            return None

        try:
            line = self.ser.readline().decode('utf-8').strip()
            if not line:
                return None

            return self.parser.parse(line)

        except (serial.SerialException, OSError) as e:
            self.logger.error(f"Serial connection lost on {self.port}: {e}")
            self._mark_disconnected()
            return None

    def disconnect(self) -> None:
        """Safely releases the USB port."""
        self._mark_disconnected(log_disconnect=True)

    def _should_attempt_reconnect(self) -> bool:
        """Return True when enough time has passed to try reconnecting."""
        now = time.monotonic()
        return now - self.last_reconnect_attempt >= self.reconnect_interval_seconds

    def _try_reconnect(self) -> bool:
        """Try to reopen the serial port, respecting the reconnect interval."""
        if not self._should_attempt_reconnect():
            return False

        self.last_reconnect_attempt = time.monotonic()
        self.status = "reconnecting"
        self.logger.info("Trying to reconnect to %s", self.port)

        reconnected = self.setup()

        if not reconnected:
            self.status = "reconnecting"

        return reconnected

    def _mark_disconnected(self, log_disconnect: bool = False) -> None:
        """Close any open serial handle and mark the driver disconnected."""
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except (serial.SerialException, OSError) as e:
                self.logger.warning(f"Failed to close serial port {self.port}: {e}")

            if log_disconnect:
                self.logger.info(f"Disconnected from {self.port}.")

        self.ser = None
        self.connected = False
        self.status = "disconnected"
