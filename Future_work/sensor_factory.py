import logging
import importlib
from typing import Dict

from labpulse_common.config import LabPulseConfig
from labpulse_common.sensor_base import BaseSensorDriver

class SensorFactory:
    """
    The Matchmaker. Reads the YAML config and dynamically loads
    the correct hardware driver for each sensor using a Plug-in architecture.
    """
    def __init__(self):
        self.logger = logging.getLogger("SensorFactory")

    def build_all(self, config: LabPulseConfig) -> Dict[str, BaseSensorDriver]:
        """
        Iterates through the YAML configuration and returns a dictionary 
        of fully initialized, ready-to-read hardware drivers.
        """
        active_sensors = {}

        for sensor_cfg in config.sensors:
            driver_name = sensor_cfg.driver.lower()
            sensor_id = sensor_cfg.id
            params = sensor_cfg.params

            try:
                # DYNAMIC IMPORT: It automatically looks for a file named "{driver_name}_driver.py"
                # Example: If YAML says "serial", it hunts for "serial_driver.py"
                module_path = f"labpulse_common.drivers.{driver_name}_driver"
                module = importlib.import_module(module_path)

                # We enforce that every driver file has a class named exactly 'Driver'
                driver_class = getattr(module, "Driver")

                # Instantiate the driver using the Phase 1 Contract
                sensor_instance = driver_class(name=sensor_id, config=params)
                active_sensors[sensor_id] = sensor_instance

                self.logger.info(f"[+] Loaded Plugin: {sensor_id} -> {driver_name}_driver.py")

            except ImportError:
                self.logger.error(f"[-] Missing Plugin: Cannot find {driver_name}_driver.py for {sensor_id}. Skipping.")
            except AttributeError:
                self.logger.error(f"[-] Malformed Plugin: {driver_name}_driver.py is missing the 'Driver' class. Skipping.")
            except Exception as e:
                self.logger.error(f"[-] Crash loading {sensor_id}: {e}")

        return active_sensors