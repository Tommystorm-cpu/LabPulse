"""Hardware-free contracts for the persistent generic GPIO output driver."""

import sys
from types import SimpleNamespace
from unittest.mock import patch

from labpulse.hardware.driver import ConnectionLost, DriverUnavailable, HardwareOutputDriver
from labpulse.hardware.drivers.gpio_output import GpioOutputConfig, GpioOutputDriver


class FakeLineRequest:
    """Hold one simulated GPIO value until explicitly released."""

    def __init__(self, initial_value: str) -> None:
        """Store the output value applied with the line request."""

        self.value = initial_value
        self.values: list[str] = [initial_value]
        self.released = False
        self.fail_writes = False

    def set_value(self, _line: int, value: str) -> None:
        """Apply or reject one simulated electrical value."""

        if self.fail_writes:
            raise OSError("simulated GPIO write failure")
        self.value = value
        self.values.append(value)

    def get_value(self, _line: int) -> str:
        """Return the currently held simulated electrical value."""

        return self.value

    def release(self) -> None:
        """Record release of the simulated line request."""

        self.released = True


class FakeGpiod:
    """Implement the small libgpiod 2.x API surface used by the driver."""

    line = SimpleNamespace(
        Direction=SimpleNamespace(OUTPUT="output"),
        Value=SimpleNamespace(ACTIVE="active", INACTIVE="inactive"),
    )

    def __init__(self) -> None:
        """Initialize request and call tracking."""

        self.requests: list[dict[str, object]] = []
        self.request: FakeLineRequest | None = None

    def LineSettings(self, *, direction: str, output_value: str) -> object:
        """Return inspectable fake output settings."""

        return SimpleNamespace(direction=direction, output_value=output_value)

    def request_lines(
        self,
        chip: str,
        *,
        consumer: str,
        config: dict[int, object],
    ) -> FakeLineRequest:
        """Create one persistent fake request at its configured initial value."""

        settings = next(iter(config.values()))
        self.requests.append({"chip": chip, "consumer": consumer, "config": config})
        self.request = FakeLineRequest(settings.output_value)
        return self.request


def make_driver(*, active_high: bool = True, safe_state: bool = False) -> GpioOutputDriver:
    """Build one output driver through its public constructor."""

    return GpioOutputDriver(
        "cooling_valve_enable",
        GpioOutputConfig(
            gpio_chip="/dev/gpiochip0",
            gpio_line=18,
            active_high=active_high,
            safe_state=safe_state,
        ),
    )


def connect_with_fake_gpiod(driver: GpioOutputDriver) -> FakeGpiod:
    """Connect a driver to an in-memory implementation of libgpiod."""

    fake_gpiod = FakeGpiod()
    with patch.dict(sys.modules, {"gpiod": fake_gpiod}):
        driver.connect()
    return fake_gpiod


def test_output_holds_line_and_applies_safe_state_atomically() -> None:
    """Request one output line with its safe value before exposing the handle."""

    driver = make_driver()
    fake_gpiod = connect_with_fake_gpiod(driver)
    request = fake_gpiod.request
    if request is None:
        raise AssertionError("GPIO line was not requested")
    settings = next(iter(fake_gpiod.requests[0]["config"].values()))
    if settings.output_value != "inactive":
        raise AssertionError("safe output value was not part of the atomic request")
    if fake_gpiod.requests[0]["chip"] != "/dev/gpiochip0":
        raise AssertionError("wrong GPIO chip was requested")
    if not isinstance(driver, HardwareOutputDriver):
        raise AssertionError("GPIO output does not implement the output-driver contract")
    if dict(driver.read().values) != {"state": 0.0}:
        raise AssertionError("initial logical state is not safe")


def test_output_changes_state_and_inverts_active_low_hardware() -> None:
    """Set and verify logical states independently of electrical polarity."""

    active_high = make_driver()
    high_gpiod = connect_with_fake_gpiod(active_high)
    active_high.set_state(True)
    if high_gpiod.request is None or high_gpiod.request.value != "active":
        raise AssertionError("active-high output did not drive electrically active")
    if dict(active_high.read().values) != {"state": 1.0}:
        raise AssertionError("active-high readback is incorrect")

    active_low = make_driver(active_high=False)
    low_gpiod = connect_with_fake_gpiod(active_low)
    active_low.set_state(True)
    if low_gpiod.request is None or low_gpiod.request.value != "inactive":
        raise AssertionError("active-low output did not drive electrically inactive")
    if dict(active_low.read().values) != {"state": 1.0}:
        raise AssertionError("active-low readback is incorrect")


def test_close_forces_safe_then_releases_and_is_idempotent() -> None:
    """Apply the safe electrical value immediately before releasing the line."""

    driver = make_driver()
    fake_gpiod = connect_with_fake_gpiod(driver)
    driver.set_state(True)
    driver.close()
    driver.close()
    request = fake_gpiod.request
    if request is None or request.values[-1] != "inactive" or not request.released:
        raise AssertionError("shutdown did not apply safe state before release")
    try:
        driver.set_state(True)
    except ConnectionLost:
        pass
    else:
        raise AssertionError("write after release was accepted")


def test_output_dependency_and_write_faults_are_classified() -> None:
    """Classify missing bindings and runtime writes for worker retry handling."""

    driver = make_driver()
    with patch.dict(sys.modules, {"gpiod": None}):
        try:
            driver.connect()
        except DriverUnavailable:
            pass
        else:
            raise AssertionError("missing gpiod binding was accepted")

    fake_gpiod = connect_with_fake_gpiod(driver)
    if fake_gpiod.request is None:
        raise AssertionError("GPIO line was not requested")
    fake_gpiod.request.fail_writes = True
    try:
        driver.set_state(True)
    except ConnectionLost:
        pass
    else:
        raise AssertionError("failed GPIO write was not classified as connection loss")


def test_output_config_is_strict_and_requests_one_device() -> None:
    """Reject unsafe option shapes and grant only the configured GPIO chip."""

    from labpulse.hardware.drivers import gpio_output

    config = GpioOutputConfig(gpio_chip="/dev/gpiochip2", gpio_line=20)
    requirements = gpio_output.container_requirements(config, False)
    if requirements.devices != ("/dev/gpiochip2",) or requirements.privileged:
        raise AssertionError(f"unexpected output resources: {requirements!r}")
    for options in (
        {},
        {"gpio_line": 54},
        {"gpio_line": 18, "pull": "down"},
        {"gpio_line": "18"},
    ):
        try:
            GpioOutputConfig(**options)
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid output options were accepted: {options!r}")
