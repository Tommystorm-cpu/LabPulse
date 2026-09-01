from pathlib import Path
import subprocess
import sys
import textwrap
from typing import Any, Callable, TypeVar


REFACTOR_DIR = Path(__file__).resolve().parents[1]

from labpulse.common.service_config import ServiceConfig
from labpulse.hardware.driver import ContainerRequirements, HardwareDriver
from labpulse.hardware.drivers.dht11 import Dht11Config, Dht11Driver
from labpulse.hardware.registry import get_driver_definition
from labpulse.hardware.drivers.serial_pipe import (
    SerialPipeConfig,
    SerialPipeDriver,
)
from labpulse.hardware.drivers.x1200 import X1200Driver


TException = TypeVar("TException", bound=Exception)


def create_driver(service_name: str, service_config: ServiceConfig) -> HardwareDriver:
    """Construct a driver through the registry declaration under test."""

    definition = get_driver_definition(service_config.driver.type)
    return definition.create_driver(service_name, service_config.driver.options)


def make_service_config(**overrides: Any) -> ServiceConfig:
    """Build a valid serial ServiceConfig, with optional field overrides."""

    config = {
        "label": "Pump Room Sensor Hub",
        "driver": {
            "type": "labpulse.serial_pipe",
            "options": {
                "port": "/tmp/labpulse-fake-serial/pump_room",
                "baud_rate": 9600,
            },
        },
        "measurements": {
            "flow1": {"label": "Flow 1", "setups": ["test_setup"], "unit": "L/min"}
        },
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

    driver = create_driver("pump_room", service_config)

    assert_equal(isinstance(driver, SerialPipeDriver), True, "driver type")
    assert_equal(driver.service_name, "pump_room", "service name")
    assert_equal(driver.port, "/tmp/labpulse-fake-serial/pump_room", "port")
    assert_equal(driver.baud_rate, 9600, "baud rate")


def test_serial_factory_keeps_gpio_dependencies_unloaded() -> None:
    """Check a serial worker never imports the DHT module or GPIO stack."""

    script = textwrap.dedent(
        f"""
        import sys

        sys.path.insert(0, {str(REFACTOR_DIR / "src")!r})

        from labpulse.common.service_config import ServiceConfig
        from labpulse.hardware.registry import get_driver_definition

        dht_dependency = "adafruit_dht"
        if dht_dependency in sys.modules:
            raise AssertionError("registry import eagerly loaded the DHT library")

        config = ServiceConfig(
            label="Pump Room Sensor Hub",
            driver={{
                "type": "labpulse.serial_pipe",
                "options": {{
                    "port": "/tmp/labpulse-fake-serial/pump_room",
                    "baud_rate": 9600,
                }},
            }},
            measurements={{
                "flow1": {{"label": "Flow 1", "setups": ["test_setup"], "unit": "L/min"}}
            }},
        )
        definition = get_driver_definition(config.driver.type)
        definition.create_driver("pump_room", config.driver.options)

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
        measurements={
            "temperature": {"label": "Temperature", "setups": ["test_setup"], "unit": "°C"},
            "humidity": {"label": "Humidity", "setups": ["test_setup"], "unit": "%"},
        },
    )

    driver = create_driver("room_environment", service_config)

    assert_equal(isinstance(driver, Dht11Driver), True, "driver type")
    assert_equal(driver.service_name, "room_environment", "service name")
    assert_equal(driver.pin_name, "D4", "pin")


def test_config_loading_applies_driver_defaults_and_registry_reports_ids() -> None:
    """Validate once through ServiceConfig and report unknown driver IDs."""

    service_config = make_service_config(
        driver={
            "type": "labpulse.serial_pipe",
            "options": {"port": "/tmp/serial"},
        }
    )
    driver_config = service_config.driver.options
    assert_equal(isinstance(driver_config, SerialPipeConfig), True, "config type")
    assert_equal(driver_config.baud_rate, 9600, "default baud rate")
    message = assert_raises(
        ValueError,
        "Available drivers: labpulse.dht11, labpulse.serial_pipe, "
        "labpulse.sht40, labpulse.x1200",
        lambda: get_driver_definition("example.unknown"),
    )
    if "example.unknown" not in message:
        raise AssertionError("unknown driver error omitted the requested ID")


def test_driver_definitions_declare_class_and_requirements_function() -> None:
    """Keep driver construction and container access plainly declared."""

    definition = get_driver_definition("labpulse.serial_pipe")
    assert_equal(definition.driver_class, SerialPipeDriver, "driver class")
    assert_equal(hasattr(definition, "build"), False, "legacy builder field")

    dht_requirements = get_driver_definition(
        "labpulse.dht11"
    ).container_requirements(
        Dht11Config(pin="D4"),
        False,
    )
    assert_equal(
        dht_requirements,
        ContainerRequirements(mounts=("/dev:/dev",), privileged=True),
        "fixed DHT resources",
    )


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
        measurements={
            "voltage": {"unit": "V"},
            "battery_level": {"unit": "%"},
            "mains_present": {"state_class": None},
        },
    )

    driver = create_driver("ups_monitor", service_config)
    assert_equal(isinstance(driver, X1200Driver), True, "driver type")
    assert_equal(driver.bus_number, 1, "I2C bus")
    assert_equal(driver.address, 0x36, "I2C address")
