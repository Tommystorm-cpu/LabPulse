"""Load and validate the single authoritative LabPulse configuration."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
import yaml

from labpulse.common.identity import slug, title
from labpulse.common.measurement_config import CustomMeasurementConfig, validate_setup_id
from labpulse.common.service_config import ServiceConfig


# The models below are the trusted form used after raw YAML crosses the
# configuration boundary. Pydantic calls @field_validator for individual values
# and @model_validator after the fields have been assembled into one model.

class MqttConfig(BaseModel):
    """MQTT broker connection settings used by LabPulse publishers."""

    model_config = ConfigDict(extra="forbid")

    broker: str
    port: int = Field(default=1883, ge=1, le=65535)


class SmsConfig(BaseModel):
    """SMS delivery settings used by the LabPulse SMS service."""

    model_config = ConfigDict(extra="forbid")

    dry_run: bool = Field(default=True, strict=True)
    recipients: list[str] = Field(default_factory=list)
    test_recipients: list[str] = Field(default_factory=list)

    @field_validator("recipients", "test_recipients")
    @classmethod
    def validate_recipients(cls, recipients: list[str]) -> list[str]:
        """Normalize recipients and reject empty, duplicate, or unsafe values."""

        normalized = [recipient.strip() for recipient in recipients]
        if any(not recipient for recipient in normalized):
            raise ValueError("SMS recipients cannot be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("SMS recipients must be unique")
        for recipient in normalized:
            if not recipient.startswith("+") or not recipient[1:].isdigit():
                raise ValueError("SMS recipients must use international format, for example +447700900000")
            if not 8 <= len(recipient[1:]) <= 15:
                raise ValueError("SMS recipients must contain 8 to 15 digits")
        return normalized

    @model_validator(mode="after")
    def require_real_recipients(self) -> "SmsConfig":
        """Require at least one recipient when real modem delivery is enabled."""

        if not self.dry_run and not self.recipients:
            raise ValueError("sms.recipients must not be empty when dry_run is false")
        return self


class ServiceHealthConfig(BaseModel):
    """Confirmation timing for whole-service hardware health alarms."""

    model_config = ConfigDict(extra="forbid")

    fault_confirm_seconds: int = Field(default=10, ge=1, le=3600)
    recovery_confirm_seconds: int = Field(default=15, ge=1, le=3600)


def validate_dashboard_id(dashboard_id: str) -> str:
    """Return one valid stable custom-dashboard identifier."""

    normalized = dashboard_id.strip()
    if not normalized or slug(normalized) != normalized:
        raise ValueError("dashboard IDs must use lowercase letters, numbers, and underscores")
    return normalized


class DashboardConfig(BaseModel):
    """Presentation metadata for one additional operator dashboard tab."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    icon: str = "mdi:view-dashboard-outline"
    order: int = Field(default=100, ge=0, le=10000)

    @field_validator("label")
    @classmethod
    def validate_label(cls, label: str | None) -> str | None:
        """Normalize an optional label and reject blank display text."""

        if label is None:
            return None
        normalized = label.strip()
        if not normalized:
            raise ValueError("dashboard label must not be blank")
        return normalized

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, icon: str) -> str:
        """Require a stable Material Design icon identifier."""

        normalized = icon.strip()
        if re.fullmatch(r"mdi:[a-z0-9]+(?:-[a-z0-9]+)*", normalized) is None:
            raise ValueError("dashboard icon must use an mdi: icon identifier")
        return normalized

    def display_label(self, dashboard_id: str) -> str:
        """Return the configured label or a readable dashboard-ID fallback."""

        return self.label or title(dashboard_id)


class SetupConfig(BaseModel):
    """Presentation metadata for one logical experimental setup."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    icon: str = "mdi:flask-outline"
    order: int = Field(default=100, ge=0, le=10000)
    dashboard: str = "main"

    @field_validator("label")
    @classmethod
    def validate_label(cls, label: str | None) -> str | None:
        """Normalize an optional label and reject blank display text."""

        if label is None:
            return None
        normalized = label.strip()
        if not normalized:
            raise ValueError("setup label must not be blank")
        return normalized

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, icon: str) -> str:
        """Require a stable Material Design icon identifier."""

        normalized = icon.strip()
        if re.fullmatch(r"mdi:[a-z0-9]+(?:-[a-z0-9]+)*", normalized) is None:
            raise ValueError("setup icon must use an mdi: icon identifier")
        return normalized

    @field_validator("dashboard")
    @classmethod
    def validate_dashboard(cls, dashboard: str) -> str:
        """Require the reserved main ID or a stable custom dashboard ID."""

        return validate_dashboard_id(dashboard)

    def display_label(self, setup_id: str) -> str:
        """Return the configured label or a readable setup-ID fallback."""

        return self.label or title(setup_id)


class LabPulseConfig(BaseModel):
    """Validated top-level LabPulse configuration object."""

    model_config = ConfigDict(extra="forbid")

    mqtt: MqttConfig
    sms: SmsConfig = Field(default_factory=SmsConfig)
    service_health: ServiceHealthConfig = Field(default_factory=ServiceHealthConfig)
    dashboards: dict[str, DashboardConfig] = Field(default_factory=dict)
    setups: dict[str, SetupConfig]
    services: dict[str, ServiceConfig]
    custom_measurements: dict[str, CustomMeasurementConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_cross_references(self) -> "LabPulseConfig":
        """Validate every reference connecting otherwise valid config sections."""

        # Dashboard and setup IDs become stable Home Assistant entity IDs, so
        # validate them before following any references between the two sections.
        for dashboard_id in self.dashboards:
            validate_dashboard_id(dashboard_id)
            if dashboard_id == "main":
                raise ValueError("dashboard ID 'main' is reserved for the built-in Monitor tab")

        for setup_id, setup in self.setups.items():
            validate_setup_id(setup_id)
            if setup.dashboard != "main" and setup.dashboard not in self.dashboards:
                raise ValueError(f"setup {setup_id} references unknown dashboard: {setup.dashboard}")

        # Physical measurements may be shared by several experimental setups.
        available_setup_ids = set(self.setups)
        for service_name, service in self.services.items():
            for measurement_name, measurement in service.measurements.items():
                if measurement.setups is None:
                    continue
                missing = sorted(set(measurement.setups).difference(available_setup_ids))
                if missing:
                    raise ValueError(
                        f"{service_name}.{measurement_name} references unknown setups: " + ", ".join(missing)
                    )

        # Custom measurements are represented as virtual services in Home
        # Assistant. Their IDs must not collide with physical service IDs.
        if self.custom_measurements and "custom" in self.services:
            raise ValueError("service ID 'custom' is reserved when custom measurements are configured")
        for custom_id, measurement in self.custom_measurements.items():
            if not custom_id or slug(custom_id) != custom_id:
                raise ValueError("custom measurement IDs must use lowercase letters, numbers, and underscores")
            virtual_service_id = f"custom_{custom_id}"
            if virtual_service_id in self.services:
                raise ValueError(
                    f"service ID '{virtual_service_id}' conflicts with custom measurement {custom_id} alarm identities"
                )
            missing = sorted(set(measurement.setups).difference(available_setup_ids))
            if missing:
                raise ValueError(
                    f"custom measurement {custom_id} references unknown setups: " + ", ".join(missing)
                )

            # Inputs can only point to physical readings. This deliberately
            # prevents chains of custom measurements that are hard to reason about.
            for alias, reference in measurement.inputs.items():
                service_name, measurement_name = reference.split(".", 1)
                source_service = self.services.get(service_name)
                if source_service is None:
                    raise ValueError(
                        f"custom measurement {custom_id} input {alias} references unknown physical service: {service_name}"
                    )
                if measurement_name not in source_service.measurements:
                    raise ValueError(
                        f"custom measurement {custom_id} input {alias} references unknown physical measurement: {reference}"
                    )
        return self


def find_default_config_path() -> Path:
    """Find the repository or deployed application config beside the code tree."""

    for parent in Path(__file__).resolve().parents:
        candidate = parent / "config.yaml"
        if candidate.is_file():
            return candidate
    return Path.cwd() / "config.yaml"


DEFAULT_CONFIG_PATH = find_default_config_path()


@dataclass(frozen=True)
class ConfigProblem:
    """One source-aware configuration problem suitable for any user interface."""

    location: tuple[str | int, ...]
    message: str


class ConfigError(Exception):
    """Report one or more failures while reading or validating configuration."""

    def __init__(self, path: Path, problems: tuple[ConfigProblem, ...]) -> None:
        """Store the normalized source path and immutable problem collection."""

        self.path = path
        self.problems = problems
        super().__init__(format_config_error(self))


@dataclass(frozen=True)
class ConfigDocument:
    """One validated configuration together with its authoritative source path."""

    path: Path
    config: LabPulseConfig


def format_config_error(error: ConfigError) -> str:
    """Render a consistent multi-line configuration failure for CLI consumers."""

    lines = [f"Configuration validation failed for {error.path}:"]
    for problem in error.problems:
        location = " -> ".join(str(item) for item in problem.location) or "root"
        lines.append(f"[ {location} ]: {problem.message}")
    return "\n".join(lines)


def load_config(yaml_path: str | Path = DEFAULT_CONFIG_PATH, *, text: str | None = None) -> ConfigDocument:
    """Read or decode and validate one LabPulse configuration without exiting."""

    config_path = Path(yaml_path).expanduser().resolve()
    if text is None:
        try:
            text = config_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ConfigError(config_path, (ConfigProblem((), str(error)),)) from error
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ConfigError(config_path, (ConfigProblem((), str(error)),)) from error

    if not isinstance(data, Mapping):
        if data is None:
            message = "configuration is empty; expected a top-level mapping"
        else:
            message = f"configuration root must be a mapping, not {type(data).__name__}"
        raise ConfigError(config_path, (ConfigProblem((), message),))

    try:
        config = LabPulseConfig.model_validate(dict(data))
    except ValidationError as error:
        problems = tuple(
            ConfigProblem(location=tuple(item["loc"]), message=str(item["msg"]))
            for item in error.errors()
        )
        raise ConfigError(config_path, problems) from error
    return ConfigDocument(config_path, config)
