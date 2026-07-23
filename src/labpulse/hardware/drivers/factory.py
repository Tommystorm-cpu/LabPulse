"""Build LabPulse sensor drivers from validated service config."""

import logging

from labpulse.common.config import ServiceConfig
from labpulse.hardware.drivers.base import BaseSensorDriver


logger = logging.getLogger("DriverFactory")


def build_driver(
    service_name: str,
    service_config: ServiceConfig,
) -> BaseSensorDriver:
    """Build the configured hardware driver for one service."""

    if service_config.driver == "serial":
        from labpulse.hardware.drivers.serial_driver import Driver as SerialDriver

        if not service_config.serial_port:
            raise ValueError(f"Serial service '{service_name}' is missing serial_port")

        logger.info("Loaded serial driver for %s", service_name)
        return SerialDriver(
            name=service_name,
            port=service_config.serial_port,
            baud_rate=service_config.baud_rate,
            reconnect_interval_seconds=service_config.reconnect_interval_seconds,
        )

    if service_config.driver == "gpio":
        read_interval_seconds = service_config.read_interval_seconds or 2.0

        if service_config.gpio_sensor == "dht11":
            from labpulse.hardware.drivers.dht11_driver import Driver as Dht11Driver

            if not service_config.gpio_pin:
                raise ValueError(f"DHT11 GPIO service '{service_name}' is missing gpio_pin")

            logger.info("Loaded DHT11 GPIO driver for %s", service_name)
            return Dht11Driver(
                name=service_name,
                pin_name=service_config.gpio_pin,
                read_interval_seconds=read_interval_seconds,
                reconnect_interval_seconds=service_config.reconnect_interval_seconds,
                maximum_measurement_age_seconds=service_config.maximum_measurement_age_seconds,
            )

        raise ValueError(
            f"GPIO service '{service_name}' must set gpio_sensor to a supported value: "
            "dht11"
        )

    if service_config.driver == "i2c":
        if service_config.i2c_sensor == "x1200_ups":
            if service_config.i2c_bus is None or service_config.i2c_address is None:
                raise ValueError(f"X1200 service '{service_name}' is missing I2C settings")
            if service_config.power_detection is None:
                raise ValueError(f"X1200 service '{service_name}' is missing power_detection")
            from labpulse.hardware.drivers.x1200_ups_driver import Driver as X1200UpsDriver

            power = service_config.power_detection
            logger.info("Loaded X1200 UPS driver for %s", service_name)
            return X1200UpsDriver(
                name=service_name,
                bus_number=service_config.i2c_bus,
                address=service_config.i2c_address,
                gpio_chip=power.gpio_chip,
                gpio_line=power.gpio_line,
                mains_present_active_high=power.mains_present_active_high,
                read_interval_seconds=service_config.read_interval_seconds or 1.0,
                reconnect_interval_seconds=service_config.reconnect_interval_seconds,
            )
        raise ValueError(
            f"I2C service '{service_name}' must set i2c_sensor to a supported value: "
            "x1200_ups"
        )

    raise ValueError(
        f"Unsupported driver '{service_config.driver}' for service '{service_name}'."
    )
