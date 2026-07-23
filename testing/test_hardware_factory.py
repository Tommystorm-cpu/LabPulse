from pathlib import Path
import subprocess
import sys
import textwrap
from typing import Any, Callable, TypeVar


REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR / "src"))

from labpulse.common.config import ServiceConfig
from labpulse.hardware.drivers.dht11 import Driver as Dht11Driver
from labpulse.hardware.registry import build_driver, get_driver_spec
from labpulse.hardware.drivers.serial_pipe import (
    Driver as SerialDriver,
    SerialPipeOptions,
)
from labpulse.hardware.drivers.x1200 import Driver as X1200UpsDriver


TException = TypeVar("TException", bound=Exception)


def make_service_config(**overrides: Any) -> ServiceConfig:
    """Build a valid serial ServiceConfig, with optional field overrides."""

    config = {
        "driver": {
            "type": "labpulse.serial_pipe",
            "options": {
                "port": "/tmp/labpulse-fake-serial/pump_room",
                "baud_rate": 9600,
            },
        },
        "reconnect_interval_seconds": 5.0,
        "device_name": "Pump Room Sensor Hub",
        "measurements": [{"name": "flow1", "label": "Flow 1", "setups": ["test_setup"], "unit": "L/min"}],
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


def test_serial_factory_keeps_gpio_dependencies_unloaded() -> None:
    """Check a serial worker never imports the DHT module or GPIO stack."""

    script = textwrap.dedent(
        f"""
        import sys

        sys.path.insert(0, {str(REFACTOR_DIR / "src")!r})

        from labpulse.common.config import ServiceConfig
        from labpulse.hardware.registry import build_driver

        dht_dependency = "adafruit_dht"
        if dht_dependency in sys.modules:
            raise AssertionError("registry import eagerly loaded the DHT library")

        config = ServiceConfig(
            driver={{
                "type": "labpulse.serial_pipe",
                "options": {{
                    "port": "/tmp/labpulse-fake-serial/pump_room",
                    "baud_rate": 9600,
                }},
            }},
            reconnect_interval_seconds=5.0,
            device_name="Pump Room Sensor Hub",
            measurements=[{{"name": "flow1", "label": "Flow 1", "setups": ["test_setup"], "unit": "L/min"}}],
        )
        build_driver("pump_room", config)

        if "board" in sys.modules or dht_dependency in sys.modules:
            raise AssertionError("serial driver construction loaded the GPIO stack")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            "Serial factory isolation subprocess failed:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def test_serial_config_requires_port() -> None:
    """Check that serial services fail clearly without a driver port."""

    assert_raises(
        ValueError,
        "port",
        lambda: make_service_config(
            driver={"type": "labpulse.serial_pipe", "options": {}}
        ),
    )


def test_parser_config_is_rejected() -> None:
    """Check that the removed parser selector cannot return to config."""

    assert_raises(
        ValueError,
        "Extra inputs are not permitted",
        lambda: make_service_config(
            driver={
                "type": "labpulse.serial_pipe",
                "options": {
                    "port": "/tmp/labpulse-fake-serial/pump_room",
                    "parser": "pressure",
                },
            }
        ),
    )


def test_gpio_dht11_driver_builds() -> None:
    """Check that a GPIO DHT11 service creates a Dht11Driver."""

    service_config = make_service_config(
        driver={"type": "labpulse.dht11", "options": {"pin": "D4"}},
        read_interval_seconds=3.0,
        measurements=[
            {"name": "temperature", "label": "Temperature", "setups": ["test_setup"], "unit": "\u00b0C"},
            {"name": "humidity", "label": "Humidity", "setups": ["test_setup"], "unit": "%"},
        ],
    )

    driver = build_driver("room_environment", service_config)

    assert_equal(isinstance(driver, Dht11Driver), True, "driver type")
    assert_equal(driver.name, "room_environment", "driver name")
    assert_equal(driver.pin_name, "D4", "pin")


def test_registry_validates_options_and_reports_available_ids() -> None:
    """Keep driver-owned defaults and unknown-ID errors at the registry seam."""

    options = get_driver_spec("labpulse.serial_pipe").validate_options(
        {"port": "/tmp/serial"}
    )
    assert_equal(isinstance(options, SerialPipeOptions), True, "options type")
    assert_equal(options.baud_rate, 9600, "default baud rate")
    message = assert_raises(
        ValueError,
        "Available drivers: labpulse.dht11, labpulse.serial_pipe, labpulse.x1200",
        lambda: get_driver_spec("example.unknown"),
    )
    if "example.unknown" not in message:
        raise AssertionError("unknown driver error omitted the requested ID")


def test_gpio_dht11_requires_pin() -> None:
    """Check that DHT11 services fail clearly without a driver pin."""

    assert_raises(
        ValueError,
        "pin",
        lambda: make_service_config(
            driver={"type": "labpulse.dht11", "options": {}}
        ),
    )


def test_x1200_i2c_gpio_driver_builds() -> None:
    """Check validated I2C and GPIO settings reach the X1200 driver."""

    service_config = make_service_config(
        driver={
            "type": "labpulse.x1200",
            "options": {
                "bus": 1,
                "address": 0x36,
                "gpio_chip": "/dev/gpiochip0",
                "gpio_line": 6,
                "mains_present_active_high": True,
            },
        },
        power_detection={},
        measurements=[
            {"name": "voltage", "unit": "V"},
            {"name": "battery_level", "unit": "%"},
            {"name": "mains_present", "state_class": None},
        ],
    )

    driver = build_driver("ups_monitor", service_config)
    assert_equal(isinstance(driver, X1200UpsDriver), True, "driver type")
    assert_equal(driver.bus_number, 1, "I2C bus")
    assert_equal(driver.address, 0x36, "I2C address")
    assert_equal(driver.gpio_reader.chip, "/dev/gpiochip0", "GPIO chip")
    assert_equal(driver.gpio_reader.line, 6, "GPIO line")


TESTS = [
    ("serial driver builds", test_serial_driver_builds),
    (
        "serial factory keeps GPIO dependencies unloaded",
        test_serial_factory_keeps_gpio_dependencies_unloaded,
    ),
    ("serial config requires port", test_serial_config_requires_port),
    ("parser config is rejected", test_parser_config_is_rejected),
    (
        "registry validates options and reports IDs",
        test_registry_validates_options_and_reports_available_ids,
    ),
    ("gpio DHT11 driver builds", test_gpio_dht11_driver_builds),
    ("gpio DHT11 requires pin", test_gpio_dht11_requires_pin),
    ("X1200 I2C/GPIO driver builds", test_x1200_i2c_gpio_driver_builds),
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
