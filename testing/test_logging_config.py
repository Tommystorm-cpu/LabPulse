"""Tests for bounded persistent LabPulse service logging."""

import logging
import shutil
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from uuid import uuid4

from labpulse.common.logging_config import LOG_RETENTION_DAYS, configure_logging


TEST_TMP = Path(__file__).resolve().parent / "tmp"


def close_root_handlers() -> None:
    """Close handlers installed on the process-wide root logger by a test."""

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.close()
    root_logger.handlers.clear()


def test_file_logging_rotates_daily_and_expires_old_days(
    monkeypatch,
) -> None:
    """Keep only the configured daily history instead of one growing file."""

    log_directory = TEST_TMP / f"logging-{uuid4().hex}"
    log_directory.mkdir(parents=True)
    monkeypatch.setenv("LABPULSE_LOG_DIR", str(log_directory))
    monkeypatch.delenv("LABPULSE_LOG_FILE", raising=False)
    try:
        log_file = configure_logging("pressure")
        file_handlers = [
            handler
            for handler in logging.getLogger().handlers
            if isinstance(handler, TimedRotatingFileHandler)
        ]

        assert log_file == (log_directory / "pressure.log").resolve()
        assert len(file_handlers) == 1
        assert file_handlers[0].backupCount == LOG_RETENTION_DAYS
        assert file_handlers[0].interval == 24 * 60 * 60
    finally:
        close_root_handlers()
        shutil.rmtree(log_directory)


def test_empty_log_file_setting_keeps_stdout_only(monkeypatch) -> None:
    """Allow explicitly disabling the persistent file without adding rotation."""

    monkeypatch.setenv("LABPULSE_LOG_FILE", "")
    try:
        assert configure_logging("sms") is None
        assert not any(
            isinstance(handler, TimedRotatingFileHandler)
            for handler in logging.getLogger().handlers
        )
    finally:
        close_root_handlers()
