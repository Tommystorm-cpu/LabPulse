"""Discover driver modules and expose their self-contained definitions."""

from __future__ import annotations

import importlib
import pkgutil

from labpulse.hardware.driver import DriverDefinition


# Public modules are treated as drivers by default. The contributor template is
# documentation, not a runnable driver.
_NON_DRIVER_MODULES = {"driver_template"}
_DRIVER_PACKAGE = "labpulse.hardware.drivers"

# Discover at import time so malformed declarations fail during config startup,
# before Compose generation or physical hardware access.
DRIVER_REGISTRY: dict[str, DriverDefinition] = {}
_driver_package = importlib.import_module(_DRIVER_PACKAGE)
_driver_modules = sorted(pkgutil.iter_modules(_driver_package.__path__), key=lambda item: item.name)

for _module_info in _driver_modules:
    # Underscored modules may contain shared driver helpers without defining a driver.
    if _module_info.name.startswith("_") or _module_info.name in _NON_DRIVER_MODULES:
        continue

    _module = importlib.import_module(f"{_DRIVER_PACKAGE}.{_module_info.name}")
    _definition = getattr(_module, "DRIVER_DEFINITION", None)
    if not isinstance(_definition, DriverDefinition):
        raise RuntimeError(f"Driver module {_module.__name__} must export DRIVER_DEFINITION")
    if _definition.driver_id in DRIVER_REGISTRY:
        raise RuntimeError(f"Duplicate LabPulse driver ID: {_definition.driver_id}")
    DRIVER_REGISTRY[_definition.driver_id] = _definition


def get_driver_definition(driver_id: str) -> DriverDefinition:
    """Return the requested driver definition or list the available IDs."""

    try:
        return DRIVER_REGISTRY[driver_id]
    except KeyError as error:
        available = ", ".join(sorted(DRIVER_REGISTRY))
        raise ValueError(f"Unknown driver type '{driver_id}'. Available drivers: {available}") from error
