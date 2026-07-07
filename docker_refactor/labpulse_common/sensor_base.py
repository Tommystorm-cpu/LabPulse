from abc import ABC, abstractmethod
from typing import Any, Optional
import logging

class BaseSensorDriver(ABC):
    """
    The Abstract Base Class for all LabPulse v2.0 sensor drivers.
    Every hardware driver (Serial, I2C, GPIO, etc.) MUST inherit from this
    and implement these core methods.
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        """
        Initialize the sensor driver with its unique name and YAML config parameters.
        """
        self.name = name
        self.config = config
        self.connected = False
        self.status = "disconnected"
        self.logger = logging.getLogger(f"Driver.{self.name}")

    @abstractmethod
    def setup(self) -> bool:
        """
        Establish connection to the hardware (open COM port, init I2C bus, etc.).
        MUST return True if successfully connected, False otherwise.
        """
        pass

    @abstractmethod
    def read(self) -> Optional[dict[str, float]]:
        """
        Read data from the hardware.
        MUST return a dictionary of {metric_name: value} (e.g., {"pump_flow2": 4.5})
        or None if the read fails/times out.
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """
        Safely close connections and release hardware resources.
        """
        pass

    def get_status(self) -> str:
        """Return the current driver health/status string."""

        return self.status
