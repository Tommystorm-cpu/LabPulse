"""Entrypoint for the LabPulse SMS container."""

import argparse
from argparse import Namespace
import logging
import os
from pathlib import Path
import signal
import sys

from labpulse_common.config import load_config
from labpulse_common.logging_config import configure_logging
from labpulse_sms.sender import SmsSender
from labpulse_sms.subscriber import RecentRequestCache, SMSSubscriber

APP_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = APP_DIR / "config.yaml"


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
    sender = SmsSender(cfg.sms.recipients, logger, dry_run=cfg.sms.dry_run)
    log_dir = Path(os.environ.get("LABPULSE_LOG_DIR", APP_DIR / "logs"))
    subscriber = SMSSubscriber(
        cfg.mqtt,
        sender,
        request_cache=RecentRequestCache(log_dir / "sms_processed_requests.json"),
    )

    def stop_service(_signum: int, _frame: object) -> None:
        """Interrupt the MQTT loop so finally can drain queued messages."""

        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop_service)
    signal.signal(signal.SIGINT, stop_service)
    try:
        subscriber.connect()
        subscriber.loop_forever()
    except KeyboardInterrupt:
        logger.info("SMS service stopping")
    finally:
        subscriber.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
