"""Command-line composition for one configured LabPulse hardware service."""

import argparse
import logging
from argparse import Namespace
from pathlib import Path

from labpulse.common.config import DEFAULT_CONFIG_PATH, ConfigError, format_config_error, load_config
from labpulse.common.logging_config import configure_logging
from labpulse.hardware.homeassistant_publisher import HomeAssistantMqttPublisher
from labpulse.hardware.registry import get_driver_definition
from labpulse.hardware.runner import HardwareServiceRunner, RunnerTimings


def parse_args() -> Namespace:
    """Parse CLI options for running one configured LabPulse service."""

    parser = argparse.ArgumentParser(description="Run one LabPulse service from config.yaml")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to LabPulse config YAML")
    parser.add_argument("--service", required=True, help="Service name from config.yaml, e.g. pump_room")
    parser.add_argument("--print", action="store_true", help="Print measurements to stdout")
    return parser.parse_args()


def main() -> None:
    """Compose and run one LabPulse hardware service."""

    # Parse the service name first so every startup message, including config
    # failures, is written to that service's own console and log file.
    args = parse_args()
    configure_logging(args.service)
    logger = logging.getLogger(f"HardwareServiceRunner.{args.service}")

    # Configuration is loaded exactly once at the process boundary. Everything
    # below receives validated models rather than reopening or parsing YAML.
    config_path = Path(args.config).expanduser().resolve()
    try:
        document = load_config(config_path)
        service_config = document.service(args.service)
    except ConfigError as error:
        logger.critical("%s", format_config_error(error))
        raise SystemExit(1) from error
    config = document.config

    # The registry turns the stable config ID into the selected driver's typed
    # declaration. Its options were already validated during config loading.
    driver_definition = get_driver_definition(service_config.driver.type)
    driver_config = service_config.driver.options

    read_interval_seconds = driver_definition.default_read_interval_seconds
    if service_config.read_interval_seconds is not None:
        read_interval_seconds = service_config.read_interval_seconds

    # Log the fully resolved runtime before opening hardware. This leaves a
    # useful diagnostic record even when the first connection attempt fails.
    target_fields = ("port", "pin", "bus", "address", "gpio_chip", "gpio_line")
    driver_options = driver_config.model_dump()
    target_parts = [f"{field}={driver_options[field]}" for field in target_fields if field in driver_options]
    target_summary = ", ".join(target_parts) or "driver-defined"
    logger.info(
        "Starting service=%s driver=%s target=(%s) config=%s "
        "read_interval=%.1fs reconnect_interval=%ss maximum_reading_age=%ss",
        args.service,
        driver_definition.driver_id,
        target_summary,
        config_path,
        read_interval_seconds,
        service_config.reconnect_interval_seconds,
        service_config.maximum_measurement_age_seconds,
    )
    driver = driver_definition.create_driver(args.service, driver_config)

    # MQTT is composed beside the driver, not hidden inside it.
    publisher = HomeAssistantMqttPublisher(args.service, service_config, config.mqtt)
    publisher.connect()

    # From this point onward the runner owns connection attempts, read timing,
    # freshness, status transitions, and cleanup. Drivers only translate their
    # hardware into HardwareReadings and the shared failure vocabulary.
    runner = HardwareServiceRunner(
        driver,
        publisher,
        RunnerTimings(
            reconnect_interval_seconds=service_config.reconnect_interval_seconds,
            maximum_measurement_age_seconds=service_config.maximum_measurement_age_seconds,
            read_interval_seconds=read_interval_seconds,
        ),
        print_measurements=args.print,
        logger=logger,
    )

    runner.run_forever()


if __name__ == "__main__":
    main()
