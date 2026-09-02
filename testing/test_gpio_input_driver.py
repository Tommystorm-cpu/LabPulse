"""Hardware-free contract tests for the generic GPIO input driver."""

from collections.abc import Callable
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

from labpulse.common.service_config import ServiceConfig
from labpulse.hardware.driver import ConnectionLost, ContainerRequirements, DriverUnavailable
from labpulse.hardware.drivers import _gpio, gpio_input
from labpulse.hardware.drivers._gpio import read_gpio
from labpulse.hardware.drivers.gpio_input import GpioInputConfig, GpioInputDriver


def command_result(
    stdout: str = "1\n",
    returncode: int = 0,
    stderr: str = "",
) -> object:
    """Build a subprocess-like result for GPIO reader tests."""

    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def sequence_runner(
    results: list[object],
    commands: list[list[str]],
) -> Callable[..., object]:
    """Return queued command results while recording each attempted command."""

    pending = list(results)

    def run(command: list[str], **_kwargs: object) -> object:
        """Record one command and return its queued fake result."""

        commands.append(command)
        return pending.pop(0)

    return run


def make_driver(active_high: bool = True) -> GpioInputDriver:
    """Build a generic input driver through its production constructor."""

    return GpioInputDriver(
        "equipment_running",
        GpioInputConfig(
            gpio_chip="/dev/gpiochip0",
            gpio_line=17,
            active_high=active_high,
        ),
    )


def connect_available_driver(driver: GpioInputDriver) -> None:
    """Connect while simulating the packaged tool and mapped GPIO device."""

    with (
        patch.object(gpio_input.shutil, "which", return_value="/usr/bin/gpioget"),
        patch.object(gpio_input.Path, "exists", return_value=True),
    ):
        driver.connect()


def test_gpio_values_and_polarity_are_numeric() -> None:
    """Publish active-high and active-low inputs as ordinary 0.0/1.0 readings."""

    active_high_driver = make_driver()
    connect_available_driver(active_high_driver)
    with patch.object(_gpio.subprocess, "run", return_value=command_result("1\n")):
        active_high = dict(active_high_driver.read().values)

    active_low_driver = make_driver(active_high=False)
    connect_available_driver(active_low_driver)
    with patch.object(_gpio.subprocess, "run", return_value=command_result("0\n")):
        active_low = dict(active_low_driver.read().values)

    if active_high != {"state": 1.0} or active_low != {"state": 1.0}:
        raise AssertionError(f"GPIO readings were not normalized: {active_high!r}, {active_low!r}")


def test_gpio_reader_supports_both_libgpiod_cli_versions() -> None:
    """Use the current gpioget form and fall back to the legacy form."""

    modern_commands: list[list[str]] = []
    with patch.object(
        _gpio.subprocess,
        "run",
        side_effect=sequence_runner([command_result('"17"=active\n')], modern_commands),
    ):
        modern = read_gpio("/dev/gpiochip0", 17, True)
    if modern != 1.0 or modern_commands != [["gpioget", "-c", "gpiochip0", "17"]]:
        raise AssertionError(f"libgpiod 2.x command is incorrect: {modern_commands!r}")

    legacy_commands: list[list[str]] = []
    with patch.object(
        _gpio.subprocess,
        "run",
        side_effect=sequence_runner(
            [command_result("", 1, "invalid option -- c"), command_result("0\n")],
            legacy_commands,
        ),
    ):
        legacy = read_gpio("/dev/gpiochip0", 17, True)
    if legacy != 0.0 or legacy_commands != [
        ["gpioget", "-c", "gpiochip0", "17"],
        ["gpioget", "gpiochip0", "17"],
    ]:
        raise AssertionError(f"libgpiod 1.x fallback is incorrect: {legacy_commands!r}")


def test_gpio_lifecycle_classifies_unavailability_and_read_failures() -> None:
    """Give the runner clear unavailable and connection-lost failure classes."""

    driver = make_driver()
    with patch.object(gpio_input.shutil, "which", return_value=None):
        try:
            driver.connect()
        except DriverUnavailable:
            pass
        else:
            raise AssertionError("missing gpioget was accepted")

    try:
        driver.read()
    except ConnectionLost:
        pass
    else:
        raise AssertionError("read before connect was accepted")

    connect_available_driver(driver)
    with patch.object(
        _gpio.subprocess,
        "run",
        side_effect=subprocess.TimeoutExpired("gpioget", 2),
    ):
        try:
            driver.read()
        except ConnectionLost:
            pass
        else:
            raise AssertionError("GPIO command timeout was not classified as connection loss")

    driver.close()
    driver.close()
    try:
        driver.read()
    except ConnectionLost:
        pass
    else:
        raise AssertionError("read after close was accepted")


def test_gpio_config_and_measurement_contract_are_strict() -> None:
    """Require one valid line and the fixed ordinary measurement key ``state``."""

    config = ServiceConfig(
        label="Equipment Running",
        driver={
            "type": "labpulse.gpio_input",
            "options": {"gpio_line": 17},
        },
        measurements={
            "state": {
                "label": "Equipment Running",
                "setups": ["test_setup"],
                "state_class": None,
            }
        },
    )
    if config.driver.options != GpioInputConfig(gpio_line=17):
        raise AssertionError("GPIO configuration defaults were not retained")

    invalid_services = (
        {"type": "labpulse.gpio_input", "options": {}},
        {"type": "labpulse.gpio_input", "options": {"gpio_line": 54}},
        {"type": "labpulse.gpio_input", "options": {"gpio_line": 17, "pull": "up"}},
    )
    for invalid_driver in invalid_services:
        try:
            ServiceConfig(
                label="Invalid GPIO",
                driver=invalid_driver,
                measurements={"state": {"setups": ["test_setup"]}},
            )
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid GPIO options were accepted: {invalid_driver!r}")

    try:
        ServiceConfig(
            label="Wrong output name",
            driver={"type": "labpulse.gpio_input", "options": {"gpio_line": 17}},
            measurements={"running": {"setups": ["test_setup"]}},
        )
    except ValueError as error:
        if "measurement named: state" not in str(error):
            raise
    else:
        raise AssertionError("GPIO service accepted an output name other than state")


def test_gpio_container_access_is_limited_to_selected_chip() -> None:
    """Request one GPIO device without privileged or broad /dev access."""

    requirements = gpio_input.container_requirements(
        GpioInputConfig(gpio_chip="/dev/gpiochip2", gpio_line=17),
        False,
    )
    expected = ContainerRequirements(devices=("/dev/gpiochip2",))
    if requirements != expected:
        raise AssertionError(f"unexpected GPIO container requirements: {requirements!r}")
