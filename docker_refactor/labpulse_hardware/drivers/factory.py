"""Build LabPulse sensor drivers from validated service config."""

import logging

from labpulse_common.config import ServiceConfig
from labpulse_hardware.drivers.base import BaseSensorDriver
from labpulse_hardware.drivers.dht11_driver import Driver as Dht11Driver
from labpulse_hardware.drivers.ina219_ups_driver import Driver as Ina219UpsDriver
from labpulse_hardware.drivers.serial_driver import Driver as SerialDriver


logger = logging.getLogger("DriverFactory")


def build_driver(
    service_name: str,
    service_config: ServiceConfig,
) -> BaseSensorDriver:
    """Build the configured hardware driver for one service."""

    if service_config.driver == "serial":
        if not service_config.serial_port:
            raise ValueError(f"Serial service '{service_name}' is missing serial_port")

        if not service_config.parser:
            raise ValueError(f"Serial service '{service_name}' is missing parser")

        logger.info("Loaded serial driver for %s", service_name)
        return SerialDriver(
            name=service_name,
            port=service_config.serial_port,
            baud_rate=service_config.baud_rate,
            parser_type=service_config.parser,
            reconnect_interval_seconds=service_config.reconnect_interval_seconds,
        )

    if service_config.driver == "gpio":
        read_interval_seconds = service_config.read_interval_seconds or 2.0

        if service_config.gpio_sensor == "dht11":
            if not service_config.gpio_pin:
                raise ValueError(f"DHT11 GPIO service '{service_name}' is missing gpio_pin")

            logger.info("Loaded DHT11 GPIO driver for %s", service_name)
            return Dht11Driver(
                name=service_name,
                pin_name=service_config.gpio_pin,
                read_interval_seconds=read_interval_seconds,
            )

        raise ValueError(
            f"GPIO service '{service_name}' must set gpio_sensor to a supported value: "
            "dht11"
        )

    if service_config.driver == "i2c":
        if service_config.i2c_sensor == "ina219_ups":
            if service_config.i2c_bus is None or service_config.i2c_address is None:
                raise ValueError(f"INA219 service '{service_name}' is missing I2C settings")
            if service_config.battery_telemetry is None:
                raise ValueError(
                    f"INA219 service '{service_name}' is missing battery_telemetry"
                )
            if (
                service_config.ina219_calibration is None
                or service_config.ina219_config_register is None
                or service_config.ina219_current_lsb_ma is None
            ):
                raise ValueError(
                    f"INA219 service '{service_name}' is missing verified calibration"
                )
            logger.info("Loaded INA219 UPS driver for %s", service_name)
            return Ina219UpsDriver(
                name=service_name,
                bus_number=service_config.i2c_bus,
                address=service_config.i2c_address,
                empty_voltage=service_config.battery_telemetry.empty_voltage,
                full_voltage=service_config.battery_telemetry.full_voltage,
                read_interval_seconds=service_config.read_interval_seconds or 1.0,
                reconnect_interval_seconds=service_config.reconnect_interval_seconds,
                calibration_register=service_config.ina219_calibration,
                config_register=service_config.ina219_config_register,
                current_lsb_ma=service_config.ina219_current_lsb_ma,
            )
        raise ValueError(
            f"I2C service '{service_name}' must set i2c_sensor to a supported value: "
            "ina219_ups"
        )

    raise ValueError(
        f"Unsupported driver '{service_config.driver}' for service '{service_name}'."
    )
