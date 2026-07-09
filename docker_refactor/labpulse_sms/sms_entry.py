"""Entrypoint for the LabPulse SMS container."""

import argparse
from argparse import Namespace
import logging
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
APP_DIR = SCRIPT_DIR.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from labpulse_common.config import load_config
from labpulse_common.logging_config import configure_logging
from labpulse_sms.sender import build_sms_sender
from labpulse_sms.sms_subscriber import SMSSubscriber

DEFAULT_CONFIG_PATH = APP_DIR / "config.yaml"


def parse_args() -> Namespace:
    """Parse SMS service command-line options."""

    parser = argparse.ArgumentParser(description="Run the SMS service")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Path to LabPulse config YAML",
    )
    return parser.parse_args()


def main() -> None:
    """Start the SMS subscriber and block on MQTT traffic."""

    args = parse_args()
    configure_logging("sms")
    cfg = load_config(args.config)

    sender = build_sms_sender(cfg.sms, logging.getLogger("HomeAssistantMqtt.SMS"))
    subscriber = SMSSubscriber(cfg.mqtt, sender)
    subscriber.connect()
    subscriber.loop_forever()


if __name__ == "__main__":
    main()
