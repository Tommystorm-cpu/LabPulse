"""Required lifecycle and shared data types for every LabPulse hardware driver.

Every driver opens hardware in ``connect()``, returns normalized values from
``read()``, and releases resources in ``close()``. Retry timing, freshness,
MQTT publication, and service status belong to the hardware runner.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import logging
from typing import Any

from pydantic import BaseModel


# Values returned by drivers
@dataclass(frozen=True)
class HardwareIssue:
    """One connected-device fault that does not invalidate every measurement."""

    code: str
    message: str


@dataclass(frozen=True)
class HardwareReadings:
    """Values returned by one hardware read, with any partial hardware faults."""

    values: Mapping[str, float]
    issues: tuple[HardwareIssue, ...] = ()


# Expected driver failures
# These tell the runner whether to retain, close, or reopen hardware.
class DriverError(Exception):
    """Base class for expected hardware lifecycle failures."""


class DriverUnavailable(DriverError):
    """Raised when a driver cannot establish its hardware connection."""


class ConnectionLost(DriverError):
    """Raised when an established hardware connection is no longer usable."""


class TransientReadError(DriverError):
    """Raised when one sample fails but the connection remains usable."""


# Required driver lifecycle
class HardwareDriver(ABC):
    """Required interface for one LabPulse hardware driver."""

    def __init__(self, service_name: str) -> None:
        """Store the service name used to identify this driver in logs."""

        self.service_name = service_name
        self.logger = logging.getLogger(f"Driver.{self.service_name}")

    @abstractmethod
    def connect(self) -> None:
        """Open or initialize the hardware, raising DriverUnavailable on failure."""

    @abstractmethod
    def read(self) -> HardwareReadings | None:
        """Return normalized readings, or None when no complete sample is ready."""

    @abstractmethod
    def close(self) -> None:
        """Release hardware resources safely and idempotently."""


class HardwareOutputDriver(HardwareDriver):
    """Hardware driver that can hold and change one logical output state."""

    @property
    @abstractmethod
    def safe_state(self) -> bool:
        """Return the logical state applied on startup and shutdown."""

    @abstractmethod
    def set_state(self, active: bool) -> None:
        """Apply one logical output state or raise a classified driver error."""


# Container requirements end up almost directly in the generated Docker
# Compose file, where they give each service container access to the hardware
# it needs.
@dataclass(frozen=True)
class ContainerRequirements:
    """Host access that Docker must give a hardware service container.

    A requirement is either a host device, a bind mount, or permission to run
    the container in privileged mode. The Compose generator adds this access
    only to services using the driver that requested it.
    """

    devices: tuple[str, ...] = ()
    mounts: tuple[str, ...] = ()
    privileged: bool = False


# This is the one declaration consumed by configuration, deployment, and the
# runner. Each driver module exports exactly one DRIVER_DEFINITION.
@dataclass(frozen=True)
class DriverDefinition:
    """Describe how one driver is configured, constructed, and deployed.

    The definition joins a self-contained driver module to the generic
    registry, Compose generator, and hardware runner. Every driver supplies one
    function that returns its required container access.
    """

    driver_id: str
    config_model: type[BaseModel]
    driver_class: type[HardwareDriver]
    container_requirements: Callable[[BaseModel, bool], ContainerRequirements]
    default_read_interval_seconds: float

    def __post_init__(self) -> None:
        """Reject malformed specs as soon as their module is discovered."""

        if not self.driver_id or self.driver_id != self.driver_id.strip():
            raise ValueError("driver_id must be a non-blank normalized string")
        if not issubclass(self.config_model, BaseModel):
            raise TypeError("config_model must extend pydantic.BaseModel")
        if not issubclass(self.driver_class, HardwareDriver):
            raise TypeError("driver_class must extend HardwareDriver")
        if not callable(self.container_requirements):
            raise TypeError("container_requirements must be a function")
        if self.default_read_interval_seconds < 0:
            raise ValueError("default_read_interval_seconds must not be negative")

    def validate_config(self, raw_config: Mapping[str, Any]) -> BaseModel:
        """Validate raw driver options during full configuration loading."""

        return self.config_model.model_validate(dict(raw_config))

    def create_driver(self, service_name: str, validated_config: BaseModel) -> HardwareDriver:
        """Construct this driver from configuration validated at load time."""

        return self.driver_class(service_name, validated_config)
