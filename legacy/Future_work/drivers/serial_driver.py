import serial
from typing import Dict, Any, Optional
from labpulse_common.sensor_base import BaseSensorDriver

class Driver(BaseSensorDriver):
    """
    The Universal Serial Driver for LabPulse 
    Automatically parses any pipe-delimited Arduino data (e.g., 'Flow1: 4.5 | Temp0: 22.1').
    """

    def __init__(self, name: str, config: Dict[str, Any]):
        super().__init__(name, config)
        # Pull specific connection settings from the YAML params
        self.port = self.config.get("port")
        self.baud_rate = self.config.get("baud_rate", 9600)
        self.ser = None

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

    def read(self) -> Optional[Dict[str, float]]:
        """Reads one line of data and parses it into a dictionary."""
        if not self.connected or not self.ser:
            return None

        try:
            line = self.ser.readline().decode('utf-8').strip()
            if not line:
                return None

            parsed_data = {}
            parts = line.split("|")
            
            for part in parts:
                if ":" in part:
                    try:
                        label, val_str = part.split(":")
                        
                        # NAMESPACE ISOLATION: 
                        # Combines the YAML ID with the Arduino label (e.g., 'pump_room_flow1')
                        key = f"{self.name}_{label.strip().lower()}"
                        
                        # Strip out random letters (C, L/min) and convert to clean float
                        val_clean = ''.join(c for c in val_str if c.isdigit() or c == '.' or c == '-')
                        parsed_data[key] = float(val_clean)
                        
                    except ValueError:
                        # Ignore malformed chunks
                        continue
                        
            return parsed_data if parsed_data else None

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