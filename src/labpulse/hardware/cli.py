import argparse
import logging
import time
from argparse import Namespace
from pathlib import Path

from labpulse.common.config import DEFAULT_CONFIG_PATH, get_service_config, load_config
from labpulse.common.logging_config import configure_logging
from labpulse.hardware.drivers.factory import build_driver
from labpulse.hardware.homeassistant_publisher import HomeAssistantMqttPublisher


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
    """Run one LabPulse service until stopped or until --once completes."""

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

    publisher = None

    if not args.no_mqtt:
        # Publishing is optional so parser/driver work can be tested without MQTT.
        publisher = HomeAssistantMqttPublisher(args.service, service_cfg, cfg.mqtt)
        publisher.connect()

    if not driver.setup():
        logger.error("Could not start service %s because the driver did not connect", args.service)

    last_status = driver.get_status()
    if publisher:
        publisher.publish_status(last_status)

    try:
        while True:
            measurements = driver.read()
            current_status = driver.get_status()

            if publisher and current_status != last_status:
                publisher.publish_status(current_status)
                last_status = current_status

            if not measurements:
                # Serial devices often produce blank lines while starting up.
                time.sleep(0.1)
                continue

            if args.print:
                logger.info("Measurements: %s", measurements)

            if publisher:
                publisher.publish(measurements)

            if args.once:
                break

    finally:
        driver.disconnect()

        if publisher:
            publisher.disconnect()


if __name__ == "__main__":
    main()
