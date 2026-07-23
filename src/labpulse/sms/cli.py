"""Entrypoint for the LabPulse SMS container."""

import argparse
from argparse import Namespace
import logging
import os
from pathlib import Path
import signal
import sys

from labpulse.common.config import DEFAULT_CONFIG_PATH, load_config
from labpulse.common.logging_config import configure_logging
from labpulse.sms.sender import SmsSender
from labpulse.sms.subscriber import RecentRequestCache, SMSSubscriber
from labpulse.sms.subscriptions import SmsCommandMonitor, SubscriptionRegistry

APP_DIR = DEFAULT_CONFIG_PATH.parent


def parse_args(argv: list[str] | None = None) -> Namespace:
    """Parse SMS service command-line options."""

    parser = argparse.ArgumentParser(description="Run the SMS service")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to LabPulse config YAML",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Start the SMS subscriber and block on MQTT traffic."""

    args = parse_args(argv)
    configure_logging("sms")
    cfg = load_config(args.config)

    logger = logging.getLogger("LabPulse.SMS")
    log_dir = Path(os.environ.get("LABPULSE_LOG_DIR", APP_DIR / "logs"))
    subscription_registry = SubscriptionRegistry(
        [*cfg.sms.recipients, *cfg.sms.test_recipients],
        log_dir / "sms_subscriptions.json",
    )
    sender = SmsSender(
        cfg.sms.recipients,
        logger,
        test_recipients=cfg.sms.test_recipients,
        dry_run=cfg.sms.dry_run,
        subscription_registry=subscription_registry,
    )
    subscriber = SMSSubscriber(
        cfg.mqtt,
        sender,
        request_cache=RecentRequestCache(log_dir / "sms_processed_requests.json"),
    )
    command_monitor = None
    if not cfg.sms.dry_run:
        command_monitor = SmsCommandMonitor(sender, subscription_registry, logger)

    def stop_service(_signum: int, _frame: object) -> None:
        """Interrupt the MQTT loop so finally can drain queued messages."""

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
    sys.exit(main())
