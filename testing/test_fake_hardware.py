"""Contracts for configuration-driven fake-hardware mode."""

import math
from pathlib import Path

from labpulse.common.config import load_config, render_resolved_config, validate_resolved_config
from labpulse.common.fake_config import derive_fake_config
from labpulse.hardware._simulation import SimulatedHardwareDriver, SimulatedOutputDriver
from labpulse.hardware.driver import ConnectionLost
from labpulse.homeassistant.alarm import build_template_context


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_fake_hardware_preserves_the_complete_dashboard_model() -> None:
    """Use the exact resolved services, measurements, outputs and metadata."""

    source = load_config(REPOSITORY_ROOT / "config.yaml")
    resolved_text = render_resolved_config(source)
    fake_text = derive_fake_config(resolved_text)
    fake = validate_resolved_config(fake_text, Path("config.fake.yaml"))

    assert fake_text == resolved_text
    assert fake.config == validate_resolved_config(
        resolved_text, Path("config.resolved.yaml")
    ).config
    assert build_template_context(fake.config) == build_template_context(source.config)


def test_simulated_driver_publishes_every_configured_measurement() -> None:
    """Generate finite, changing values without depending on driver type."""

    services = load_config(REPOSITORY_ROOT / "config.yaml").config.services
    for service_name, service in services.items():
        if not service.enabled:
            continue
        driver = SimulatedHardwareDriver(service_name, service.measurements)
        driver.connect()
        first = driver.read().values
        second = driver.read().values

        assert set(first) == set(service.measurements)
        assert set(second) == set(service.measurements)
        assert all(math.isfinite(value) for value in first.values())
        varying_values = [name for name in first if first[name] not in {0.0, 1.0}]
        assert any(first[name] != second[name] for name in varying_values)

        driver.close()
        try:
            driver.read()
        except ConnectionLost:
            pass
        else:
            raise AssertionError("closed simulated hardware still returned readings")


def test_simulated_output_never_accesses_physical_hardware() -> None:
    """Retain commands in memory and return to the configured safe state."""

    driver = SimulatedOutputDriver("cooling_valve", safe_state=False)
    driver.connect()
    assert driver.read().values == {"state": 0.0}
    driver.set_state(True)
    assert driver.read().values == {"state": 1.0}
    driver.close()

    driver.connect()
    assert driver.read().values == {"state": 0.0}
