"""Fake DHT11 driver tests for test Raspberry Pi deployments."""

from pathlib import Path
import sys
from typing import Any, Callable
from uuid import uuid4


sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_hardware.drivers.fake_dht11_driver import Driver


TEST_TMP_DIR = REFACTOR_DIR / "testing" / "tmp"


def make_driver(path: Path, **overrides: Any) -> Driver:
    """Build a fake DHT11 driver pointed at a test state file."""

    config = {"state_file": str(path), "read_interval_seconds": 0.01}
    config.update(overrides)
    return Driver("room_environment", config)


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise AssertionError when two values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_setup_creates_default_state_file() -> None:
    """Check setup creates a usable fake DHT state file."""

    state_file = TEST_TMP_DIR / f"fake-dht-{uuid4().hex}" / "room_environment.env"
    driver = make_driver(state_file)

    assert_equal(driver.setup(), True, "setup")
    assert_equal(state_file.exists(), True, "state file exists")
    assert_equal(driver.read(), {"temperature": 21.5, "humidity": 48.0}, "default reading")


def test_live_state_file_updates_are_read() -> None:
    """Check changing the file changes subsequent readings without reconnect."""

    state_file = TEST_TMP_DIR / f"fake-dht-{uuid4().hex}" / "room_environment.env"
    driver = make_driver(state_file)
    driver.setup()

    state_file.write_text("temperature=5.25\nhumidity=81.44\n", encoding="utf-8")
    assert_equal(driver.read(), {"temperature": 5.2, "humidity": 81.4}, "first reading")

    driver.last_read_at = 0.0
    state_file.write_text("temperature=22.0\nhumidity=45.0\n", encoding="utf-8")
    assert_equal(driver.read(), {"temperature": 22.1, "humidity": 45.1}, "updated reading")


def test_stale_mode_keeps_values_constant() -> None:
    """Check mode=stale deliberately emits unchanged values."""

    state_file = TEST_TMP_DIR / f"fake-dht-{uuid4().hex}" / "room_environment.env"
    driver = make_driver(state_file)
    driver.setup()

    state_file.write_text("mode=stale\ntemperature=22.0\nhumidity=45.0\n", encoding="utf-8")
    assert_equal(driver.read(), {"temperature": 22.0, "humidity": 45.0}, "first reading")

    driver.last_read_at = 0.0
    assert_equal(driver.read(), {"temperature": 22.0, "humidity": 45.0}, "stale reading")


def test_invalid_state_file_sets_error_status() -> None:
    """Check malformed fake files fail visibly without crashing."""

    state_file = TEST_TMP_DIR / f"fake-dht-{uuid4().hex}" / "room_environment.env"
    driver = make_driver(state_file)
    driver.setup()

    state_file.write_text("temperature=not-a-number\nhumidity=50\n", encoding="utf-8")
    assert_equal(driver.read(), None, "bad reading")
    assert_equal(driver.get_status(), "error", "status")


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("setup creates default state file", test_setup_creates_default_state_file),
    ("live state file updates are read", test_live_state_file_updates_are_read),
    ("stale mode keeps values constant", test_stale_mode_keeps_values_constant),
    ("invalid state file sets error status", test_invalid_state_file_sets_error_status),
]


def main() -> None:
    """Run all fake DHT11 driver tests."""

    print("Running fake DHT11 driver tests")
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

    failed_count = len(TESTS) - passed_count
    print(f"Summary: {passed_count}/{len(TESTS)} passed, {failed_count} failed")

    if failed_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
