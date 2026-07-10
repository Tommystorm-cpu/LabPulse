from pathlib import Path
import sys
from typing import Any, Callable, TypeVar


REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.config import ServiceConfig
from labpulse_hardware.drivers.factory import SensorFactory
from labpulse_hardware.drivers.serial_driver import Driver as SerialDriver


TException = TypeVar("TException", bound=Exception)


def make_service_config(**overrides: Any) -> ServiceConfig:
    """Build a valid serial ServiceConfig, with optional field overrides."""

    config = {
        "driver": "serial",
        "parser": "pump_room",
        "serial_port": "/tmp/labpulse-fake-serial/pump_room",
        "baud_rate": 9600,
        "reconnect_interval_seconds": 5.0,
        "device_name": "Pump Room Sensor Hub",
        "readings": [{"name": "flow1", "label": "Flow 1", "unit": "L/min"}],
    }
    config.update(overrides)
    return ServiceConfig(**config)


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise AssertionError when two values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_raises(
    expected_error: type[TException],
    expected_message: str,
    func: Callable[[], object],
) -> str:
    """Assert that a callable raises the expected error and message."""

    try:
        func()
    except expected_error as error:
        actual_message = str(error)
        if expected_message not in actual_message:
            raise AssertionError(
                f"Expected error message to contain {expected_message!r}, "
                f"got {actual_message!r}"
            )
        return actual_message

    raise AssertionError(f"Expected {expected_error.__name__} to be raised")


def test_serial_driver_builds() -> None:
    """Check that a serial service creates a SerialDriver with driver config."""

    factory = SensorFactory()
    service_config = make_service_config()

    driver = factory.build("pump_room", service_config)

    assert_equal(isinstance(driver, SerialDriver), True, "driver type")
    assert_equal(driver.name, "pump_room", "driver name")
    assert_equal(driver.config["port"], "/tmp/labpulse-fake-serial/pump_room", "port")
    assert_equal(driver.config["baud_rate"], 9600, "baud rate")
    assert_equal(driver.config["parser"], "pump_room", "parser")
    assert_equal(driver.config["reconnect_interval_seconds"], 5.0, "reconnect interval")


def test_serial_config_requires_port() -> None:
    """Check that serial services fail clearly without serial_port."""

    factory = SensorFactory()
    service_config = make_service_config(serial_port=None)

    assert_raises(
        ValueError,
        "missing serial_port",
        lambda: factory.build("pump_room", service_config),
    )


def test_serial_config_requires_parser() -> None:
    """Check that serial services fail clearly without parser."""

    factory = SensorFactory()
    service_config = make_service_config(parser=None)

    assert_raises(
        ValueError,
        "missing parser",
        lambda: factory.build("pump_room", service_config),
    )


def test_gpio_slot_exists_but_is_not_implemented() -> None:
    """Check that the GPIO factory slot exists as a placeholder."""

    factory = SensorFactory()
    service_config = make_service_config(driver="gpio", parser=None, serial_port=None)

    assert_raises(
        NotImplementedError,
        "GPIO driver support is not implemented yet",
        lambda: factory.build("dht_room_sensor", service_config),
    )


def test_i2c_slot_exists_but_is_not_implemented() -> None:
    """Check that the I2C factory slot exists as a placeholder."""

    factory = SensorFactory()
    service_config = make_service_config(driver="i2c", parser=None, serial_port=None)

    assert_raises(
        NotImplementedError,
        "I2C driver support is not implemented yet",
        lambda: factory.build("ups_hat", service_config),
    )


TESTS = [
    ("serial driver builds", test_serial_driver_builds),
    ("serial config requires port", test_serial_config_requires_port),
    ("serial config requires parser", test_serial_config_requires_parser),
    ("gpio slot exists but is not implemented", test_gpio_slot_exists_but_is_not_implemented),
    ("i2c slot exists but is not implemented", test_i2c_slot_exists_but_is_not_implemented),
]


def main() -> None:
    """Run all SensorFactory test cases."""

    print("Running SensorFactory tests")
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
