import argparse
import logging
import time
from argparse import Namespace
from pathlib import Path

from labpulse_common.config import get_service_config, load_config
from labpulse_common.logging_config import configure_logging
from labpulse_hardware.drivers.factory import SensorFactory
from labpulse_hardware.homeassistant_publisher import HomeAssistantMqttPublisher

APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = APP_DIR / "config.yaml"

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
        help="Print readings to stdout"
    )

    parser.add_argument(
        "--no-mqtt",
        action="store_true",
        help="Read and parse data without publishing to MQTT"
    )
    
    parser.add_argument(
        "--once",
        action="store_true",
        help="Read one valid reading and exit",
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

    factory = SensorFactory()
    driver = factory.build(args.service, service_cfg)
    logger.info("Created serial driver for %s: %s", args.service, driver)

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
            readings = driver.read()
            current_status = driver.get_status()

            if publisher and current_status != last_status:
                publisher.publish_status(current_status)
                last_status = current_status

            if not readings:
                # Serial devices often produce blank lines while starting up.
                time.sleep(0.1)
                continue

            if args.print:
                logger.info("Readings: %s", readings)

            if publisher:
                publisher.publish(readings)

            if args.once:
                break

    finally:
        driver.disconnect()

        if publisher:
            publisher.disconnect()


if __name__ == "__main__":
    main()
