from pathlib import Path
import sys
from typing import Any, Callable, TypeVar


REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.config import ServiceConfig
from labpulse_hardware.drivers.dht11_driver import Driver as Dht11Driver
from labpulse_hardware.drivers.factory import build_driver
from labpulse_hardware.drivers.max17043_ups_driver import Driver as Max17043UpsDriver
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

    service_config = make_service_config()

    driver = build_driver("pump_room", service_config)

    assert_equal(isinstance(driver, SerialDriver), True, "driver type")
    assert_equal(driver.name, "pump_room", "driver name")
    assert_equal(driver.port, "/tmp/labpulse-fake-serial/pump_room", "port")
    assert_equal(driver.baud_rate, 9600, "baud rate")
    assert_equal(driver.parser_type, "pump_room", "parser")
    assert_equal(driver.reconnect_interval_seconds, 5.0, "reconnect interval")


def test_serial_config_requires_port() -> None:
    """Check that serial services fail clearly without serial_port."""

    service_config = make_service_config(serial_port=None)

    assert_raises(
        ValueError,
        "missing serial_port",
        lambda: build_driver("pump_room", service_config),
    )


def test_serial_config_requires_parser() -> None:
    """Check that serial services fail clearly without parser."""

    service_config = make_service_config(parser=None)

    assert_raises(
        ValueError,
        "missing parser",
        lambda: build_driver("pump_room", service_config),
    )


def test_gpio_dht11_driver_builds() -> None:
    """Check that a GPIO DHT11 service creates a Dht11Driver."""

    service_config = make_service_config(
        driver="gpio",
        gpio_sensor="dht11",
        gpio_pin="D4",
        parser=None,
        serial_port=None,
        read_interval_seconds=3.0,
        readings=[
            {"name": "temperature", "label": "Temperature", "unit": "\u00b0C"},
            {"name": "humidity", "label": "Humidity", "unit": "%"},
        ],
    )

    driver = build_driver("room_environment", service_config)

    assert_equal(isinstance(driver, Dht11Driver), True, "driver type")
    assert_equal(driver.name, "room_environment", "driver name")
    assert_equal(driver.pin_name, "D4", "pin")
    assert_equal(driver.read_interval_seconds, 3.0, "read interval")


def test_gpio_dht11_requires_pin() -> None:
    """Check that DHT11 services fail clearly without gpio_pin."""

    service_config = make_service_config(
        driver="gpio",
        gpio_sensor="dht11",
        gpio_pin=None,
        parser=None,
        serial_port=None,
    )

    assert_raises(
        ValueError,
        "missing gpio_pin",
        lambda: build_driver("room_environment", service_config),
    )


def test_max17043_i2c_driver_builds() -> None:
    """Check validated MAX17043 settings reach the concrete I2C driver."""

    service_config = make_service_config(
        driver="i2c",
        parser=None,
        serial_port=None,
        i2c_sensor="max17043_ups",
        i2c_bus=1,
        i2c_address=0x36,
        power_detection={},
        readings=[
            {"name": "voltage", "unit": "V"},
            {"name": "battery_level", "unit": "%"},
        ],
    )

    driver = build_driver("ups_monitor", service_config)
    assert_equal(isinstance(driver, Max17043UpsDriver), True, "driver type")
    assert_equal(driver.bus_number, 1, "I2C bus")
    assert_equal(driver.address, 0x36, "I2C address")


TESTS = [
    ("serial driver builds", test_serial_driver_builds),
    ("serial config requires port", test_serial_config_requires_port),
    ("serial config requires parser", test_serial_config_requires_parser),
    ("gpio DHT11 driver builds", test_gpio_dht11_driver_builds),
    ("gpio DHT11 requires pin", test_gpio_dht11_requires_pin),
    ("MAX17043 I2C driver builds", test_max17043_i2c_driver_builds),
]


def main() -> None:
    """Run all driver factory test cases."""

    print("Running driver factory tests")
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
