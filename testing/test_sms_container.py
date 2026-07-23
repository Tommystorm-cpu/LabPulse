"""Integration and unit checks for the LabPulse SMS service."""

from pathlib import Path
import json
import subprocess
import sys

from pydantic import ValidationError

sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR / "src"))

from labpulse.common.config import MqttConfig, SmsConfig
from labpulse.common.mqtt_contracts import (
    SMS_STATUS_DISCOVERY_TOPIC,
    SMS_STATUS_TOPIC,
    SMS_SUBSCRIPTION_TOPIC,
    SmsRequest,
    sms_result_topic,
)
from labpulse.common.sms_templates import (
    CURRENT_MEASUREMENT_PLACEHOLDER,
    TEMPLATE_PATH,
    load_sms_templates,
)
from labpulse.sms.cli import DEFAULT_CONFIG_PATH, parse_args
from labpulse.sms.sender import (
    DeliveryResult,
    InboundSms,
    SmsSender,
    UNSUBSCRIBE_FOOTER,
    format_sms_message,
    mask_phone_number,
    parse_mmcli_key_values,
    quote_mmcli_value,
)
from labpulse.sms.subscriber import (
    RecentRequestCache,
    SMSSubscriber,
    SmsPayloadError,
    parse_sms_payload,
)
from labpulse.sms.subscriptions import (
    SUBSCRIBE_CONFIRMATION,
    UNSUBSCRIBE_CONFIRMATION,
    SmsCommandMonitor,
    SubscriptionRegistry,
)


class FakeSmsClient:
    """Small MQTT client stand-in for SMS subscriber tests."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.constructor_args = args
        self.constructor_kwargs = kwargs
        self.on_connect = None
        self.on_message = None
        self.connected_to: tuple[str, int, int] | None = None
        self.subscriptions: list[tuple[str, int]] = []
        self.published: list[tuple[str, str, int, bool]] = []
        self.will: tuple[str, str, int, bool] | None = None
        self.disconnected = False

    def will_set(self, topic: str, payload: str, qos: int, retain: bool) -> None:
        self.will = (topic, payload, qos, retain)

    def connect(self, broker: str, port: int, keepalive: int) -> None:
        self.connected_to = (broker, port, keepalive)

    def subscribe(self, topic: str, qos: int = 0) -> None:
        self.subscriptions.append((topic, qos))

    def publish(self, topic: str, payload: str, qos: int, retain: bool) -> None:
        self.published.append((topic, payload, qos, retain))

    def disconnect(self) -> None:
        self.disconnected = True

    def loop_forever(self) -> None:
        return


class FakeSender:
    """Small sender stand-in for subscriber tests."""

    def __init__(self, accepted: bool = True) -> None:
        self.requests: list[SmsRequest] = []
        self.accepted = accepted
        self.result_handler = None
        self.closed = False

    def set_result_handler(self, handler: object) -> None:
        self.result_handler = handler

    def broadcast(self, request: SmsRequest) -> bool:
        self.requests.append(request)
        return self.accepted

    def close(self, timeout: float = 15) -> None:
        self.closed = True


class FakeCommandSender:
    """Modem-facing sender stand-in for inbound command tests."""

    def __init__(self, messages: list[InboundSms]) -> None:
        self.messages = messages
        self.sent: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    def list_received_sms(self) -> list[InboundSms]:
        """Return the currently configured fake inbox."""

        return list(self.messages)

    def delete_received_sms(self, sms_path: str) -> None:
        """Record deletion of a processed modem object."""

        self.deleted.append(sms_path)

    def send_sms(self, phone_number: str, message: str) -> bool:
        """Record one direct confirmation message."""

        self.sent.append((phone_number, message))
        return True


def quiet_logger() -> object:
    """Return a logger-like object suitable for isolated backend tests."""

    return type(
        "Logger",
        (),
        {
            "info": lambda *_args: None,
            "warning": lambda *_args: None,
            "error": lambda *_args: None,
            "exception": lambda *_args: None,
        },
    )()


def request_payload(request_id: str = "request-1", event: str = "warning") -> dict[str, str]:
    """Return one complete valid SMS request payload."""

    return {
        "request_id": request_id,
        "event": event,
        "service": "pump_room",
        "service_label": "Pump Room",
        "measurement": "flow1",
        "measurement_label": "Flow 1",
        "state": "Danger",
        "title": "LabPulse Flow warning",
        "message": "Pump Room / Flow 1 is in Danger.\nCurrent Measurement: {current_measurement}",
        "test_mode": False,
        "current_measurement": "0.2",
    }


def request(request_id: str = "request-1", event: str = "warning") -> SmsRequest:
    """Return one validated SMS request."""

    return SmsRequest.model_validate(request_payload(request_id, event))


def assert_contains(text: str, expected: str, label: str) -> None:
    """Raise AssertionError when expected text is absent."""

    if expected not in text:
        raise AssertionError(f"{label}: missing {expected!r}")


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise AssertionError when two values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_setup_and_compose_contract() -> None:
    """Check deployment copies SMS code and limits host MQTT exposure."""

    setup = (REFACTOR_DIR / "deployment" / "setup_container_fs.sh").read_text(
        encoding="utf-8"
    )
    compose = (REFACTOR_DIR / "deployment" / "generate_compose.sh").read_text(
        encoding="utf-8"
    )
    assert_contains(setup, "COPY labpulse ./labpulse", "Dockerfile package copy")
    assert_contains(
        setup,
        'replace_dir "$PACKAGE_SOURCE" "$PROJECT_DIR/labpulse-python/labpulse"',
        "setup package copy",
    )
    assert_contains(compose, "labpulse-sms:", "SMS service")
    assert_contains(compose, "container_name: labpulse-sms", "SMS container name")
    assert_contains(compose, "127.0.0.1:1883:1883", "localhost-only MQTT port")
    assert_contains(compose, "- /run/dbus:/run/dbus:ro", "mmcli D-Bus mount")


def test_sms_entry_accepts_explicit_argv() -> None:
    """Check the CLI path default and directly injectable argument parsing."""

    assert_equal(DEFAULT_CONFIG_PATH.name, "config.yaml", "default config filename")
    args = parse_args(["--config", "custom.yaml"])
    assert_equal(args.config, "custom.yaml", "custom config argument")


def test_sms_config_validates_recipients() -> None:
    """Check normalization and production-recipient validation."""

    config = SmsConfig(
        dry_run=False,
        recipients=[" +447700900000 "],
        test_recipients=[" +447700900001 "],
    )
    assert_equal(config.recipients, ["+447700900000"], "normalized recipient")
    assert_equal(
        config.test_recipients,
        ["+447700900001"],
        "normalized test recipient",
    )
    for recipients in ([], [""], ["+447700900000", "+447700900000"], ["07700900000"]):
        try:
            SmsConfig(dry_run=False, recipients=recipients)
        except ValidationError:
            continue
        raise AssertionError(f"invalid recipients accepted: {recipients!r}")
    try:
        SmsConfig(dry_run="false", recipients=["+447700900000"])  # type: ignore[arg-type]
    except ValidationError:
        return
    raise AssertionError("quoted dry_run value was accepted as a boolean")


def test_test_mode_routes_only_to_test_recipients() -> None:
    """Check test requests cannot reach the normal emergency contact list."""

    sender = SmsSender(
        ["+447700900000"],
        quiet_logger(),
        test_recipients=["+447700900001", "+447700900002"],
        dry_run=True,
    )
    results: list[DeliveryResult] = []
    sender.set_result_handler(results.append)
    test_request = request(event="notification").model_copy(
        update={"test_mode": True, "title": "LabPulse Flow warning"}
    )
    try:
        assert_equal(sender.broadcast(test_request), True, "test request accepted")
        sender.queue.join()
    finally:
        sender.close()
    assert_equal(len(results), 2, "test recipient fan-out")
    assert_equal(
        [result.recipient for result in results],
        ["+44*******001", "+44*******002"],
        "test recipients only",
    )
    assert_contains(format_sms_message(test_request), "[TEST]", "test prefix")


def test_unsubscribed_numbers_are_filtered_in_both_modes() -> None:
    """Apply one persistent subscription choice to live and test routing."""

    registry = SubscriptionRegistry(
        ["+447700900000", "+447700900001", "+447700900002"]
    )
    registry.set_subscribed("+447700900000", False)
    registry.set_subscribed("+447700900002", False)
    sender = SmsSender(
        ["+447700900000", "+447700900001"],
        quiet_logger(),
        test_recipients=["+447700900001", "+447700900002"],
        dry_run=True,
        subscription_registry=registry,
    )
    results: list[DeliveryResult] = []
    sender.set_result_handler(results.append)
    try:
        assert_equal(sender.broadcast(request("live-filter")), True, "live accepted")
        test_request = request("test-filter").model_copy(update={"test_mode": True})
        assert_equal(sender.broadcast(test_request), True, "test accepted")
        sender.queue.join()
    finally:
        sender.close()
    suppressed = [
        result.recipient for result in results if result.status == "unsubscribed"
    ]
    assert_equal(
        suppressed,
        ["+44*******000", "+44*******002"],
        "suppression spans delivery modes",
    )
    delivered = [result for result in results if result.status == "logged"]
    assert_equal(len(delivered), 2, "one active recipient per mode")


def test_subscription_registry_persists_and_rejects_outsiders() -> None:
    """Persist choices while preventing unconfigured numbers from changing state."""

    temp_dir = REFACTOR_DIR / "testing" / "tmp" / "sms-subscription-test"
    temp_dir.mkdir(parents=True, exist_ok=True)
    state_path = temp_dir / "subscriptions.json"
    if state_path.exists():
        state_path.unlink()
    try:
        registry = SubscriptionRegistry(
            ["+447700900000", "+447700900001"], state_path
        )
        assert_equal(
            registry.set_subscribed("+447700999999", False),
            False,
            "outsider rejected",
        )
        assert_equal(
            registry.set_subscribed("+447700900000", False),
            True,
            "unsubscribe accepted",
        )
        restored = SubscriptionRegistry(
            ["+447700900000", "+447700900001"], state_path
        )
        assert_equal(
            restored.is_subscribed("+447700900000"), False, "unsubscribe restored"
        )
        restored.set_subscribed("+447700900000", True)
        subscribed = SubscriptionRegistry(
            ["+447700900000", "+447700900001"], state_path
        )
        assert_equal(
            subscribed.is_subscribed("+447700900000"), True, "subscribe restored"
        )
    finally:
        if state_path.exists():
            state_path.unlink()
        if temp_dir.exists():
            temp_dir.rmdir()


def test_inbound_subscription_commands_are_allow_listed() -> None:
    """Confirm valid commands, ignore outsiders, and delete every received object."""

    registry = SubscriptionRegistry(["+447700900000", "+447700900001"])
    sender = FakeCommandSender(
        [
            InboundSms("/sms/1", "+447700900000", " unsubscribe \n"),
            InboundSms("/sms/2", "+447700999999", "UNSUBSCRIBE"),
            InboundSms("/sms/3", "+447700900001", "hello"),
        ]
    )
    monitor = SmsCommandMonitor(sender, registry, quiet_logger())  # type: ignore[arg-type]
    monitor.poll_once()
    assert_equal(
        registry.is_subscribed("+447700900000"), False, "allowed unsubscribe"
    )
    assert_equal(
        sender.sent,
        [("+447700900000", UNSUBSCRIBE_CONFIRMATION)],
        "unsubscribe confirmation only",
    )
    assert_equal(sender.deleted, ["/sms/1", "/sms/2", "/sms/3"], "inbox cleanup")

    sender.messages = [InboundSms("/sms/4", "+447700900000", "SuBsCrIbE")]
    monitor.poll_once()
    assert_equal(registry.is_subscribed("+447700900000"), True, "allowed subscribe")
    assert_equal(sender.sent[-1], ("+447700900000", SUBSCRIBE_CONFIRMATION), "subscribe confirmation")


def test_mmcli_received_sms_parsing() -> None:
    """Read only complete received ModemManager objects via key-value output."""

    calls: list[list[str]] = []

    def runner(command: list[str], **_kwargs: object) -> object:
        """Return a mixed received/sent modem inbox."""

        calls.append(command)
        if command == ["mmcli", "-L"]:
            stdout = "/org/freedesktop/ModemManager1/Modem/7\n"
        elif command[-1] == "--messaging-list-sms":
            stdout = (
                "/org/freedesktop/ModemManager1/SMS/8 (received)\n"
                "/org/freedesktop/ModemManager1/SMS/9 (sent)\n"
            )
        elif command[2] == "/org/freedesktop/ModemManager1/SMS/8":
            stdout = (
                "sms.content.number : +447700900000\n"
                "sms.content.text : UNSUBSCRIBE: now\n"
                "sms.properties.state : received\n"
            )
        else:
            stdout = (
                "sms.content.number : +447700900001\n"
                "sms.content.text : outbound\n"
                "sms.properties.state : sent\n"
            )
        return type("Completed", (), {"stdout": stdout, "stderr": "", "returncode": 0})()

    sender = SmsSender([], quiet_logger(), dry_run=False, runner=runner)
    try:
        messages = sender.list_received_sms()
    finally:
        sender.close()
    assert_equal(
        messages,
        [
            InboundSms(
                "/org/freedesktop/ModemManager1/SMS/8",
                "+447700900000",
                "UNSUBSCRIBE: now",
            )
        ],
        "received object parsing",
    )
    assert_equal(
        parse_mmcli_key_values("sms.content.text : value: with colon\n")[
            "sms.content.text"
        ],
        "value: with colon",
        "key-value colon preservation",
    )


def test_test_requests_do_not_rate_limit_live_alerts() -> None:
    """Check a test event cannot consume the live alert cooldown slot."""

    cache = RecentRequestCache(clock=lambda: 100.0)
    test_request = request("test-request").model_copy(update={"test_mode": True})
    live_request = request("live-request")
    cache.remember(test_request)
    assert_equal(cache.rejection_reason(live_request), None, "live request after test")


def test_subscriber_uses_persistent_qos_one_session() -> None:
    """Check persistent client settings, last will, exact topic, and QoS."""

    sender = FakeSender()
    client = FakeSmsClient()
    constructor: dict[str, object] = {}

    def client_factory(*args: object, **kwargs: object) -> FakeSmsClient:
        """Record persistent-session constructor arguments."""

        constructor["args"] = args
        constructor["kwargs"] = kwargs
        return client

    subscriber = SMSSubscriber(
        MqttConfig(broker="mosquitto", port=1883),
        sender,
        client_factory=client_factory,
    )
    assert_equal(constructor["kwargs"]["client_id"], "LabPulse-SMS", "stable client ID")
    assert_equal(constructor["kwargs"]["clean_session"], False, "persistent session")
    assert_equal(client.will[0], SMS_STATUS_TOPIC, "status last-will topic")
    assert_equal(client.will[2:], (1, True), "status last-will delivery")

    subscriber.connect()
    assert_equal(client.connected_to, ("mosquitto", 1883, 60), "MQTT connection")
    subscriber.on_connect(client, None, None, 0, None)
    assert_equal(client.subscriptions, [(SMS_SUBSCRIPTION_TOPIC, 1)], "QoS 1 subscription")
    assert_equal(client.published[-2][0], SMS_STATUS_DISCOVERY_TOPIC, "status discovery topic")
    assert_equal(client.published[-1][0], SMS_STATUS_TOPIC, "online status topic")
    assert_equal(client.published[-1][2:], (1, True), "retained online status")


def test_payload_parser_is_strict() -> None:
    """Check typed parsing and rejection of malformed or unexpected payloads."""

    parsed = parse_sms_payload(json.dumps(request_payload()).encode())
    assert_equal(parsed.service, "pump_room", "payload service")
    assert_equal(parsed.measurement, "flow1", "payload measurement")

    invalid_payloads = [
        b"plain text",
        b"\xff",
        b'{"request_id":"missing-fields"}',
        json.dumps({**request_payload(), "unexpected": "field"}).encode(),
    ]
    for payload in invalid_payloads:
        try:
            parse_sms_payload(payload)
        except SmsPayloadError:
            continue
        raise AssertionError(f"invalid payload accepted: {payload!r}")


def test_subscriber_deduplicates_and_rate_limits() -> None:
    """Check accepted requests, duplicate IDs, and repeated-event cooldown."""

    now = [1_000.0]
    sender = FakeSender()
    client = FakeSmsClient()
    subscriber = SMSSubscriber(
        MqttConfig(broker="mosquitto"),
        sender,
        client_factory=lambda *args, **kwargs: client,
        request_cache=RecentRequestCache(clock=lambda: now[0]),
    )

    message = type("Message", (), {"payload": json.dumps(request_payload()).encode()})()
    subscriber.on_message(client, None, message)
    assert_equal(len(sender.requests), 1, "accepted request")
    subscriber.on_message(client, None, message)
    assert_equal(len(sender.requests), 1, "duplicate suppressed")
    assert_equal(json.loads(client.published[-1][1])["status"], "duplicate", "duplicate result")

    repeated = type(
        "Message",
        (),
        {"payload": json.dumps(request_payload("request-2")).encode()},
    )()
    subscriber.on_message(client, None, repeated)
    assert_equal(len(sender.requests), 1, "event cooldown")
    assert_equal(json.loads(client.published[-1][1])["status"], "rate_limited", "rate result")


def test_recent_request_cache_persists() -> None:
    """Check request IDs survive service reconstruction."""

    temp_dir = REFACTOR_DIR / "testing" / "tmp" / "sms-cache-test"
    temp_dir.mkdir(parents=True, exist_ok=True)
    cache_path = temp_dir / "requests.json"
    try:
        first = RecentRequestCache(path=cache_path, clock=lambda: 1_000.0)
        first.remember(request())
        second = RecentRequestCache(path=cache_path, clock=lambda: 1_001.0)
        assert_equal(second.rejection_reason(request()), "duplicate", "persistent duplicate")
    finally:
        if cache_path.exists():
            cache_path.unlink()
        if temp_dir.exists():
            temp_dir.rmdir()


def test_delivery_results_are_published() -> None:
    """Check sender outcomes are published with masked recipient data."""

    sender = FakeSender()
    client = FakeSmsClient()
    subscriber = SMSSubscriber(
        MqttConfig(broker="mosquitto"),
        sender,
        client_factory=lambda *args, **kwargs: client,
    )
    subscriber.publish_delivery_result(
        DeliveryResult("request-1", "+44*******000", "sent")
    )
    topic, payload, qos, retain = client.published[-1]
    assert_equal(topic, sms_result_topic("request-1"), "result topic")
    assert_equal(json.loads(payload)["status"], "sent", "result status")
    assert_equal((qos, retain), (1, False), "result delivery settings")


def test_subscriber_closes_gracefully() -> None:
    """Check shutdown drains the sender, publishes offline, and disconnects."""

    sender = FakeSender()
    client = FakeSmsClient()
    subscriber = SMSSubscriber(
        MqttConfig(broker="mosquitto"),
        sender,
        client_factory=lambda *args, **kwargs: client,
    )
    subscriber.close()
    assert_equal(sender.closed, True, "sender closed")
    assert_equal(json.loads(client.published[-1][1])["state"], "offline", "offline status")
    assert_equal(client.disconnected, True, "MQTT disconnected")


def test_queue_fans_out_and_stops_cleanly() -> None:
    """Check the real worker delivers once per recipient and joins on close."""

    sender = SmsSender(
        ["+447700900000", "+447700900001"], quiet_logger(), dry_run=True
    )
    results: list[DeliveryResult] = []
    sender.set_result_handler(results.append)
    assert_equal(sender.broadcast(request()), True, "queue accepted")
    sender.queue.join()
    sender.close()
    assert_equal(len(results), 2, "recipient fan-out")
    assert_equal(
        [result.status for result in results], ["logged", "logged"], "delivery results"
    )
    assert_equal(sender.worker.is_alive(), False, "worker stopped")


def test_dry_run_reports_logged_not_sent() -> None:
    """Check dry-run delivery results cannot be mistaken for a real SMS."""

    sender = SmsSender(["+447700900000"], quiet_logger(), dry_run=True)
    results: list[DeliveryResult] = []
    sender.set_result_handler(results.append)
    sender.broadcast(request())
    sender.queue.join()
    sender.close()
    assert_equal(results[0].status, "logged", "dry-run status")


def test_mmcli_sends_and_deletes_created_object() -> None:
    """Check ModemManager create, send, and storage cleanup commands."""

    calls: list[list[str]] = []

    def runner(command: list[str], **_kwargs: object) -> object:
        """Return deterministic mmcli output and record commands."""

        calls.append(command)
        if command == ["mmcli", "-L"]:
            stdout = "/org/freedesktop/ModemManager1/Modem/7 [Test Modem]\n"
        elif command[:4] == ["mmcli", "-m", "7", "--messaging-create-sms"]:
            stdout = "Successfully created new SMS: /org/freedesktop/ModemManager1/SMS/12\n"
        else:
            stdout = ""
        return type("Completed", (), {"stdout": stdout, "stderr": "", "returncode": 0})()

    sender = SmsSender(
        ["+447700900000"],
        quiet_logger(),
        dry_run=False,
        runner=runner,
        retries=1,
    )
    try:
        assert_equal(sender.send_sms("+447700900000", "hello"), True, "mmcli send")
    finally:
        sender.close()
    assert_equal(calls[0], ["mmcli", "-L"], "list modems")
    assert_equal(
        calls[-2],
        ["mmcli", "-s", "/org/freedesktop/ModemManager1/SMS/12", "--send"],
        "send command",
    )
    assert_equal(
        calls[-1],
        [
            "mmcli",
            "-m",
            "7",
            "--messaging-delete-sms=/org/freedesktop/ModemManager1/SMS/12",
        ],
        "delete command",
    )


def test_retry_does_not_sleep_after_final_failure() -> None:
    """Check retry delays occur only between attempts."""

    sleeps: list[float] = []

    def runner(command: list[str], **_kwargs: object) -> object:
        """Fail SMS creation while allowing modem discovery."""

        if command == ["mmcli", "-L"]:
            return type(
                "Completed",
                (),
                {
                    "stdout": "/org/freedesktop/ModemManager1/Modem/7\n",
                    "stderr": "",
                    "returncode": 0,
                },
            )()
        raise subprocess.CalledProcessError(1, command, stderr="failed")

    sender = SmsSender(
        ["+447700900000"],
        quiet_logger(),
        dry_run=False,
        runner=runner,
        retries=2,
        retry_delay_seconds=3,
        sleeper=sleeps.append,
    )
    try:
        assert_equal(sender.send_sms("+447700900000", "hello"), False, "failed send")
    finally:
        sender.close()
    assert_equal(sleeps, [3], "between-attempt sleep")


def test_message_formatting_and_privacy_helpers() -> None:
    """Check concise formatting, mmcli quoting, and recipient masking."""

    formatted = format_sms_message(request())
    assert_equal(formatted.count("Pump Room / Flow 1"), 1, "identity not duplicated")
    assert_contains(formatted, "Current Measurement: 0.2", "current measurement")
    assert_equal(
        formatted.endswith(UNSUBSCRIBE_FOOTER), True, "warning unsubscribe footer"
    )
    recovery = format_sms_message(request("recovery-message", "recovery"))
    assert_equal(
        UNSUBSCRIBE_FOOTER in recovery, False, "recovery has no warning footer"
    )
    notification = format_sms_message(request("notification-message", "notification"))
    assert_equal(
        UNSUBSCRIBE_FOOTER in notification,
        False,
        "notification does not gain duplicate warning footer",
    )
    missing_measurement = request().model_copy(update={"current_measurement": "unknown"})
    assert_equal(
        "Current Measurement:" in format_sms_message(missing_measurement),
        False,
        "missing measurement line removed",
    )
    assert_equal(mask_phone_number("+447700900000"), "+44*******000", "masked number")
    assert_equal(quote_mmcli_value("Dave's lab"), "'Dave\\'s lab'", "mmcli quote")


def test_shared_sms_template_catalogue() -> None:
    """Check all runtime SMS wording comes from the shared YAML catalogue."""

    templates = load_sms_templates()
    assert_equal(TEMPLATE_PATH.name, "sms_templates.yaml", "catalogue filename")
    assert_equal(
        templates["formatting"]["unsubscribe_footer"],
        UNSUBSCRIBE_FOOTER,
        "footer source",
    )
    assert_equal(
        templates["commands"]["unsubscribe_confirmation"],
        UNSUBSCRIBE_CONFIRMATION,
        "unsubscribe confirmation source",
    )
    assert_equal(
        templates["commands"]["subscribe_confirmation"],
        SUBSCRIBE_CONFIRMATION,
        "subscribe confirmation source",
    )
    assert_equal(len(templates["alerts"]), 10, "alert template pairs")
    for name, alert in templates["alerts"].items():
        assert_equal("[TEST]" in alert["title"], False, f"{name} central test prefix")
        assert_contains(
            alert["message"], CURRENT_MEASUREMENT_PLACEHOLDER, f"{name} current measurement"
        )
    phone_book = templates["notifications"]["phone_book"]
    assert_equal("[TEST]" in phone_book["title"], False, "notification test prefix")
    assert_contains(
        phone_book["title"],
        "LabPulse Phone Book Notification",
        "phone book notification title",
    )
    for expected in (
        "t.k.davey@lancaster.ac.uk",
        "UNSUBSCRIBE",
        "SUBSCRIBE",
        "No action is required.",
        "triggered manually from the LabPulse dashboard",
    ):
        assert_contains(phone_book["message"], expected, "phone book notification")


TESTS = [
    ("setup and Compose contract", test_setup_and_compose_contract),
    ("SMS entry accepts explicit argv", test_sms_entry_accepts_explicit_argv),
    ("SMS config validates recipients", test_sms_config_validates_recipients),
    ("test mode routes only to test recipients", test_test_mode_routes_only_to_test_recipients),
    ("unsubscribed numbers filtered in both modes", test_unsubscribed_numbers_are_filtered_in_both_modes),
    ("subscription registry persists", test_subscription_registry_persists_and_rejects_outsiders),
    ("inbound commands are allow-listed", test_inbound_subscription_commands_are_allow_listed),
    ("mmcli received SMS parsing", test_mmcli_received_sms_parsing),
    ("test requests do not rate limit live alerts", test_test_requests_do_not_rate_limit_live_alerts),
    ("subscriber uses persistent QoS 1 session", test_subscriber_uses_persistent_qos_one_session),
    ("payload parser is strict", test_payload_parser_is_strict),
    ("subscriber deduplicates and rate limits", test_subscriber_deduplicates_and_rate_limits),
    ("recent request cache persists", test_recent_request_cache_persists),
    ("delivery results are published", test_delivery_results_are_published),
    ("subscriber closes gracefully", test_subscriber_closes_gracefully),
    ("queue fans out and stops cleanly", test_queue_fans_out_and_stops_cleanly),
    ("dry run reports logged not sent", test_dry_run_reports_logged_not_sent),
    ("mmcli sends and deletes created object", test_mmcli_sends_and_deletes_created_object),
    ("retry does not sleep after final failure", test_retry_does_not_sleep_after_final_failure),
    ("message formatting and privacy helpers", test_message_formatting_and_privacy_helpers),
    ("shared SMS template catalogue", test_shared_sms_template_catalogue),
]


def main() -> None:
    """Run SMS container and service tests."""

    print("Running SMS container tests")
    print(f"Refactor dir: {REFACTOR_DIR}\n")
    passed = 0
    for name, test_func in TESTS:
        try:
            test_func()
        except Exception as error:
            print(f"[FAIL] {name}\n  error: {type(error).__name__}: {error}\n")
            continue
        print(f"[PASS] {name}\n")
        passed += 1
    failed = len(TESTS) - passed
    print(f"Summary: {passed}/{len(TESTS)} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
