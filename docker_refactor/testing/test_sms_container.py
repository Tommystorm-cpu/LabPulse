from pathlib import Path
import sys

sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.config import MqttConfig
from labpulse_sms.sender import LogSmsSender, MmcliSmsSender, format_sms_message, quote_mmcli_value
from labpulse_sms.sms_entry import DEFAULT_CONFIG_PATH, parse_args
from labpulse_common.mqtt_contracts import SMS_SUBSCRIPTION_TOPIC
from labpulse_sms.sms_subscriber import SMSSubscriber, parse_sms_payload


class FakeSmsClient:
    """Small MQTT client stand-in for SMS subscriber tests."""

    def __init__(self) -> None:
        self.on_connect = None
        self.on_message = None
        self.connected_to: tuple[str, int, int] | None = None
        self.subscriptions: list[str] = []

    def connect(self, broker: str, port: int, keepalive: int) -> None:
        """Record MQTT connection arguments."""

        self.connected_to = (broker, port, keepalive)

    def subscribe(self, topic: str) -> None:
        """Record MQTT subscription topics."""

        self.subscriptions.append(topic)


class FakeSender:
    """Small SMS sender stand-in for subscriber tests."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def broadcast(self, message: str) -> None:
        """Record outbound SMS messages."""

        self.messages.append(message)


def assert_contains(text: str, expected: str, label: str) -> None:
    """Raise AssertionError when expected text is missing."""

    if expected not in text:
        raise AssertionError(f"{label}: missing {expected!r}")


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise AssertionError when two values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_setup_copies_sms_package_into_image() -> None:
    """Check setup copies the SMS package into the Docker build context."""

    setup_script = (REFACTOR_DIR / "setup_container_fs.sh").read_text(encoding="utf-8")
    assert_contains(setup_script, "COPY labpulse_hardware ./labpulse_hardware", "Dockerfile copies hardware package")
    assert_contains(setup_script, "COPY labpulse_sms ./labpulse_sms", "Dockerfile copies SMS package")
    assert_contains(
        setup_script,
        'replace_dir "$SCRIPT_DIR/labpulse_sms" "$PROJECT_DIR/labpulse-python/labpulse_sms"',
        "setup copies SMS package",
    )


def test_compose_generates_one_sms_container() -> None:
    """Check generated Compose includes one SMS container command."""

    compose_script = (REFACTOR_DIR / "generate_compose.sh").read_text(encoding="utf-8")
    assert_contains(compose_script, "labpulse-sms:", "SMS service")
    assert_contains(compose_script, "container_name: labpulse-sms", "SMS container name")
    assert_contains(compose_script, '["python", "-m", "labpulse_sms.sms_entry"', "SMS entry command")
    assert_contains(compose_script, 'labpulse_hardware.runner', "hardware module command")
    assert_contains(compose_script, 'sms_backend = str(sms_config.get("backend", "log")).lower()', "SMS backend read")
    assert_contains(compose_script, "- /run/dbus:/run/dbus:ro", "mmcli D-Bus mount")


def test_sms_entry_defaults_to_app_config() -> None:
    """Check sms_entry.py defaults to /app-style package-parent config."""

    assert_equal(DEFAULT_CONFIG_PATH.name, "config.yaml", "default config filename")
    assert_equal(DEFAULT_CONFIG_PATH.parent.name, "docker_refactor", "repo default config parent")

    original_argv = sys.argv[:]
    try:
        sys.argv = ["sms_entry.py", "--config", "custom.yaml"]
        args = parse_args()
    finally:
        sys.argv = original_argv

    assert_equal(args.config, "custom.yaml", "custom config argument")


def test_sms_subscriber_subscribes_to_sms_topic() -> None:
    """Check the SMS subscriber subscribes to the SMS MQTT namespace."""

    subscriber = SMSSubscriber(MqttConfig(broker="mosquitto", port=1883), FakeSender())
    fake_client = FakeSmsClient()
    subscriber.client = fake_client

    subscriber.connect()
    assert_equal(fake_client.connected_to, ("mosquitto", 1883, 60), "MQTT connection")
    if fake_client.on_connect is None:
        raise AssertionError("connect callback should be registered")
    if fake_client.on_message is None:
        raise AssertionError("message callback should be registered")

    subscriber.on_connect(fake_client, None, None, 0, None)
    assert_equal(fake_client.subscriptions, [SMS_SUBSCRIPTION_TOPIC], "SMS topic subscription")


def test_sms_payload_parser_keeps_service_and_reading() -> None:
    """Check SMS JSON payloads preserve alarm identity fields."""

    payload = (
        b'{"event":"alert","service":"pressure_monitor","reading":"pressure",'
        b'"entity_id":"binary_sensor.labpulse_pressure_monitor_pressure_alarm",'
        b'"message":"Pressure tripped"}'
    )
    parsed = parse_sms_payload(payload)

    assert_equal(parsed["service"], "pressure_monitor", "payload service")
    assert_equal(parsed["reading"], "pressure", "payload reading")
    assert_equal(
        parsed["entity_id"],
        "binary_sensor.labpulse_pressure_monitor_pressure_alarm",
        "payload entity",
    )

    fallback = parse_sms_payload(b"plain text")
    assert_equal(fallback["message"], "plain text", "plain text fallback")


def test_sms_subscriber_broadcasts_formatted_message() -> None:
    """Check inbound MQTT payloads are formatted and queued for sending."""

    sender = FakeSender()
    subscriber = SMSSubscriber(MqttConfig(broker="mosquitto", port=1883), sender)

    message = type("Message", (), {})()
    message.payload = (
        b'{"title":"LabPulse alarm","service_label":"Pump Room",'
        b'"reading_label":"Flow 1","message":"Flow 1 alarm is active.",'
        b'"current":"0.2"}'
    )
    subscriber.on_message(None, None, message)

    assert_equal(len(sender.messages), 1, "broadcast count")
    assert_contains(sender.messages[0], "Pump Room / Flow 1", "formatted identity")
    assert_contains(sender.messages[0], "Current: 0.2", "formatted current value")


def test_log_sender_queues_one_message_per_recipient() -> None:
    """Check log backend accepts messages without contacting hardware."""

    logger = type("Logger", (), {"info": lambda *_args: None, "warning": lambda *_args: None})()
    sender = LogSmsSender(["+441", "+442"], logger)

    assert_equal(sender.send_sms("+441", "hello"), True, "log sender success")


def test_mmcli_sender_uses_modemmanager_commands() -> None:
    """Check mmcli backend creates and sends an SMS without real hardware."""

    calls: list[list[str]] = []

    def runner(command: list[str], **_kwargs: object):
        calls.append(command)
        if command == ["mmcli", "-L"]:
            stdout = "/org/freedesktop/ModemManager1/Modem/7 [Test Modem]\n"
        elif command[:4] == ["mmcli", "-m", "7", "--messaging-create-sms"]:
            stdout = "Successfully created new SMS: /org/freedesktop/ModemManager1/SMS/12\n"
        elif command == ["mmcli", "-s", "/org/freedesktop/ModemManager1/SMS/12", "--send"]:
            stdout = ""
        else:
            raise AssertionError(f"unexpected command: {command!r}")
        return type("Completed", (), {"stdout": stdout, "stderr": "", "returncode": 0})()

    logger = type(
        "Logger",
        (),
        {
            "info": lambda *_args: None,
            "warning": lambda *_args: None,
            "error": lambda *_args: None,
            "exception": lambda *_args: None,
        },
    )()
    sender = MmcliSmsSender(["+441"], logger, runner=runner, retries=1, retry_delay_seconds=0)

    assert_equal(sender.send_sms("+441", "hello"), True, "mmcli send success")
    assert_equal(calls[0], ["mmcli", "-L"], "list modems command")
    assert_equal(calls[-1], ["mmcli", "-s", "/org/freedesktop/ModemManager1/SMS/12", "--send"], "send command")


def test_sms_message_helpers_quote_and_format() -> None:
    """Check mmcli quoting and user-facing message formatting."""

    assert_equal(quote_mmcli_value("Dave's lab"), "'Dave\\'s lab'", "mmcli quote")
    formatted = format_sms_message({"title": "Title", "service": "pump", "reading": "flow"})
    assert_contains(formatted, "pump / flow", "fallback labels")


TESTS = [
    ("setup copies SMS package into image", test_setup_copies_sms_package_into_image),
    ("compose generates one SMS container", test_compose_generates_one_sms_container),
    ("SMS entry defaults to app config", test_sms_entry_defaults_to_app_config),
    ("SMS subscriber subscribes to SMS topic", test_sms_subscriber_subscribes_to_sms_topic),
    ("SMS payload parser keeps service and reading", test_sms_payload_parser_keeps_service_and_reading),
    ("SMS subscriber broadcasts formatted message", test_sms_subscriber_broadcasts_formatted_message),
    ("log sender queues one message per recipient", test_log_sender_queues_one_message_per_recipient),
    ("mmcli sender uses ModemManager commands", test_mmcli_sender_uses_modemmanager_commands),
    ("SMS message helpers quote and format", test_sms_message_helpers_quote_and_format),
]


def main() -> None:
    """Run SMS container setup tests."""

    print("Running SMS container tests")
    print(f"Refactor dir: {REFACTOR_DIR}")
    print()

    passed_count = 0
    for name, test_func in TESTS:
        try:
            test_func()
        except Exception as error:
            print(f"[FAIL] {name}")
            print(f"  error: {type(error).__name__}: {error}")
            print()
            continue

        print(f"[PASS] {name}")
        print()
        passed_count += 1

    total = len(TESTS)
    failed_count = total - passed_count
    print(f"Summary: {passed_count}/{total} passed, {failed_count} failed")

    if failed_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
