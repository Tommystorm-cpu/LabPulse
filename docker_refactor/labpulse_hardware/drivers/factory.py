"""Build LabPulse sensor drivers from validated service config."""

import logging

from labpulse_common.config import ServiceConfig
from labpulse_hardware.drivers.base import BaseSensorDriver
from labpulse_hardware.drivers.dht11_driver import Driver as Dht11Driver
from labpulse_hardware.drivers.fake_dht11_driver import Driver as FakeDht11Driver
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
        Build a Raspberry Pi GPIO-backed service driver.
        """
        if service_config.gpio_sensor == "dht11":
            driver_config = self._build_dht11_driver_config(service_name, service_config)
            self.logger.info("Loaded DHT11 GPIO driver for %s", service_name)
            return Dht11Driver(name=service_name, config=driver_config)

        if service_config.gpio_sensor == "fake_dht11":
            driver_config = self._build_fake_dht11_driver_config(service_name, service_config)
            self.logger.info("Loaded fake DHT11 GPIO driver for %s", service_name)
            return FakeDht11Driver(name=service_name, config=driver_config)

        raise ValueError(
            f"GPIO service '{service_name}' must set gpio_sensor to a supported value: dht11, fake_dht11"
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

    def _build_dht11_driver_config(
        self,
        service_name: str,
        service_config: ServiceConfig,
    ) -> dict[str, object]:
        """Convert service config into dht11_driver.py's config shape."""

        if not service_config.gpio_pin:
            raise ValueError(f"DHT11 GPIO service '{service_name}' is missing gpio_pin")

        return {
            "pin": service_config.gpio_pin,
            "read_interval_seconds": service_config.read_interval_seconds or 2.0,
        }

    def _build_fake_dht11_driver_config(
        self,
        service_name: str,
        service_config: ServiceConfig,
    ) -> dict[str, object]:
        """Convert service config into fake_dht11_driver.py's config shape."""

        state_file = service_config.fake_state_file or f"/tmp/labpulse-fake-dht11/{service_name}.env"
        return {
            "state_file": state_file,
            "read_interval_seconds": service_config.read_interval_seconds or 2.0,
        }
