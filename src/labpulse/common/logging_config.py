"""Configure Docker-friendly logging for LabPulse services."""

import logging
from logging.handlers import TimedRotatingFileHandler
import os
import sys
from pathlib import Path

from labpulse.common.config import DEFAULT_CONFIG_PATH


DEFAULT_LOG_DIR = DEFAULT_CONFIG_PATH.parent / "logs"
LOG_RETENTION_DAYS = 7


def configure_logging(app_name: str = "labpulse", level: int = logging.INFO) -> Path | None:
    """
    Configure LabPulse logging for a running service.

    Logs always go to stdout so Docker can collect them. They are also written
    to a file unless LABPULSE_LOG_FILE is set to an empty string.
    """
    configured_file = os.getenv("LABPULSE_LOG_FILE")
    if configured_file == "":
        log_file = None
    elif configured_file:
        log_file = Path(configured_file).expanduser().resolve()
    else:
        log_dir = Path(os.getenv("LABPULSE_LOG_DIR", DEFAULT_LOG_DIR)).expanduser()
        log_file = (log_dir / f"{app_name}.log").resolve()

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # Keep the current file plus one dated file for each completed day in
        # the retention window. Rollover and old-file deletion happen inside
        # the worker, so the Pi does not need a separate cron or logrotate job.
        handlers.append(
            TimedRotatingFileHandler(
                log_file,
                when="midnight",
                interval=1,
                backupCount=LOG_RETENTION_DAYS,
                encoding="utf-8",
            )
        )

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S %z",
        handlers=handlers,
        force=True,
    )

    logging.getLogger("LabPulse").info("Logging to stdout and %s", log_file)
    return log_file
