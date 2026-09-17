"""Queued SMS delivery for the LabPulse SMS container."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import queue
import re
import subprocess
import threading
import time

from labpulse.common.mqtt_contracts import SmsRequest
from labpulse.common.sms_templates import CURRENT_MEASUREMENT_PLACEHOLDER, sms_template


SEND_RETRIES = 3
RETRY_DELAY_SECONDS = 2.0
QUEUE_SIZE = 100
COMMAND_POLL_INTERVAL_SECONDS = 5.0


@dataclass(frozen=True)
class DeliveryResult:
    """Outcome of delivering one request to one configured recipient."""

    request_id: str
    recipient: str
    status: str
    detail: str = ""


UNSUBSCRIBE_FOOTER = sms_template("formatting", "unsubscribe_footer")
TEST_PREFIX = sms_template("formatting", "test_prefix")
UNSUBSCRIBE_COMMAND = "UNSUBSCRIBE"
SUBSCRIBE_COMMAND = "SUBSCRIBE"
UNSUBSCRIBE_CONFIRMATION = sms_template("commands", "unsubscribe_confirmation")
SUBSCRIBE_CONFIRMATION = sms_template("commands", "subscribe_confirmation")


@dataclass(frozen=True)
class InboundSms:
    """One complete received SMS returned by ModemManager."""

    path: str
    phone_number: str
    text: str


class SubscriptionRegistry:
    """Persist the unsubscribed subset of configured phone numbers."""

    def __init__(self, allowed_numbers: Iterable[str], path: Path) -> None:
        """Load subscription choices for an exact-number allow-list."""

        self.allowed_numbers = frozenset(number.strip() for number in allowed_numbers)
        self.path = path
        # The MQTT delivery thread and modem command thread both consult this
        # state, so changes and file writes must happen under the same lock.
        self._lock = threading.Lock()
        self._unsubscribed: set[str] = set()
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
            values = payload.get("unsubscribed") if isinstance(payload, dict) else None
            if isinstance(values, list):
                self._unsubscribed = {value for value in values if isinstance(value, str)}

    def is_allowed(self, phone_number: str) -> bool:
        """Return whether the exact normalized number may issue commands."""

        return phone_number.strip() in self.allowed_numbers

    def is_subscribed(self, phone_number: str) -> bool:
        """Return whether an allowed number currently receives alerts."""

        normalized = phone_number.strip()
        with self._lock:
            return normalized in self.allowed_numbers and normalized not in self._unsubscribed

    def set_subscribed(self, phone_number: str, subscribed: bool) -> bool:
        """Persist an allowed number's choice and reject unknown numbers."""

        normalized = phone_number.strip()
        if normalized not in self.allowed_numbers:
            return False
        with self._lock:
            previous = set(self._unsubscribed)
            if subscribed:
                self._unsubscribed.discard(normalized)
            else:
                self._unsubscribed.add(normalized)
            try:
                # Replace a complete temporary file in one operation so a
                # restart cannot observe half-written JSON. Restore the in-memory
                # choice too if the disk write fails.
                self.path.parent.mkdir(parents=True, exist_ok=True)
                temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
                temporary_path.write_text(
                    json.dumps({"unsubscribed": sorted(self._unsubscribed)}, indent=2) + "\n",
                    encoding="utf-8",
                )
                temporary_path.replace(self.path)
                return True
            except OSError:
                self._unsubscribed = previous
                return False


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
        *,
        subscription_registry: SubscriptionRegistry,
        test_recipients: Sequence[str] = (),
        dry_run: bool = True,
    ) -> None:
        """Store delivery settings and start the background send worker."""

        self.recipients = tuple(recipients)
        self.test_recipients = tuple(test_recipients)
        self.dry_run = dry_run
        self.subscription_registry = subscription_registry

        # Sending and receiving both call mmcli. The re-entrant lock ensures one
        # complete modem operation finishes before the other thread starts one.
        self._logger = logger
        self._modem_lock = threading.RLock()
        self._result_handler: Callable[[DeliveryResult], None] | None = None
        # Queue items are (recipient, request) pairs. None is the shutdown signal
        # consumed after all earlier messages have been sent.
        self._queue: queue.Queue[tuple[str, SmsRequest] | None] = queue.Queue(maxsize=QUEUE_SIZE)
        self._closed = False
        self._worker_thread = threading.Thread(target=self._worker, name="labpulse-sms-sender", daemon=False)
        self._worker_thread.start()

    def set_result_handler(self, handler: Callable[[DeliveryResult], None]) -> None:
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
            if not self.subscription_registry.is_subscribed(recipient):
                result = DeliveryResult(
                    request.request_id, mask_phone_number(recipient), "unsubscribed", "recipient has unsubscribed"
                )
                self._report(result)
            else:
                active_recipients.append(recipient)

        # Accept all recipients for one alert or reject the complete alert. This
        # avoids silently notifying only the first few people when the queue fills.
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
                result = subprocess.run(
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
            # ModemManager can repeat an object path in its human-readable
            # output. dict.fromkeys removes duplicates while preserving order.
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
            result = subprocess.run(
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
        # None follows every previously queued message, so the worker drains the
        # queue before it exits.
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
                # Match every queue.get() with task_done(), even when sending
                # raises an exception.
                self._queue.task_done()

    def _report(self, result: DeliveryResult) -> None:
        """Send a delivery result when a handler has been registered."""

        if self._result_handler is not None:
            self._result_handler(result)

    def _send_with_mmcli(self, phone_number: str, message: str) -> bool:
        """Send one SMS through the first modem reported by mmcli."""

        for attempt in range(1, SEND_RETRIES + 1):
            modem_id = self._get_modem_id()
            if modem_id is None:
                self._logger.error("No operational cellular modem found")
                return False

            sms_path: str | None = None
            try:
                sms_path = self._create_sms(modem_id, phone_number, message)
                subprocess.run(
                    ["mmcli", "-s", sms_path, "--send"],
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                self._logger.warning("SMS send timed out on attempt %s/%s", attempt, SEND_RETRIES)
            except subprocess.CalledProcessError as error:
                stderr = (error.stderr or "").strip()
                self._logger.warning(
                    "SMS send failed on attempt %s/%s: %s",
                    attempt,
                    SEND_RETRIES,
                    stderr or f"mmcli exited with {error.returncode}",
                )
            except RuntimeError as error:
                self._logger.warning("SMS setup failed on attempt %s/%s: %s", attempt, SEND_RETRIES, error)
            else:
                self._logger.info(
                    "SMS sent to %s via %s", mask_phone_number(phone_number), sms_path
                )
                return True
            finally:
                # mmcli creates a stored SMS object before sending it. Always
                # delete that object so retries do not fill modem storage.
                if sms_path is not None:
                    self._delete_sms(modem_id, sms_path)

            if attempt < SEND_RETRIES:
                time.sleep(RETRY_DELAY_SECONDS)

        self._logger.error(
            "SMS delivery failed after %s attempts to %s",
            SEND_RETRIES,
            mask_phone_number(phone_number),
        )
        return False

    def _get_modem_id(self) -> str | None:
        """Return the first modem ID visible to ModemManager."""

        try:
            result = subprocess.run(
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
        result = subprocess.run(
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
            subprocess.run(
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


class SmsCommandMonitor:
    """Poll received modem messages and apply subscription commands."""

    def __init__(
        self,
        sender: SmsSender,
        registry: SubscriptionRegistry,
        logger: logging.Logger,
    ) -> None:
        """Store dependencies for the inbound-command worker."""

        self.sender = sender
        self.registry = registry
        self._logger = logger
        self._stop_event = threading.Event()
        # A modem message can appear in more than one poll. Remember it in this
        # process so its command is applied once before deletion succeeds.
        self._processed_paths: set[str] = set()
        self._worker_thread = threading.Thread(
            target=self._worker, name="labpulse-sms-command-monitor", daemon=False
        )

    def start(self) -> None:
        """Start polling for inbound subscription commands."""

        self._worker_thread.start()

    def close(self, timeout: float = 15.0) -> None:
        """Stop the inbound-command worker and wait for it to finish."""

        self._stop_event.set()
        if self._worker_thread.ident is not None:
            self._worker_thread.join(timeout=timeout)
        if self._worker_thread.is_alive():
            self._logger.warning("SMS command monitor did not stop within %.1f seconds", timeout)

    def poll_once(self) -> None:
        """Process every complete received SMS currently stored by the modem."""

        for message in self.sender.list_received_sms():
            if message.path not in self._processed_paths:
                self._processed_paths.add(message.path)
                self._handle_message(message)
            self.sender.delete_received_sms(message.path)

    def _handle_message(self, message: InboundSms) -> None:
        """Apply one exact subscription command without replying to outsiders."""

        phone_number = message.phone_number.strip()
        command = message.text.strip().upper()
        if not self.registry.is_allowed(phone_number):
            self._logger.warning(
                "Ignored inbound SMS command from unconfigured number %s", mask_phone_number(phone_number)
            )
            return

        if command == UNSUBSCRIBE_COMMAND:
            subscribed = False
            confirmation = UNSUBSCRIBE_CONFIRMATION
            action = "Unsubscribed"
        elif command == SUBSCRIBE_COMMAND:
            subscribed = True
            confirmation = SUBSCRIBE_CONFIRMATION
            action = "Subscribed"
        else:
            self._logger.info("Ignored unrecognized inbound SMS from %s", mask_phone_number(phone_number))
            return

        if not self.registry.set_subscribed(phone_number, subscribed):
            self._logger.error("Could not persist %s request for %s", command.lower(), mask_phone_number(phone_number))
            return
        self._logger.info("%s %s", action, mask_phone_number(phone_number))
        self.sender.send_sms(phone_number, confirmation)

    def _worker(self) -> None:
        """Poll immediately and then at a bounded interval until shutdown."""

        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception:
                self._logger.exception("Unexpected SMS command monitor failure")
            self._stop_event.wait(COMMAND_POLL_INTERVAL_SECONDS)


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
