"""SMS sender backends for the LabPulse SMS container."""

import logging
import queue
import re
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from typing import Protocol

from labpulse_common.config import SmsConfig


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class SmsSender(Protocol):
    """Common interface for asynchronous SMS sender backends."""

    def broadcast(self, message: str) -> None:
        """Queue one message for every configured recipient."""


def format_sms_message(request: dict[str, str]) -> str:
    """Create a readable SMS body from one MQTT request payload."""

    title = request.get("title", "LabPulse alert").strip()
    message = request.get("message", "").strip()
    service = request.get("service_label") or request.get("service")
    reading = request.get("reading_label") or request.get("reading")
    current = request.get("current")

    lines = [title]
    if message:
        lines.append(message)
    if service or reading:
        lines.append(" / ".join(part for part in [service, reading] if part))
    if current not in (None, "", "unknown", "None"):
        lines.append(f"Current: {current}")

    return "\n".join(lines)


class QueuedSmsSender:
    """Base class that serializes SMS sends through one worker thread."""

    def __init__(self, recipients: Sequence[str], logger: logging.Logger) -> None:
        """Store recipients and start the background send worker."""

        self.recipients = list(recipients)
        self.logger = logger
        self.queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.worker = threading.Thread(target=self._worker, daemon=True)
        self.worker.start()

    def broadcast(self, message: str) -> None:
        """Queue one outbound message for every configured recipient."""

        if not self.recipients:
            self.logger.warning("SMS request dropped because no recipients are configured")
            return

        for recipient in self.recipients:
            self.queue.put((recipient, message))

    def send_sms(self, phone_number: str, message: str) -> bool:
        """Send one SMS to one recipient."""

        raise NotImplementedError

    def _worker(self) -> None:
        """Send queued SMS messages one at a time."""

        while True:
            phone_number, message = self.queue.get()
            try:
                self.send_sms(phone_number, message)
            except Exception:
                self.logger.exception("Unexpected SMS sender failure")
            finally:
                self.queue.task_done()


class LogSmsSender(QueuedSmsSender):
    """SMS backend that logs messages without contacting a modem."""

    def send_sms(self, phone_number: str, message: str) -> bool:
        """Log the SMS that would be sent."""

        self.logger.info("SMS log backend would send to %s: %s", phone_number, message)
        return True


class MmcliSmsSender(QueuedSmsSender):
    """SMS backend that sends through ModemManager's mmcli command."""

    def __init__(
        self,
        recipients: Sequence[str],
        logger: logging.Logger,
        runner: CommandRunner = subprocess.run,
        retries: int = 3,
        retry_delay_seconds: float = 2.0,
    ) -> None:
        """Store mmcli settings and start the queued sender."""

        self.runner = runner
        self.retries = retries
        self.retry_delay_seconds = retry_delay_seconds
        super().__init__(recipients, logger)

    def send_sms(self, phone_number: str, message: str) -> bool:
        """Send one SMS through the first modem reported by mmcli."""

        for attempt in range(1, self.retries + 1):
            modem_id = self.get_modem_id()
            if modem_id is None:
                self.logger.error("No operational cellular modem found")
                return False

            try:
                sms_path = self.create_sms(modem_id, phone_number, message)
                self.runner(
                    ["mmcli", "-s", sms_path, "--send"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
            except subprocess.TimeoutExpired as error:
                self.logger.warning("SMS send timed out on attempt %s/%s: %s", attempt, self.retries, error)
            except subprocess.CalledProcessError as error:
                stderr = (error.stderr or "").strip()
                self.logger.warning("SMS send failed on attempt %s/%s: %s", attempt, self.retries, stderr or error)
            else:
                self.logger.info("SMS sent to %s via %s", phone_number, sms_path)
                return True

            time.sleep(self.retry_delay_seconds)

        self.logger.error("SMS delivery failed after %s attempts to %s", self.retries, phone_number)
        return False

    def get_modem_id(self) -> str | None:
        """Return the first modem id visible to ModemManager."""

        try:
            result = self.runner(
                ["mmcli", "-L"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            self.logger.error("Failed to list modems with mmcli: %s", error)
            return None

        for line in result.stdout.splitlines():
            match = re.search(r"/Modem/(\d+)", line)
            if match:
                return match.group(1)

        return None

    def create_sms(self, modem_id: str, phone_number: str, message: str) -> str:
        """Create an SMS in ModemManager and return its storage path."""

        sms_args = (
            f"text={quote_mmcli_value(message)},"
            f"number={quote_mmcli_value(phone_number)}"
        )
        result = self.runner(
            ["mmcli", "-m", modem_id, "--messaging-create-sms", sms_args],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )

        for line in result.stdout.splitlines():
            match = re.search(r"(/org/freedesktop/ModemManager1/SMS/\d+)", line)
            if match:
                return match.group(1)

        raise RuntimeError(f"Could not parse SMS path from mmcli output: {result.stdout}")


def quote_mmcli_value(value: str) -> str:
    """Quote a value for mmcli's key-value SMS parser."""

    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def build_sms_sender(config: SmsConfig, logger: logging.Logger) -> SmsSender:
    """Create the configured SMS backend."""

    if config.backend == "mmcli":
        logger.info("Using real mmcli SMS backend")
        return MmcliSmsSender(config.recipients, logger)

    logger.info("Using log-only SMS backend")
    return LogSmsSender(config.recipients, logger)
