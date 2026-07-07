from pathlib import Path
import sys


REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.config import ServiceConfig
from labpulse_common.drivers.serial_driver import Driver as SerialDriver
from labpulse_common.sensor_factory import SensorFactory


def make_service_config(**overrides):
    config = {
        "driver": "serial",
        "parser": "pump_room",
        "serial_port": "/tmp/labpulse-fake-serial/pump_room",
        "baud_rate": 9600,
        "device_name": "Pump Room Sensor Hub",
        "metric_prefix": "pump",
    }
    config.update(overrides)
    return ServiceConfig(**config)


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_raises(expected_error, expected_message, func):
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


def test_serial_driver_builds():
    factory = SensorFactory()
    service_config = make_service_config()

    driver = factory.build("pump_room", service_config)

    assert_equal(isinstance(driver, SerialDriver), True, "driver type")
    assert_equal(driver.name, "pump_room", "driver name")
    assert_equal(driver.config["port"], "/tmp/labpulse-fake-serial/pump_room", "port")
    assert_equal(driver.config["baud_rate"], 9600, "baud rate")
    assert_equal(driver.config["parser"], "pump_room", "parser")


def test_serial_config_requires_port():
    factory = SensorFactory()
    service_config = make_service_config(serial_port=None)

    assert_raises(
        ValueError,
        "missing serial_port",
        lambda: factory.build("pump_room", service_config),
    )


def test_serial_config_requires_parser():
    factory = SensorFactory()
    service_config = make_service_config(parser=None)

    assert_raises(
        ValueError,
        "missing parser",
        lambda: factory.build("pump_room", service_config),
    )


def test_gpio_slot_exists_but_is_not_implemented():
    factory = SensorFactory()
    service_config = make_service_config(driver="gpio", parser=None, serial_port=None)

    assert_raises(
        NotImplementedError,
        "GPIO driver support is not implemented yet",
        lambda: factory.build("dht_room_sensor", service_config),
    )


def test_i2c_slot_exists_but_is_not_implemented():
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


def main():
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
