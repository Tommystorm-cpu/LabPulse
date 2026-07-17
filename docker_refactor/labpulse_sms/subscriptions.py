"""Persistent, allow-listed SMS subscription command handling."""

from collections.abc import Iterable
import json
import logging
from pathlib import Path
import threading

from labpulse_common.sms_templates import sms_template
from labpulse_sms.sender import InboundSms, SmsSender, mask_phone_number


UNSUBSCRIBE_COMMAND = "UNSUBSCRIBE"
SUBSCRIBE_COMMAND = "SUBSCRIBE"
UNSUBSCRIBE_CONFIRMATION = sms_template("commands", "unsubscribe_confirmation")
SUBSCRIBE_CONFIRMATION = sms_template("commands", "subscribe_confirmation")


class SubscriptionRegistry:
    """Store the globally unsubscribed subset of configured phone numbers."""

    def __init__(self, allowed_numbers: Iterable[str], path: Path | None = None) -> None:
        """Load persisted subscription choices for an exact-number allow-list."""

        self.allowed_numbers = frozenset(number.strip() for number in allowed_numbers)
        self.path = path
        self.lock = threading.Lock()
        self.unsubscribed: set[str] = set()
        self._load()

    def is_allowed(self, phone_number: str) -> bool:
        """Return whether the exact normalized number may issue commands."""

        return phone_number.strip() in self.allowed_numbers

    def is_subscribed(self, phone_number: str) -> bool:
        """Return whether an allowed number currently receives alerts."""

        normalized = phone_number.strip()
        with self.lock:
            return normalized in self.allowed_numbers and normalized not in self.unsubscribed

    def set_subscribed(self, phone_number: str, subscribed: bool) -> bool:
        """Persist an allowed number's choice and reject every unknown number."""

        normalized = phone_number.strip()
        if normalized not in self.allowed_numbers:
            return False
        with self.lock:
            previous = set(self.unsubscribed)
            if subscribed:
                self.unsubscribed.discard(normalized)
            else:
                self.unsubscribed.add(normalized)
            if self._save():
                return True
            self.unsubscribed = previous
            return False

    def _load(self) -> None:
        """Load a valid unsubscribed-number list, ignoring malformed state."""

        if self.path is None or not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        values = payload.get("unsubscribed") if isinstance(payload, dict) else None
        if isinstance(values, list):
            self.unsubscribed = {value for value in values if isinstance(value, str)}

    def _save(self) -> bool:
        """Atomically store subscription choices when persistence is configured."""

        if self.path is None:
            return True
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary_path.write_text(
                json.dumps({"unsubscribed": sorted(self.unsubscribed)}, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(self.path)
            return True
        except OSError:
            return False


class SmsCommandMonitor:
    """Poll received modem messages and apply allow-listed subscription commands."""

    def __init__(
        self,
        sender: SmsSender,
        registry: SubscriptionRegistry,
        logger: logging.Logger,
        poll_interval_seconds: float = 5.0,
    ) -> None:
        """Store dependencies for the inbound-command worker."""

        self.sender = sender
        self.registry = registry
        self.logger = logger
        self.poll_interval_seconds = poll_interval_seconds
        self.stop_event = threading.Event()
        self.processed_paths: set[str] = set()
        self.worker = threading.Thread(
            target=self._worker,
            name="labpulse-sms-command-monitor",
            daemon=False,
        )

    def start(self) -> None:
        """Start polling for inbound subscription commands."""

        self.worker.start()

    def close(self, timeout: float = 15.0) -> None:
        """Stop the inbound-command worker and wait for it to finish."""

        self.stop_event.set()
        if self.worker.ident is not None:
            self.worker.join(timeout=timeout)
        if self.worker.is_alive():
            self.logger.warning(
                "SMS command monitor did not stop within %.1f seconds", timeout
            )

    def poll_once(self) -> None:
        """Process every complete received SMS currently stored by the modem."""

        for message in self.sender.list_received_sms():
            if message.path not in self.processed_paths:
                self.processed_paths.add(message.path)
                self._handle_message(message)
            self.sender.delete_received_sms(message.path)

    def _handle_message(self, message: InboundSms) -> None:
        """Apply one exact subscription command without replying to outsiders."""

        phone_number = message.phone_number.strip()
        command = message.text.strip().upper()
        if not self.registry.is_allowed(phone_number):
            self.logger.warning(
                "Ignored inbound SMS command from unconfigured number %s",
                mask_phone_number(phone_number),
            )
            return

        if command == UNSUBSCRIBE_COMMAND:
            if not self.registry.set_subscribed(phone_number, False):
                self.logger.error(
                    "Could not persist unsubscribe request for %s",
                    mask_phone_number(phone_number),
                )
                return
            self.logger.info("Unsubscribed %s", mask_phone_number(phone_number))
            self.sender.send_sms(phone_number, UNSUBSCRIBE_CONFIRMATION)
        elif command == SUBSCRIBE_COMMAND:
            if not self.registry.set_subscribed(phone_number, True):
                self.logger.error(
                    "Could not persist subscribe request for %s",
                    mask_phone_number(phone_number),
                )
                return
            self.logger.info("Subscribed %s", mask_phone_number(phone_number))
            self.sender.send_sms(phone_number, SUBSCRIBE_CONFIRMATION)
        else:
            self.logger.info(
                "Ignored unrecognized inbound SMS from %s",
                mask_phone_number(phone_number),
            )

    def _worker(self) -> None:
        """Poll immediately and then at a bounded interval until shutdown."""

        while not self.stop_event.is_set():
            try:
                self.poll_once()
            except Exception:
                self.logger.exception("Unexpected SMS command monitor failure")
            self.stop_event.wait(self.poll_interval_seconds)
