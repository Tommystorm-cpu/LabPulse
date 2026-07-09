from pathlib import Path
import sys

sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.config import MqttConfig
from labpulse_sms.sms_entry import DEFAULT_CONFIG_PATH, parse_args
from labpulse_sms.sms_subscriber import SMS_TOPIC, SMSSubscriber


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
    assert_contains(compose_script, '["python", "labpulse_sms/sms_entry.py"', "SMS entry command")


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

    subscriber = SMSSubscriber(MqttConfig(broker="mosquitto", port=1883))
    fake_client = FakeSmsClient()
    subscriber.client = fake_client

    subscriber.connect()
    assert_equal(fake_client.connected_to, ("mosquitto", 1883, 60), "MQTT connection")
    if fake_client.on_connect is None:
        raise AssertionError("connect callback should be registered")
    if fake_client.on_message is None:
        raise AssertionError("message callback should be registered")

    subscriber.on_connect(fake_client, None, None, 0, None)
    assert_equal(fake_client.subscriptions, [SMS_TOPIC], "SMS topic subscription")


TESTS = [
    ("setup copies SMS package into image", test_setup_copies_sms_package_into_image),
    ("compose generates one SMS container", test_compose_generates_one_sms_container),
    ("SMS entry defaults to app config", test_sms_entry_defaults_to_app_config),
    ("SMS subscriber subscribes to SMS topic", test_sms_subscriber_subscribes_to_sms_topic),
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
