"""Build LabPulse sensor drivers from validated service config."""

import logging

from labpulse_common.config import ServiceConfig
from labpulse_hardware.drivers.base import BaseSensorDriver
from labpulse_hardware.drivers.serial_driver import Driver as SerialDriver

class SensorFactory:
    """
    Builds the correct sensor driver for one configured LabPulse service.

    The factory keeps driver-specific construction in one place. Serial is
    implemented now; GPIO and I2C have placeholder methods ready for later.
    """
    def __init__(self) -> None:
        """Create a factory logger."""

        self.logger = logging.getLogger("SensorFactory")

    def build(self, service_name: str, service_config: ServiceConfig) -> BaseSensorDriver:
        """
        Create one driver instance for the selected service.

        service_name is the key from config.yaml, for example pump_room.
        service_config is the validated config object for that service.
        """
        if service_config.driver == "serial":
            return self._build_serial_driver(service_name, service_config)

        if service_config.driver == "gpio":
            return self._build_gpio_driver(service_name, service_config)

        if service_config.driver == "i2c":
            return self._build_i2c_driver(service_name, service_config)

        raise ValueError(
            f"Unsupported driver '{service_config.driver}' for service '{service_name}'."
        )

    def _build_serial_driver(
        self,
        service_name: str,
        service_config: ServiceConfig,
    ) -> BaseSensorDriver:
        """
        Build a USB serial driver for Arduino-backed services.
        """
        driver_config = self._build_serial_driver_config(service_name, service_config)
        self.logger.info("Loaded serial driver for %s", service_name)

        return SerialDriver(name=service_name, config=driver_config)

    def _build_gpio_driver(
        self,
        service_name: str,
        service_config: ServiceConfig,
    ) -> BaseSensorDriver:
        """
        Placeholder for Raspberry Pi GPIO-backed services.
        """
        raise NotImplementedError(
            f"GPIO driver support is not implemented yet for service '{service_name}'."
        )

    def _build_i2c_driver(
        self,
        service_name: str,
        service_config: ServiceConfig,
    ) -> BaseSensorDriver:
        """
        Placeholder for I2C-backed services.
        """
        raise NotImplementedError(
            f"I2C driver support is not implemented yet for service '{service_name}'."
        )

    def _build_serial_driver_config(
        self,
        service_name: str,
        service_config: ServiceConfig,
    ) -> dict[str, object]:
        """
        Convert the service config format into serial_driver.py's config shape.
        """
        if not service_config.serial_port:
            raise ValueError(f"Serial service '{service_name}' is missing serial_port")

        if not service_config.parser:
            raise ValueError(f"Serial service '{service_name}' is missing parser")

        # serial_driver.py intentionally receives a small driver-specific dict
        # rather than the full ServiceConfig object.
        return {
            "port": service_config.serial_port,
            "baud_rate": service_config.baud_rate,
            "parser": service_config.parser,
            "reconnect_interval_seconds": service_config.reconnect_interval_seconds,
        }
