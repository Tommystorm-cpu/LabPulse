import argparse
import logging
from argparse import Namespace
from pathlib import Path

from labpulse.common.config import DEFAULT_CONFIG_PATH, get_service_config, load_config
from labpulse.common.logging_config import configure_logging
from labpulse.hardware.registry import build_driver, get_driver_spec
from labpulse.hardware.homeassistant_publisher import HomeAssistantMqttPublisher
from labpulse.hardware.runner import HardwareRunner, RunnerPolicy


def parse_args() -> Namespace:
    """Parse CLI options for running one configured LabPulse service."""

    parser = argparse.ArgumentParser(description="Run one LabPulse service from config.yaml")

    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to LabPulse config YAML"
    )

    parser.add_argument(
        "--service",
        required=True,
        help="Service name from config.yaml, e.g pump_room"
    )

    parser.add_argument(
        "--print",
        action="store_true",
        help="Print measurements to stdout"
    )

    parser.add_argument(
        "--no-mqtt",
        action="store_true",
        help="Read and parse data without publishing to MQTT"
    )
    
    parser.add_argument(
        "--once",
        action="store_true",
        help="Read one valid measurement and exit",
    )

    return parser.parse_args()


def main() -> None:
    """Compose and run one LabPulse hardware service."""

    args = parse_args()
    configure_logging(args.service)
    logger = logging.getLogger("HardwareRunner")

    config_path = Path(args.config).expanduser().resolve()
    cfg = load_config(config_path)
    service_cfg = get_service_config(cfg, args.service)

    logger.info("Loaded config: %s", config_path)
    logger.info("Selected service: %s", args.service)

    driver = build_driver(args.service, service_cfg)
    logger.info("Created hardware driver for %s: %s", args.service, driver)

    publisher: HomeAssistantMqttPublisher | None = None

    if not args.no_mqtt:
        # Publishing is optional so parser/driver work can be tested without MQTT.
        publisher = HomeAssistantMqttPublisher(args.service, service_cfg, cfg.mqtt)
        publisher.connect()

    driver_spec = get_driver_spec(service_cfg.driver.type)
    read_interval_seconds = (
        service_cfg.read_interval_seconds
        if service_cfg.read_interval_seconds is not None
        else driver_spec.default_read_interval_seconds
    )

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
    runner.run_forever(once=args.once)


if __name__ == "__main__":
    main()
