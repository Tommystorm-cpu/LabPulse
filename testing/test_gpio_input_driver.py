"""Hardware-free tests for multi-line GPIO input services."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from labpulse.common.service_config import ServiceConfig
from labpulse.hardware.driver import ConnectionLost, ContainerRequirements, DriverUnavailable
from labpulse.hardware.drivers.gpio_input import GpioInputConfig, GpioInputDriver, container_requirements
from labpulse.hardware.registry import get_driver_definition


def make_service() -> ServiceConfig:
    """Build the representative two-line service."""

    return ServiceConfig.model_validate({
        "label": "GPIO Inputs",
        "driver": {"type": "labpulse.gpio_input", "options": {"gpio_chip": "/dev/gpiochip0"}},
        "measurement_defaults": {"setups": ["io_testing"], "state_class": None},
        "measurements": {
            "pin_17": {"label": "GPIO Pin 17", "gpio_line": 17},
            "pin_27": {"label": "GPIO Pin 27", "gpio_line": 27, "active_high": False},
        },
    })


def make_driver() -> GpioInputDriver:
    """Construct the service through the production registry."""

    service = make_service()
    driver = get_driver_definition(service.driver.type).create_driver("gpio_inputs", service.driver.options)
    assert isinstance(driver, GpioInputDriver)
    return driver


def fake_gpiod(request: Mock) -> object:
    """Build the subset of gpiod used by the driver."""

    return SimpleNamespace(
        LineSettings=lambda **kwargs: kwargs,
        line=SimpleNamespace(
            Direction=SimpleNamespace(INPUT="input"),
            Value=SimpleNamespace(ACTIVE="active", INACTIVE="inactive"),
        ),
        request_lines=Mock(return_value=request),
    )


def test_multi_line_read_mixed_polarity_and_cleanup() -> None:
    """Request once, publish named logical values, and release once."""

    request = Mock()
    request.get_value.side_effect = lambda line: {17: "active", 27: "inactive"}[line]
    module = fake_gpiod(request)
    driver = make_driver()
    with patch.dict(sys.modules, {"gpiod": module}):
        driver.connect()
    assert module.request_lines.call_count == 1
    assert set(module.request_lines.call_args.kwargs["config"]) == {17, 27}
    assert dict(driver.read().values) == {"pin_17": 1.0, "pin_27": 1.0}
    driver.close()
    driver.close()
    request.release.assert_called_once_with()


def test_defaults_and_validation() -> None:
    """Default polarity and reject bad, duplicate, misplaced, or legacy fields."""

    service = make_service()
    assert service.measurements["pin_17"].active_high is True
    raw = {
        "label": "GPIO", "driver": {"type": "labpulse.gpio_input", "options": {}},
        "measurements": {"one": {"setups": ["io_testing"]}},
    }
    with pytest.raises(ValidationError, match="requires gpio_line"):
        ServiceConfig.model_validate(raw)
    raw["measurements"] = {}
    with pytest.raises(ValidationError, match="at least one measurement"):
        ServiceConfig.model_validate(raw)
    raw["measurements"] = {
        "one": {"setups": ["io_testing"], "gpio_line": 17},
        "two": {"setups": ["io_testing"], "gpio_line": 17},
    }
    with pytest.raises(ValidationError, match="both use line 17"):
        ServiceConfig.model_validate(raw)
    for value in (-1, True):
        raw["measurements"] = {"one": {"setups": ["io_testing"], "gpio_line": value}}
        with pytest.raises(ValidationError):
            ServiceConfig.model_validate(raw)
    raw["driver"]["options"] = {"gpio_line": 17, "active_high": True}
    with pytest.raises(ValidationError):
        ServiceConfig.model_validate(raw)
    with pytest.raises(ValidationError, match="does not support GPIO measurement fields"):
        ServiceConfig.model_validate({
            "label": "Serial", "driver": {"type": "labpulse.serial_pipe", "options": {"port": "/tmp/x"}},
            "measurements": {"one": {"setups": ["io_testing"], "gpio_line": 17}},
        })


def test_failures_publish_nothing_and_reconnect() -> None:
    """Classify request/read failures and permit a fresh request after cleanup."""

    driver = make_driver()
    failed_module = fake_gpiod(Mock())
    failed_module.request_lines.side_effect = OSError("busy")
    with patch.dict(sys.modules, {"gpiod": failed_module}), pytest.raises(DriverUnavailable):
        driver.connect()

    first = Mock()
    first.get_value.side_effect = OSError("gone")
    module = fake_gpiod(first)
    with patch.dict(sys.modules, {"gpiod": module}):
        driver.connect()
    with pytest.raises(ConnectionLost):
        driver.read()
    driver.close()
    second = Mock()
    module.request_lines.return_value = second
    with patch.dict(sys.modules, {"gpiod": module}):
        driver.connect()
    assert module.request_lines.call_count == 2
    driver.close()


def test_gpio_container_access_uses_one_chip() -> None:
    """Mount the selected chip once for the multi-line service."""

    assert container_requirements(GpioInputConfig(gpio_chip="/dev/gpiochip2"), False) == ContainerRequirements(devices=("/dev/gpiochip2",))
