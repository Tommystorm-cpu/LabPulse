from typing import Any, Optional

import serial

from labpulse_common.parser import SerialParser
from labpulse_common.sensor_base import BaseSensorDriver

class Driver(BaseSensorDriver):
    """
    USB serial driver for Arduino-backed LabPulse services.

    The driver reads raw serial lines and delegates format-specific parsing to
    SerialParser.
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        """Store serial settings and create the parser for this service."""

        super().__init__(name, config)

        # SensorFactory translates ServiceConfig into this driver-specific shape.
        self.port = self.config.get("port")
        self.baud_rate = self.config.get("baud_rate", 9600)
        self.ser = None
        self.parser_type = self.config.get("parser")
        self.parser = SerialParser(name, self.parser_type)

    def setup(self) -> bool:
        """Attempts to open the USB serial port."""
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=2)
            self.logger.info(f"Connected to {self.port} at {self.baud_rate} baud.")
            self.connected = True
            return True
        except serial.SerialException as e:
            self.logger.error(f"Failed to connect to {self.port}: {e}")
            self.connected = False
            return False

    def read(self) -> Optional[dict[str, float]]:
        """Reads one line of data and parses it into a dictionary."""
        if not self.connected or not self.ser:
            return None

        try:
            line = self.ser.readline().decode('utf-8').strip()
            if not line:
                return None

            return self.parser.parse(line)

        except serial.SerialException as e:
            self.logger.error(f"Hardware disconnected on {self.port}: {e}")
            self.connected = False
            return None

    def disconnect(self) -> None:
        """Safely releases the USB port."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.logger.info(f"Disconnected from {self.port}.")
        self.connected = False
