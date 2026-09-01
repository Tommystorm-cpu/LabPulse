"""Hardware-free contract tests for the Sensirion SHT40 driver."""

from collections.abc import Callable, Iterator
import sys
from typing import Any
from unittest.mock import patch

import yaml
from pydantic import ValidationError

from labpulse.common.config import LabPulseConfig
from labpulse.common.fake_config import derive_fake_config
from labpulse.common.service_config import ServiceConfig
from labpulse.hardware.driver import (
    ConnectionLost,
    ContainerRequirements,
    DriverUnavailable,
    TransientReadError,
)
from labpulse.hardware.drivers import sht40
from labpulse.hardware.drivers.sht40 import (
    MEASUREMENT_DELAY_SECONDS,
    MEASURE_HIGH_PRECISION,
    Sht40Config,
    Sht40Driver,
    crc8,
    decode_measurement,
)
from labpulse.hardware.registry import get_driver_definition


class FakeMessage:
    """Mutable stand-in for one smbus2 I2C message."""

    def __init__(self, operation: str, address: int, data: list[int]) -> None:
        """Store the message direction, address, and bytes."""

        self.operation = operation
        self.address = address
        self.data = data

    def __iter__(self) -> Iterator[int]:
        """Expose received bytes using the real smbus2 message interface."""

        return iter(self.data)


class FakeI2cMessageFactory:
    """Construct fake raw I2C read and write messages."""

    @staticmethod
    def write(address: int, data: list[int]) -> FakeMessage:
        """Return a one-way command message."""

        return FakeMessage("write", address, list(data))

    @staticmethod
    def read(address: int, length: int) -> FakeMessage:
        """Return a mutable response message of the requested length."""

        return FakeMessage("read", address, [0] * length)


class FakeBus:
    """In-memory SHT40 bus with a configurable response or read failure."""

    def __init__(
        self,
        response: list[int],
        read_error: Exception | None = None,
    ) -> None:
        """Store the response and track bus operations."""

        self.response = response
        self.read_error = read_error
        self.messages: list[FakeMessage] = []
        self.closed = False

    def i2c_rdwr(self, message: FakeMessage) -> None:
        """Capture writes and fill reads with the configured sample."""

        self.messages.append(message)
        if message.operation == "read":
            if self.read_error is not None:
                raise self.read_error
            message.data[:] = self.response

    def close(self) -> None:
        """Record release of the bus."""

        self.closed = True


class FakeSmbus2:
    """Minimal smbus2 module used by the driver."""

    i2c_msg = FakeI2cMessageFactory

    def __init__(self, bus: FakeBus) -> None:
        """Return one supplied bus for every open request."""

        self.bus = bus
        self.opened_bus_numbers: list[int] = []

    def SMBus(self, bus_number: int) -> FakeBus:
        """Record and return the requested fake bus."""

        self.opened_bus_numbers.append(bus_number)
        return self.bus


def response(raw_temperature: int, raw_humidity: int) -> list[int]:
    """Build one valid CRC-protected SHT40 response."""

    temperature = [(raw_temperature >> 8) & 0xFF, raw_temperature & 0xFF]
    humidity = [(raw_humidity >> 8) & 0xFF, raw_humidity & 0xFF]
    return [*temperature, crc8(temperature), *humidity, crc8(humidity)]


def install_fake_bus(
    payload: list[int] | None = None,
    read_error: Exception | None = None,
) -> tuple[FakeBus, FakeSmbus2]:
    """Patch the lazy I2C dependency with an in-memory bus."""

    bus = FakeBus(payload or response(0x6666, 0x8000), read_error)
    dependency = FakeSmbus2(bus)
    sys.modules["smbus2"] = dependency  # type: ignore[assignment]
    return bus, dependency


def make_driver() -> Sht40Driver:
    """Build one SHT40 driver using normal validated options."""

    return Sht40Driver("room_environment", Sht40Config(bus=1, address=0x44))


def assert_raises(expected: type[Exception], action: Callable[[], Any]) -> Exception:
    """Require one expected lifecycle exception and return it."""

    try:
        action()
    except expected as error:
        return error
    raise AssertionError(f"expected {expected.__name__}")


def test_crc_and_datasheet_conversion() -> None:
    """Match the documented CRC example and raw-value conversion equations."""

    assert crc8([0xBE, 0xEF]) == 0x92
    temperature, humidity = decode_measurement(response(0, 0xFFFF))
    assert temperature == -45.0
    assert humidity == 100.0


def test_connect_and_read_high_precision_sample() -> None:
    """Open the configured bus, issue 0xFD, wait, and normalize measurements."""

    delays: list[float] = []
    bus, dependency = install_fake_bus(response(0x6666, 0x8000))
    driver = make_driver()

    driver.connect()
    with patch.object(sht40.time, "sleep", side_effect=delays.append):
        batch = driver.read()

    assert dependency.opened_bus_numbers == [1]
    assert delays == [MEASUREMENT_DELAY_SECONDS]
    assert bus.messages[0].operation == "write"
    assert bus.messages[0].address == 0x44
    assert bus.messages[0].data == [MEASURE_HIGH_PRECISION]
    assert bus.messages[1].operation == "read"
    assert dict(batch.values) == {
        "temperature": 25.0,
        "humidity": 56.5,
    }


def test_crc_failure_is_a_transient_sample_error() -> None:
    """Keep the open connection when one response is corrupted."""

    payload = response(0x6666, 0x8000)
    payload[2] ^= 0xFF
    bus, _ = install_fake_bus(payload)
    driver = make_driver()
    driver.connect()

    with patch.object(sht40.time, "sleep", return_value=None):
        error = assert_raises(TransientReadError, driver.read)
    assert "temperature CRC mismatch" in str(error)
    assert bus.closed is False


def test_i2c_failure_loses_connection() -> None:
    """Classify a failed raw I2C transaction for runner-managed reconnect."""

    install_fake_bus(read_error=OSError("sensor missing"))
    driver = make_driver()
    driver.connect()

    with patch.object(sht40.time, "sleep", return_value=None):
        error = assert_raises(ConnectionLost, driver.read)
    assert "sensor missing" in str(error)


def test_missing_dependency_and_closed_bus_are_reported() -> None:
    """Fail clearly without smbus2 or without an established connection."""

    sys.modules["smbus2"] = None  # type: ignore[assignment]
    assert_raises(DriverUnavailable, make_driver().connect)
    assert_raises(ConnectionLost, make_driver().read)


def test_config_registry_and_resources_are_end_to_end() -> None:
    """Validate once, discover the driver, construct it, and declare access."""

    service = ServiceConfig(
        label="Room Environment",
        driver={"type": "labpulse.sht40", "options": {"bus": 3}},
        measurements={
            "temperature": {"setups": ["room"], "unit": "°C"},
            "humidity": {"setups": ["room"], "unit": "%"},
        },
    )
    definition = get_driver_definition(service.driver.type)
    driver = definition.create_driver("room_environment", service.driver.options)
    assert isinstance(driver, Sht40Driver)
    assert driver.bus_number == 3
    assert driver.address == 0x44

    definition = get_driver_definition("labpulse.sht40")
    assert definition.default_read_interval_seconds == 2.0
    assert definition.container_requirements(
        service.driver.options,
        False,
    ) == ContainerRequirements(
        devices=("/dev/i2c-3",)
    )
    assert_raises(
        ValidationError,
        lambda: Sht40Config(address=0x45),
    )


def test_fake_usb_mode_substitutes_the_room_sht40() -> None:
    """Keep the standard room service hardware-free in fake-USB mode."""

    source = """mqtt: {broker: mosquitto}
sms: {dry_run: true}
setups:
  room: {}
services:
  room_environment:
    label: Room Environment
    driver:
      type: labpulse.sht40
      options:
        bus: 1
        address: 0x44
    measurements:
      temperature: {setups: [room], unit: "°C"}
      humidity: {setups: [room], unit: "%"}
"""

    converted = LabPulseConfig.model_validate(
        yaml.safe_load(derive_fake_config(source))
    )
    room = converted.services["room_environment"]

    assert room.driver.type == "labpulse.serial_pipe"
    assert (
        getattr(room.driver.options, "port", None)
        == "/tmp/labpulse-fake-serial/room_environment"
    )


def test_close_is_idempotent() -> None:
    """Allow central cleanup to release the I2C bus repeatedly."""

    bus, _ = install_fake_bus()
    driver = make_driver()
    driver.connect()

    driver.close()
    driver.close()

    assert bus.closed is True
