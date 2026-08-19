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


# These are runner-owned service states. Drivers may add a component-specific
# status through ComponentIssue, but they never manage service transitions.
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


# Expected hardware failures form the language between drivers and the runner.
# Their distinctions decide whether a handle is retained, closed, or retried.
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


# Every implementation exposes only the hardware lifecycle. Scheduling, MQTT,
# status, and retry policy deliberately remain outside this class hierarchy.
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


ResourceResolver = Callable[[BaseModel, bool], ContainerRequirements]
ResourceDeclaration = ContainerRequirements | ResourceResolver


# DriverSpec is the only metadata layer: the registry discovers it, config uses
# it to validate options, deployment asks it for resources, and the CLI creates
# the implementation. A second registry/adapter abstraction is unnecessary.
@dataclass(frozen=True)
class DriverSpec:
    """Describe how one driver is configured, constructed, and deployed.

    The spec is the small translation layer between self-contained driver
    modules and the generic registry, Compose generator, and hardware runner.
    Drivers with fixed container access can declare ``ContainerRequirements``
    directly; only option-dependent access needs a resolver function.
    """

    driver_id: str
    options_model: type[BaseModel]
    implementation: type[BaseSensorDriver]
    resources: ResourceDeclaration
    default_read_interval_seconds: float

    def __post_init__(self) -> None:
        """Reject malformed specs as soon as their module is discovered."""

        if not self.driver_id or self.driver_id != self.driver_id.strip():
            raise ValueError("driver_id must be a non-blank normalized string")
        if not issubclass(self.options_model, BaseModel):
            raise TypeError("options_model must extend pydantic.BaseModel")
        if not issubclass(self.implementation, BaseSensorDriver):
            raise TypeError("implementation must extend BaseSensorDriver")
        if not isinstance(self.resources, ContainerRequirements) and not callable(
            self.resources
        ):
            raise TypeError(
                "resources must be ContainerRequirements or a resolver function"
            )
        if self.default_read_interval_seconds < 0:
            raise ValueError("default_read_interval_seconds must not be negative")

    def validate_options(self, options: Mapping[str, Any] | BaseModel) -> BaseModel:
        """Return the driver's typed and normalized configuration."""

        # Config loading normally reaches this fast path. Accepting a mapping as
        # well keeps DriverSpec useful in tests and direct deployment tooling.
        if isinstance(options, self.options_model):
            return options
        if isinstance(options, BaseModel):
            raise TypeError(
                f"{self.driver_id} expected {self.options_model.__name__}, "
                f"got {type(options).__name__}"
            )
        return self.options_model.model_validate(dict(options))

    def create(
        self,
        service_name: str,
        options: Mapping[str, Any] | BaseModel,
    ) -> BaseSensorDriver:
        """Construct the implementation from one validated options object."""

        validated = self.validate_options(options)
        return self.implementation(service_name, validated)

    def resolve_resources(
        self,
        options: Mapping[str, Any] | BaseModel,
        force_simulated: bool,
    ) -> ContainerRequirements:
        """Return the fixed or option-dependent container access declaration."""

        validated = self.validate_options(options)
        # Most simple GPIO drivers have fixed access and need no resolver
        # function. Dynamic drivers receive the same validated options model.
        if isinstance(self.resources, ContainerRequirements):
            return self.resources

        requirements = self.resources(validated, force_simulated)
        if not isinstance(requirements, ContainerRequirements):
            raise TypeError(
                f"{self.driver_id} resources must return ContainerRequirements"
            )
        return requirements
