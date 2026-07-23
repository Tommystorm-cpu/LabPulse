"""Public lifecycle contract shared by every LabPulse hardware driver.

Drivers translate hardware-specific behavior into this deliberately small API.
They open hardware in ``connect()``, return normalized values from ``read()``,
and release resources idempotently in ``close()``. Retry timing, service
freshness, MQTT publication, and status transitions belong to HardwareRunner.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
import logging
from typing import Any

from pydantic import BaseModel


class ServiceStatus(StrEnum):
    """Core service-health states owned by the hardware runner."""

    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    ONLINE = "online"
    ERROR = "error"


@dataclass(frozen=True)
class ComponentIssue:
    """One connected-device fault that does not invalidate every measurement."""

    code: str
    message: str


@dataclass(frozen=True)
class ReadingBatch:
    """One normalized set of numeric readings and optional component issues."""

    measurements: Mapping[str, float]
    issues: tuple[ComponentIssue, ...] = field(default_factory=tuple)


class DriverError(Exception):
    """Base class for expected hardware lifecycle failures."""


class DriverUnavailable(DriverError):
    """Raised when a driver cannot establish its hardware connection."""


class ConnectionLost(DriverError):
    """Raised when an established hardware connection is no longer usable."""


class TransientReadError(DriverError):
    """Raised when one sample fails but the connection remains usable."""


@dataclass(frozen=True)
class ContainerRequirements:
    """Structured host resources that Compose must expose to one driver."""

    devices: tuple[str, ...] = field(default_factory=tuple)
    mounts: tuple[str, ...] = field(default_factory=tuple)
    privileged: bool = False


DriverBuilder = Callable[[str, BaseModel], "BaseSensorDriver"]
ResourceResolver = Callable[[BaseModel, bool], ContainerRequirements]


@dataclass(frozen=True)
class DriverDefinition:
    """Everything LabPulse needs to validate, deploy, and run one driver."""

    driver_id: str
    options_model: type[BaseModel]
    build: DriverBuilder
    resources: ResourceResolver
    default_read_interval_seconds: float

    def __post_init__(self) -> None:
        """Reject malformed definitions as soon as their module is discovered."""

        if not self.driver_id or self.driver_id != self.driver_id.strip():
            raise ValueError("driver_id must be a non-blank normalized string")
        if self.default_read_interval_seconds < 0:
            raise ValueError("default_read_interval_seconds must not be negative")

    def validate_options(self, options: Mapping[str, Any]) -> BaseModel:
        """Return the driver's typed and normalized configuration."""

        return self.options_model.model_validate(dict(options))

    def resolve_resources(
        self,
        options: BaseModel,
        force_simulated: bool,
    ) -> ContainerRequirements:
        """Return the container access needed by validated options."""

        if not isinstance(options, self.options_model):
            raise TypeError(
                f"{self.driver_id} expected {self.options_model.__name__}, "
                f"got {type(options).__name__}"
            )
        requirements = self.resources(options, force_simulated)
        if not isinstance(requirements, ContainerRequirements):
            raise TypeError(
                f"{self.driver_id} resources must return ContainerRequirements"
            )
        return requirements

    def create(self, service_name: str, options: BaseModel) -> "BaseSensorDriver":
        """Build a driver and verify that it implements the lifecycle API."""

        driver = self.build(service_name, options)
        if not isinstance(driver, BaseSensorDriver):
            raise TypeError(
                f"{self.driver_id} build must return BaseSensorDriver, "
                f"got {type(driver).__name__}"
            )
        return driver


# NEW HARDWARE DRIVER:
# Do not put device protocols or vendor-library imports in this API module.
# Create ``drivers/<device_name>.py`` and add:
#
#   1. A small Pydantic options model for the device's ``driver.options``.
#   2. ``class Driver(BaseSensorDriver)`` implementing the three methods below.
#   3. ``build_driver(service_name, options)`` returning that Driver.
#   4. ``resources(options, force_simulated)`` declaring container access.
#   5. One module-level ``DRIVER = DriverDefinition(...)`` tying it together.
#
# ``connect()`` should translate setup failures to DriverUnavailable.
# ``read()`` should return ReadingBatch, return None when no sample is ready,
# raise TransientReadError for a bad sample on a usable connection, and raise
# ConnectionLost when the hardware handle must be recreated. ``close()`` must
# be safe to call repeatedly. The registry discovers the new module
# automatically; copy ``driver_template.py`` for a complete starting point.
class BaseSensorDriver(ABC):
    """Provide driver identity and logging while the runner owns lifecycle state."""

    def __init__(self, name: str) -> None:
        """Initialize the stable service identity used by driver logs."""

        self.name = name
        self.logger = logging.getLogger(f"Driver.{self.name}")

    @abstractmethod
    def connect(self) -> None:
        """Open or initialize the hardware, raising DriverUnavailable on failure."""

    @abstractmethod
    def read(self) -> ReadingBatch | None:
        """Return one normalized batch, or None when no complete sample is ready."""

    @abstractmethod
    def close(self) -> None:
        """Release hardware resources safely and idempotently."""
