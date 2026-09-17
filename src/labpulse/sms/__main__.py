"""Run the LabPulse SMS service."""

import argparse
import logging
import os
from pathlib import Path
import signal

from labpulse.common.config import ConfigError, DEFAULT_CONFIG_PATH, format_config_error, load_config
from labpulse.common.logging_config import configure_logging
from labpulse.sms.sender import SmsCommandMonitor, SmsSender, SubscriptionRegistry
from labpulse.sms.subscriber import SmsSubscriber


APP_DIR = DEFAULT_CONFIG_PATH.parent


def main(argv: list[str] | None = None) -> int:
    """Start the SMS subscriber and block on MQTT traffic."""

    parser = argparse.ArgumentParser(description="Run the SMS service")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="Path to LabPulse config YAML")
    args = parser.parse_args(argv)

    configure_logging("sms")
    logger = logging.getLogger("LabPulse.SMS")
    try:
        config = load_config(args.config).config
    except ConfigError as error:
        logger.critical("%s", format_config_error(error))
        return 1

    log_dir = Path(os.environ.get("LABPULSE_LOG_DIR", APP_DIR / "logs"))
    subscription_registry = SubscriptionRegistry(
        [*config.sms.recipients, *config.sms.test_recipients],
        log_dir / "sms_subscriptions.json",
    )
    sender = SmsSender(
        config.sms.recipients,
        logger,
        subscription_registry=subscription_registry,
        test_recipients=config.sms.test_recipients,
        dry_run=config.sms.dry_run,
    )
    subscriber = SmsSubscriber(config.mqtt, sender, log_dir / "sms_processed_requests.json")
    command_monitor = None if config.sms.dry_run else SmsCommandMonitor(sender, subscription_registry, logger)

    def stop_service(_signum: int, _frame: object) -> None:
        """Interrupt the MQTT loop so cleanup can drain queued messages."""

        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_service)
    signal.signal(signal.SIGINT, stop_service)
    try:
        if command_monitor is not None:
            command_monitor.start()
        subscriber.connect()
        subscriber.loop_forever()
    except KeyboardInterrupt:
        logger.info("SMS service stopping")
    finally:
        if command_monitor is not None:
            command_monitor.close()
        subscriber.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
