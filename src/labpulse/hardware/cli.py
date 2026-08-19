"""Command-line composition for one configured LabPulse hardware service."""

import argparse
import logging
from argparse import Namespace
from pathlib import Path

from pydantic import BaseModel

from labpulse.common.config import (
    DEFAULT_CONFIG_PATH,
    ConfigError,
    format_config_error,
    load_config,
)
from labpulse.common.logging_config import configure_logging
from labpulse.hardware.registry import get_driver_spec
from labpulse.hardware.homeassistant_publisher import HomeAssistantMqttPublisher
from labpulse.hardware.runner import HardwareRunner, RunnerPolicy


def parse_args() -> Namespace:
    """Parse CLI options for running one configured LabPulse service."""

    parser = argparse.ArgumentParser(
        description="Run one LabPulse service from config.yaml"
    )

    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to LabPulse config YAML",
    )

    parser.add_argument(
        "--service",
        required=True,
        help="Service name from config.yaml, e.g. pump_room",
    )

    parser.add_argument(
        "--print",
        action="store_true",
        help="Print measurements to stdout",
    )

    parser.add_argument(
        "--no-mqtt",
        action="store_true",
        help="Read and parse data without publishing to MQTT",
    )
    
    parser.add_argument(
        "--once",
        action="store_true",
        help="Read one valid measurement and exit",
    )

    return parser.parse_args()


def _target_summary(options: BaseModel) -> str:
    """Describe configured hardware identities without dumping arbitrary options."""

    fields = ("port", "pin", "bus", "address", "gpio_chip", "gpio_line")
    values = options.model_dump()
    parts = [f"{field}={values[field]}" for field in fields if field in values]
    return ", ".join(parts) or "driver-defined"


def main() -> None:
    """Compose and run one LabPulse hardware service."""

    # Parse the service name first so every startup message, including config
    # failures, is written to that service's own console and log file.
    args = parse_args()
    configure_logging(args.service)
    logger = logging.getLogger(f"HardwareRunner.{args.service}")

    # Configuration is loaded exactly once at the process boundary. Everything
    # below receives validated models rather than reopening or parsing YAML.
    config_path = Path(args.config).expanduser().resolve()
    try:
        document = load_config(config_path)
        service_cfg = document.service(args.service)
    except ConfigError as error:
        logger.critical("%s", format_config_error(error))
        raise SystemExit(1) from error
    cfg = document.config

    # The registry turns the stable config ID into the selected driver's typed
    # declaration. Its options were already validated during config loading.
    driver_spec = get_driver_spec(service_cfg.driver.type)
    driver_options = service_cfg.driver.options

    # A service-level interval is an explicit override; otherwise the hardware
    # module supplies the safe default appropriate to that device or transport.
    read_interval_seconds = (
        service_cfg.read_interval_seconds
        if service_cfg.read_interval_seconds is not None
        else driver_spec.default_read_interval_seconds
    )

    # Log the fully resolved runtime before opening hardware. This leaves a
    # useful diagnostic record even when the first connection attempt fails.
    logger.info(
        "Starting service=%s driver=%s target=(%s) config=%s "
        "read_interval=%.1fs reconnect_interval=%ss maximum_reading_age=%ss",
        args.service,
        driver_spec.driver_id,
        _target_summary(driver_options),
        config_path,
        read_interval_seconds,
        service_cfg.reconnect_interval_seconds,
        service_cfg.maximum_measurement_age_seconds,
    )
    driver = driver_spec.create(args.service, driver_options)

    # MQTT is composed beside the driver, not inside it. --no-mqtt therefore
    # exercises the exact same hardware path during local and bench testing.
    publisher: HomeAssistantMqttPublisher | None = None
    if not args.no_mqtt:
        publisher = HomeAssistantMqttPublisher(args.service, service_cfg, cfg.mqtt)
        publisher.connect()

    # From this point onward the runner owns connection attempts, read timing,
    # freshness, status transitions, and cleanup. Drivers only translate their
    # hardware into ReadingBatch values and the shared failure vocabulary.
    runner = HardwareRunner(
        driver,
        publisher,
        RunnerPolicy(
            reconnect_interval_seconds=service_cfg.reconnect_interval_seconds,
            maximum_measurement_age_seconds=(
                service_cfg.maximum_measurement_age_seconds
            ),
            read_interval_seconds=read_interval_seconds,
        ),
        print_measurements=args.print,
        logger=logger,
    )

    # run_forever() also owns final cleanup, including the early --once path.
    runner.run_forever(once=args.once)


if __name__ == "__main__":
    main()
