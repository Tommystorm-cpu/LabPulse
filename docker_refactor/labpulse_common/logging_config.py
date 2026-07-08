"""Configure Docker-friendly logging for LabPulse services."""

import logging
import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = BASE_DIR / "logs"


def configure_logging(app_name: str = "labpulse", level: int = logging.INFO) -> Path | None:
    """
    Configure LabPulse logging for a running service.

    Logs always go to stdout so Docker can collect them. They are also written
    to a file unless LABPULSE_LOG_FILE is set to an empty string.
    """
    log_file = _get_log_file(app_name)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=handlers,
        force=True,
    )

    logging.getLogger("LabPulse").info("Logging to stdout and %s", log_file)
    return log_file


def _get_log_file(app_name: str) -> Path | None:
    """Return the configured log path, or None when file logging is disabled."""

    configured_file = os.getenv("LABPULSE_LOG_FILE")

    if configured_file == "":
        return None

    if configured_file:
        return Path(configured_file).expanduser().resolve()

    log_dir = Path(os.getenv("LABPULSE_LOG_DIR", DEFAULT_LOG_DIR)).expanduser()
    return (log_dir / f"{app_name}.log").resolve()
