"""Queued SMS delivery for the LabPulse SMS container."""

from dataclasses import dataclass
import logging
import queue
import re
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from typing import Protocol

from labpulse.common.mqtt_contracts import SmsRequest
from labpulse.common.sms_templates import CURRENT_MEASUREMENT_PLACEHOLDER, sms_template


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class SubscriptionLookup(Protocol):
    """Minimal subscription interface required by outbound routing."""

    def is_subscribed(self, phone_number: str) -> bool:
        """Return whether one configured recipient currently accepts alerts."""

        ...


@dataclass(frozen=True)
class DeliveryResult:
    """Outcome of delivering one request to one configured recipient."""

    request_id: str
    recipient: str
    status: str
    detail: str = ""


ResultHandler = Callable[[DeliveryResult], None]

UNSUBSCRIBE_FOOTER = sms_template("formatting", "unsubscribe_footer")
TEST_PREFIX = sms_template("formatting", "test_prefix")


@dataclass(frozen=True)
class InboundSms:
    """One complete received SMS returned by ModemManager."""

    path: str
    phone_number: str
    text: str


def format_sms_message(request: SmsRequest) -> str:
    """Create one concise SMS body from a validated request."""

    title = request.title
    if request.test_mode and not title.startswith(TEST_PREFIX):
        title = f"{TEST_PREFIX} {title}"
    if request.current_measurement not in (None, "", "unknown", "None"):
        message = request.message.replace(CURRENT_MEASUREMENT_PLACEHOLDER, str(request.current_measurement))
    else:
        message = "\n".join(
            line for line in request.message.splitlines() if CURRENT_MEASUREMENT_PLACEHOLDER not in line
        )
    lines = [title, message]
    if request.event == "warning":
        lines.extend(("", UNSUBSCRIBE_FOOTER))
    return "\n".join(lines)
def mask_phone_number(phone_number: str) -> str:
    """Return a log-safe representation of a recipient number."""

    if len(phone_number) <= 6:
        return "***"
    return f"{phone_number[:3]}{'*' * (len(phone_number) - 6)}{phone_number[-3:]}"


class SmsSender:
    """Queue SMS requests and either log them or deliver them through mmcli."""

    def __init__(
        self,
        recipients: Sequence[str],
        logger: logging.Logger,
        test_recipients: Sequence[str] = (),
        dry_run: bool = True,
        runner: CommandRunner = subprocess.run,
        retries: int = 3,
        retry_delay_seconds: float = 2.0,
        sleeper: Callable[[float], None] = time.sleep,
        queue_size: int = 100,
        subscription_registry: SubscriptionLookup | None = None,
    ) -> None:
        """Store delivery settings and start the background send worker."""

        self.recipients = tuple(recipients)
        self.test_recipients = tuple(test_recipients)
        self.dry_run = dry_run
        self.subscription_registry = subscription_registry

        self._logger = logger
        self._command_runner = runner
        self._retries = retries
        self._retry_delay_seconds = retry_delay_seconds
        self._sleep = sleeper
        self._modem_lock = threading.RLock()
        self._result_handler: ResultHandler | None = None
        self._queue: queue.Queue[tuple[str, SmsRequest] | None] = queue.Queue(maxsize=queue_size)
        self._closed = False
        self._worker_thread = threading.Thread(target=self._worker, name="labpulse-sms-sender", daemon=False)
        self._worker_thread.start()

    def set_result_handler(self, handler: ResultHandler) -> None:
        """Register the callback used for delivery results."""

        self._result_handler = handler

    def broadcast(self, request: SmsRequest) -> bool:
        """Queue one outbound request for every configured recipient."""

        if self._closed:
            self._logger.error("SMS request rejected because the sender is stopping")
            return False
        recipients = self.test_recipients if request.test_mode else self.recipients
        recipient_kind = "test recipients" if request.test_mode else "recipients"
        if not recipients:
            self._logger.warning("SMS request dropped because no %s are configured", recipient_kind)
            self._report(DeliveryResult(request.request_id, "", "failed", f"no {recipient_kind} configured"))
            return False

        active_recipients = []
        for recipient in recipients:
            if self.subscription_registry is not None and not self.subscription_registry.is_subscribed(recipient):
                result = DeliveryResult(
                    request.request_id, mask_phone_number(recipient), "unsubscribed", "recipient has unsubscribed"
                )
                self._report(result)
            else:
                active_recipients.append(recipient)

        available_slots = self._queue.maxsize - self._queue.qsize()
        if self._queue.maxsize and available_slots < len(active_recipients):
            self._logger.error("SMS queue is full; request %s was rejected", request.request_id)
            self._report(DeliveryResult(request.request_id, "", "failed", "sender queue full"))
            return False
        for recipient in active_recipients:
            self._queue.put_nowait((recipient, request))
        return True

    def send_sms(self, phone_number: str, message: str) -> bool:
        """Log one SMS in dry-run mode or send it through ModemManager."""

        if self.dry_run:
            self._logger.info(
                "SMS dry run would send to %s: %s",
                mask_phone_number(phone_number),
                message,
            )
            return True
        with self._modem_lock:
            return self._send_with_mmcli(phone_number, message)

    def list_received_sms(self) -> list[InboundSms]:
        """Return complete received text messages currently stored by the modem."""

        with self._modem_lock:
            modem_id = self._get_modem_id()
            if modem_id is None:
                return []
            try:
                result = self._command_runner(
                    ["mmcli", "-m", modem_id, "--messaging-list-sms"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=15,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                self._logger.warning(
                    "Could not list received SMS objects: %s", type(error).__name__
                )
                return []

            messages = []
            paths = dict.fromkeys(
                re.findall(r"/org/freedesktop/ModemManager1/SMS/\d+", result.stdout)
            )
            for sms_path in paths:
                message = self._read_received_sms(sms_path)
                if message is not None:
                    messages.append(message)
            return messages

    def _read_received_sms(self, sms_path: str) -> InboundSms | None:
        """Read one SMS object and return it only when reception is complete."""

        try:
            result = self._command_runner(
                ["mmcli", "-s", sms_path, "--output-keyvalue"],
                capture_output=True,
                text=True,
                check=True,
                timeout=15,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            self._logger.warning("Could not read SMS object %s: %s", sms_path, error)
            return None
        fields = parse_mmcli_key_values(result.stdout)
        if fields.get("sms.properties.state") != "received":
            return None
        phone_number = fields.get("sms.content.number", "").strip()
        text = fields.get("sms.content.text", "")
        if not phone_number or not text:
            return None
        return InboundSms(sms_path, phone_number, text)

    def delete_received_sms(self, sms_path: str) -> None:
        """Delete one processed received SMS object from modem storage."""

        with self._modem_lock:
            modem_id = self._get_modem_id()
            if modem_id is not None:
                self._delete_sms(modem_id, sms_path)

    def close(self, timeout: float = 15) -> None:
        """Drain pending sends and stop the worker thread."""

        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._worker_thread.join(timeout=timeout)
        if self._worker_thread.is_alive():
            self._logger.warning("SMS sender did not stop within %.1f seconds", timeout)

    def _worker(self) -> None:
        """Send queued SMS messages one at a time."""

        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                phone_number, request = item
                try:
                    success = self.send_sms(phone_number, format_sms_message(request))
                except Exception:
                    self._logger.exception("Unexpected SMS sender failure")
                    success = False
                self._report(
                    DeliveryResult(
                        request.request_id,
                        mask_phone_number(phone_number),
                        ("logged" if self.dry_run else "sent") if success else "failed",
                        "" if success else "SMS delivery failed",
                    )
                )
            finally:
                self._queue.task_done()

    def _report(self, result: DeliveryResult) -> None:
        """Send a delivery result when a handler has been registered."""

        if self._result_handler is not None:
            self._result_handler(result)

    def _send_with_mmcli(self, phone_number: str, message: str) -> bool:
        """Send one SMS through the first modem reported by mmcli."""

        for attempt in range(1, self._retries + 1):
            modem_id = self._get_modem_id()
            if modem_id is None:
                self._logger.error("No operational cellular modem found")
                return False

            sms_path: str | None = None
            try:
                sms_path = self._create_sms(modem_id, phone_number, message)
                self._command_runner(
                    ["mmcli", "-s", sms_path, "--send"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                self._logger.warning("SMS send timed out on attempt %s/%s", attempt, self._retries)
            except subprocess.CalledProcessError as error:
                stderr = (error.stderr or "").strip()
                self._logger.warning(
                    "SMS send failed on attempt %s/%s: %s",
                    attempt,
                    self._retries,
                    stderr or f"mmcli exited with {error.returncode}",
                )
            except RuntimeError as error:
                self._logger.warning("SMS setup failed on attempt %s/%s: %s", attempt, self._retries, error)
            else:
                self._logger.info(
                    "SMS sent to %s via %s", mask_phone_number(phone_number), sms_path
                )
                return True
            finally:
                if sms_path is not None:
                    self._delete_sms(modem_id, sms_path)

            if attempt < self._retries:
                self._sleep(self._retry_delay_seconds)

        self._logger.error(
            "SMS delivery failed after %s attempts to %s",
            self._retries,
            mask_phone_number(phone_number),
        )
        return False

    def _get_modem_id(self) -> str | None:
        """Return the first modem ID visible to ModemManager."""

        try:
            result = self._command_runner(
                ["mmcli", "-L"],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            self._logger.error("Failed to list modems with mmcli: %s", type(error).__name__)
            return None

        for line in result.stdout.splitlines():
            match = re.search(r"/Modem/(\d+)", line)
            if match:
                return match.group(1)
        return None

    def _create_sms(self, modem_id: str, phone_number: str, message: str) -> str:
        """Create an SMS in ModemManager and return its storage path."""

        sms_args = (
            f"text={quote_mmcli_value(message)},"
            f"number={quote_mmcli_value(phone_number)}"
        )
        result = self._command_runner(
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
        raise RuntimeError("Could not parse the created SMS path from mmcli output")

    def _delete_sms(self, modem_id: str, sms_path: str) -> None:
        """Delete a created SMS object from ModemManager storage."""

        try:
            self._command_runner(
                ["mmcli", "-m", modem_id, f"--messaging-delete-sms={sms_path}"],
                capture_output=True,
                text=True,
                check=True,
                timeout=15,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            self._logger.warning(
                "Could not remove ModemManager SMS object %s: %s",
                sms_path,
                type(error).__name__,
            )


def quote_mmcli_value(value: str) -> str:
    """Quote a value for mmcli's key-value SMS parser."""

    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def parse_mmcli_key_values(output: str) -> dict[str, str]:
    """Parse mmcli's stable machine-readable key-value output."""

    fields = {}
    for line in output.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    return fields
