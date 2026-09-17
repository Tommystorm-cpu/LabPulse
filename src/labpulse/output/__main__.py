"""Run one configured LabPulse physical-output service."""

import argparse
import logging
import signal

import paho.mqtt.client as mqtt

from labpulse.common.config import ConfigError, DEFAULT_CONFIG_PATH, format_config_error, load_config
from labpulse.common.logging_config import configure_logging
from labpulse.hardware.driver import HardwareOutputDriver
from labpulse.hardware.registry import get_driver_definition
from labpulse.output.service import OutputMqttService


def main(argv: list[str] | None = None) -> int:
    """Load one output, then listen for Home Assistant MQTT commands."""

    parser = argparse.ArgumentParser(description="Run one LabPulse output service")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to LabPulse config YAML")
    parser.add_argument("--output", required=True, help="Output name from config.yaml")
    args = parser.parse_args(argv)

    configure_logging(f"output-{args.output}")
    logger = logging.getLogger(f"LabPulse.Output.{args.output}")
    try:
        config = load_config(args.config).config
        output_config = config.outputs[args.output]
    except ConfigError as error:
        logger.critical("%s", format_config_error(error))
        return 1
    except KeyError:
        available = ", ".join(sorted(config.outputs))
        logger.critical("Unknown output %r; available outputs: %s", args.output, available or "none")
        return 1
    if not output_config.enabled:
        logger.critical("Output %r is disabled", args.output)
        return 1

    definition = get_driver_definition(output_config.driver.type)
    driver = definition.create_driver(args.output, output_config.driver.options)
    if not isinstance(driver, HardwareOutputDriver):
        logger.critical("Driver %s is not output-capable", definition.driver_id)
        return 1

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"LabPulse-Output-{args.output}",
        clean_session=True,
    )
    service = OutputMqttService(args.output, output_config, config.mqtt, driver, client)

    def stop_service(_signum: int, _frame: object) -> None:
        """Ask the worker loop to apply the safe state and stop."""

        service.stop()

    signal.signal(signal.SIGTERM, stop_service)
    signal.signal(signal.SIGINT, stop_service)
    try:
        service.run_forever()
    except (OSError, ValueError) as error:
        logger.critical("Output service failed: %s", error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
