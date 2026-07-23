"""Discover driver modules and expose their self-contained definitions."""

from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType
from typing import TYPE_CHECKING

from labpulse.hardware.api import BaseSensorDriver, DriverDefinition

if TYPE_CHECKING:
    from labpulse.common.config import ServiceConfig


_NON_DRIVER_MODULES = {"driver_template"}


def _driver_modules() -> list[ModuleType]:
    """Import public modules in this package that are expected to be drivers."""

    package_name = "labpulse.hardware.drivers"
    package = importlib.import_module(package_name)
    modules: list[ModuleType] = []
    for module_info in sorted(
        pkgutil.iter_modules(package.__path__),
        key=lambda item: item.name,
    ):
        if module_info.name.startswith("_") or module_info.name in _NON_DRIVER_MODULES:
            continue
        modules.append(importlib.import_module(f"{package_name}.{module_info.name}"))
    return modules


def _discover_drivers() -> dict[str, DriverDefinition]:
    """Build the registry and reject incomplete or duplicate driver modules."""

    registry: dict[str, DriverDefinition] = {}
    for module in _driver_modules():
        definition = getattr(module, "DRIVER", None)
        if not isinstance(definition, DriverDefinition):
            raise RuntimeError(
                f"Driver module {module.__name__} must export DRIVER "
                "as a DriverDefinition"
            )
        if definition.driver_id in registry:
            raise RuntimeError(f"Duplicate LabPulse driver ID: {definition.driver_id}")
        registry[definition.driver_id] = definition
    return registry


DRIVER_REGISTRY = _discover_drivers()


def get_driver_spec(driver_id: str) -> DriverDefinition:
    """Return one registered driver or raise a readable configuration error."""

    try:
        return DRIVER_REGISTRY[driver_id]
    except KeyError as error:
        available = ", ".join(sorted(DRIVER_REGISTRY))
        raise ValueError(
            f"Unknown driver type '{driver_id}'. Available drivers: {available}"
        ) from error


def build_driver(
    service_name: str,
    service_config: ServiceConfig,
) -> BaseSensorDriver:
    """Build the configured hardware driver for one service."""

    definition = get_driver_spec(service_config.driver.type)
    options = definition.validate_options(service_config.driver.options)
    return definition.create(service_name, options)
