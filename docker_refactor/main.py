import argparse
import json
import logging
import time
from pathlib import Path

import paho.mqtt.client as mqtt

from labpulse_common.config import get_service_config, load_config
from labpulse_common.logging_config import configure_logging
from labpulse_common.sensor_factory import SensorFactory

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config.yaml"
DISCOVERY_PREFIX = "homeassistant"
STATE_TOPIC_PREFIX = "home/sensor"

def parse_args():
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


def create_mqtt_client(service_name):
    return mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"LabPulse-{service_name}",
    )


def state_topic(service_name, metric_name):
    return f"{STATE_TOPIC_PREFIX}/{service_name}/{metric_name}/state"


def discovery_topic(service_name, metric_name):
    return f"{DISCOVERY_PREFIX}/sensor/{service_name}_{metric_name}/config"


def metric_label(metric_name):
    return metric_name.replace("_", " ").title()


def unit_for_metric(metric_name):
    if "pressure" in metric_name or "press" in metric_name:
        return "bar"

    if "temp" in metric_name:
        return "°C"

    if "hum" in metric_name:
        return "%"

    if "flow" in metric_name:
        return "L/min"

    return None


def publish_discovery(mqtt_client, service_name, service_config, readings, logger):
    for metric_name in readings:
        payload = {
            "name": metric_label(metric_name),
            "state_topic": state_topic(service_name, metric_name),
            "unique_id": f"{service_name}_{metric_name}",
            "device": {
                "identifiers": [service_name],
                "name": service_config.device_name,
            },
        }

        unit = unit_for_metric(metric_name)
        if unit:
            payload["unit_of_measurement"] = unit

        mqtt_client.publish(
            discovery_topic(service_name, metric_name),
            json.dumps(payload),
            retain=True,
        )
        logger.info("Published Home Assistant discovery for %s", metric_name)


def publish_readings(mqtt_client, service_name, readings, logger):
    for metric_name, reading in readings.items():
        mqtt_client.publish(state_topic(service_name, metric_name), reading)
        logger.info("Published %s reading: %s", metric_name, reading)


def main():
    args = parse_args()
    configure_logging(args.service)
    logger = logging.getLogger("Main")

    config_path = Path(args.config).expanduser().resolve()
    cfg = load_config(config_path)
    service_cfg = get_service_config(cfg, args.service)

    logger.info("Loaded config: %s", config_path)
    logger.info("Selected service: %s", args.service)

    factory = SensorFactory()
    driver = factory.build(args.service, service_cfg)
    logger.info("Created serial driver for %s: %s", args.service, driver)

    mqtt_client = None

    if not args.no_mqtt:
        mqtt_client = create_mqtt_client(args.service)
        logger.info("Connecting to MQTT broker %s:%s", cfg.mqtt.broker, cfg.mqtt.port)
        mqtt_client.connect(cfg.mqtt.broker, cfg.mqtt.port, 60)
        mqtt_client.loop_start()

    if not driver.setup():
        logger.error("Could not start service %s because the driver did not connect", args.service)
        return

    discovery_published = False

    try:
        while True:
            readings = driver.read()

            if not readings:
                time.sleep(0.1)
                continue

            if args.print:
                logger.info("Readings: %s", readings)

            if mqtt_client:
                if not discovery_published:
                    publish_discovery(mqtt_client, args.service, service_cfg, readings, logger)
                    discovery_published = True

                publish_readings(mqtt_client, args.service, readings, logger)

            if args.once:
                break

    finally:
        driver.disconnect()

        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()


if __name__ == "__main__":
    main()
