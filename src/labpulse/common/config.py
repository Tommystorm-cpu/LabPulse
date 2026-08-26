"""Load and validate the single authoritative LabPulse configuration model."""

from collections.abc import Mapping
from dataclasses import dataclass
import keyword
import math
import re
from pathlib import Path
import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializeAsAny,
    ValidationError,
    field_validator,
    model_validator,
)

from labpulse.common.formula import compile_formula
from labpulse.common.identity import slug, title

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
    kind: str


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
    config: "LabPulseConfig"

    def service(self, service_name: str) -> "ServiceConfig":
        """Return one configured service or raise a source-aware selection error."""

        try:
            return self.config.services[service_name]
        except KeyError as error:
            available = ", ".join(sorted(self.config.services))
            raise ConfigError(
                self.path,
                (
                    ConfigProblem(
                        location=("services", service_name),
                        message=(
                            f"unknown service; available services: {available}"
                        ),
                        kind="service_not_found",
                    ),
                ),
            ) from error


def format_config_error(error: "ConfigError") -> str:
    """Render a consistent multi-line configuration failure for CLI consumers."""

    lines = [f"Configuration validation failed for {error.path}:"]
    for problem in error.problems:
        location = " -> ".join(str(item) for item in problem.location) or "root"
        lines.append(f"[ {location} ]: {problem.message}")
    return "\n".join(lines)

# ==========================================
# PYDANTIC SCHEMAS
# ==========================================

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
                raise ValueError(
                    "SMS recipients must use international format, for example +447700900000"
                )
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


class SetupScope(BaseModel):
    """Normalized explicit logical-setup membership for one physical measurement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    setup_ids: tuple[str, ...]

    @model_validator(mode="after")
    def validate_shape(self) -> "SetupScope":
        """Require every ordinary measurement to name at least one setup."""

        if not self.setup_ids:
            raise ValueError("setup membership must not be empty")
        return self


def validate_setup_id(setup_id: str) -> str:
    """Return one valid stable setup identifier."""

    normalized = setup_id.strip()
    if not normalized or slug(normalized) != normalized:
        raise ValueError(
            "setup IDs must use lowercase letters, numbers, and underscores"
        )
    return normalized


def validate_dashboard_id(dashboard_id: str) -> str:
    """Return one valid stable custom-dashboard identifier."""

    normalized = dashboard_id.strip()
    if not normalized or slug(normalized) != normalized:
        raise ValueError(
            "dashboard IDs must use lowercase letters, numbers, and underscores"
        )
    return normalized


def normalize_setup_scope(value: object) -> SetupScope | None:
    """Normalize an optional, explicit non-empty setup-ID list."""

    if value is None:
        return None
    if isinstance(value, SetupScope):
        return value
    if isinstance(value, list):
        if not value:
            raise ValueError("setups must contain at least one setup ID")
        normalized_ids: list[str] = []
        for setup_id in value:
            if not isinstance(setup_id, str):
                raise ValueError("selected setup IDs must be strings")
            normalized_ids.append(validate_setup_id(setup_id))
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("selected setup IDs must be unique")
        return SetupScope(setup_ids=tuple(normalized_ids))
    raise ValueError("setups must be a non-empty list of setup IDs")


def validate_measurement_icon(icon: str | None) -> str | None:
    """Normalize an optional Material Design entity icon."""

    if icon is None:
        return None
    normalized = icon.strip()
    if re.fullmatch(r"mdi:[a-z0-9]+(?:-[a-z0-9]+)*", normalized) is None:
        raise ValueError("measurement icon must use an mdi: icon identifier")
    return normalized

class MeasurementConfig(BaseModel):
    """One named value published by a LabPulse service."""

    model_config = ConfigDict(extra="forbid")

    name: str
    label: str | None = None
    short_label: str | None = None
    subcategory: str | None = None
    setups: SetupScope | None = None
    alarmed: bool = Field(default=True, strict=True)
    unit: str | None = None
    device_class: str | None = None
    icon: str | None = None
    state_class: str | None = "measurement"

    @field_validator("setups", mode="before")
    @classmethod
    def normalize_setups(cls, value: object) -> SetupScope | None:
        """Normalize an explicit non-empty setup-ID list."""

        return normalize_setup_scope(value)

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, icon: str | None) -> str | None:
        """Normalize an optional Material Design entity icon."""

        return validate_measurement_icon(icon)

    @property
    def display_label(self) -> str:
        """Return the full label used outside compact dashboard rows."""

        return self.label or title(self.name)

    @property
    def display_short_label(self) -> str:
        """Return the shorter label used where surrounding context is sufficient."""

        return self.short_label or self.display_label


class CustomMeasurementConfig(BaseModel):
    """One Home Assistant-calculated reading built from physical measurements."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    short_label: str | None = None
    subcategory: str | None = None
    setups: SetupScope
    inputs: dict[str, str]
    constants: dict[str, float] = Field(default_factory=dict)
    formula: str
    precision: int = Field(default=2, ge=0, le=10)
    alarmed: bool = Field(default=True, strict=True)
    unit: str | None = None
    device_class: str | None = None
    icon: str | None = None
    state_class: str | None = "measurement"

    @field_validator("setups", mode="before")
    @classmethod
    def normalize_setups(cls, value: object) -> SetupScope:
        """Require custom readings to belong to at least one setup."""

        scope = normalize_setup_scope(value)
        if scope is None:
            raise ValueError("custom measurements must declare setups")
        return scope

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, icon: str | None) -> str | None:
        """Normalize an optional Material Design entity icon."""

        return validate_measurement_icon(icon)

    @field_validator("inputs")
    @classmethod
    def validate_inputs(cls, inputs: dict[str, str]) -> dict[str, str]:
        """Require at least one physical source with a safe local alias."""

        if not inputs:
            raise ValueError("custom measurements require at least one input")
        normalized: dict[str, str] = {}
        reserved = {"true", "false", "none", "null", "states", "is_number"}
        for alias, reference in inputs.items():
            clean_alias = alias.strip()
            if (
                not clean_alias
                or slug(clean_alias) != clean_alias
                or keyword.iskeyword(clean_alias)
                or clean_alias in reserved
            ):
                raise ValueError(
                    "input aliases must use non-reserved lowercase letters, numbers, and underscores"
                )
            clean_reference = reference.strip()
            if clean_reference.count(".") != 1:
                raise ValueError(
                    f"input {clean_alias} must reference service.measurement"
                )
            normalized[clean_alias] = clean_reference
        if len(set(normalized.values())) != len(normalized):
            raise ValueError("custom measurement inputs must reference distinct measurements")
        return normalized

    @field_validator("constants", mode="before")
    @classmethod
    def validate_constants(cls, constants: object) -> dict[str, float]:
        """Require finite numeric constants with the same safe naming rules."""

        if not isinstance(constants, Mapping):
            raise ValueError("custom measurement constants must be a mapping")
        normalized: dict[str, float] = {}
        reserved = {"true", "false", "none", "null", "states", "is_number"}
        for name, raw_value in constants.items():
            if not isinstance(name, str):
                raise ValueError("custom measurement constant names must be strings")
            clean_name = name.strip()
            if (
                not clean_name
                or slug(clean_name) != clean_name
                or keyword.iskeyword(clean_name)
                or clean_name in reserved
            ):
                raise ValueError(
                    "constant names must use non-reserved lowercase letters, numbers, and underscores"
                )
            if (
                isinstance(raw_value, bool)
                or not isinstance(raw_value, (int, float))
                or not math.isfinite(raw_value)
            ):
                raise ValueError("custom measurement constants must be finite numbers")
            normalized[clean_name] = float(raw_value)
        return normalized

    @model_validator(mode="after")
    def validate_formula(self) -> "CustomMeasurementConfig":
        """Ensure the formula uses every declared input and no unknown names."""

        overlap = sorted(set(self.inputs).intersection(self.constants))
        if overlap:
            raise ValueError("inputs and constants use the same names: " + ", ".join(overlap))
        compiled = compile_formula(self.formula, set(self.inputs) | set(self.constants))
        unused_inputs = sorted(set(self.inputs).difference(compiled.names))
        if unused_inputs:
            raise ValueError("formula does not use inputs: " + ", ".join(unused_inputs))
        unused_constants = sorted(set(self.constants).difference(compiled.names))
        if unused_constants:
            raise ValueError("formula does not use constants: " + ", ".join(unused_constants))
        return self

    def display_label(self, custom_id: str) -> str:
        """Return the full label used outside compact dashboard rows."""

        return self.label or title(custom_id)

    def display_short_label(self, custom_id: str) -> str:
        """Return the compact dashboard label."""

        return self.short_label or self.display_label(custom_id)

class DriverConfig(BaseModel):
    """One stable driver identity and its typed, driver-owned options."""

    model_config = ConfigDict(extra="forbid")

    type: str
    options: SerializeAsAny[BaseModel]

    @model_validator(mode="before")
    @classmethod
    def validate_registered_driver(cls, value: object) -> object:
        """Resolve the driver and retain its concrete validated options model."""

        from labpulse.hardware.registry import get_driver_spec

        if not isinstance(value, Mapping):
            raise ValueError("driver must be a mapping")
        raw = dict(value)
        driver_value = raw.get("type")
        if not isinstance(driver_value, str):
            raise ValueError("driver type must be a string")
        driver_type = driver_value.strip()
        if not driver_type:
            raise ValueError("driver type must not be blank")
        spec = get_driver_spec(driver_type)
        options = raw.get("options", {})
        if not isinstance(options, (Mapping, BaseModel)):
            raise ValueError("driver options must be a mapping")
        raw["type"] = driver_type
        raw["options"] = spec.validate_options(options)
        return raw


class PowerDetectionConfig(BaseModel):
    """Home Assistant timing for direct external-power detection."""

    model_config = ConfigDict(extra="forbid")

    outage_confirm_seconds: int = Field(default=3, ge=1, le=3600)
    restore_confirm_seconds: int = Field(default=5, ge=1, le=3600)

class ServiceConfig(BaseModel):
    """Configuration for one independently running LabPulse sensor service."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    driver: DriverConfig
    device_name: str
    measurements: list[MeasurementConfig]
    reconnect_interval_seconds: float = Field(default=5.0, gt=0)
    read_interval_seconds: float | None = Field(default=None, gt=0)
    maximum_measurement_age_seconds: int = Field(default=300, ge=2, le=86400)
    power_detection: PowerDetectionConfig | None = None

    @model_validator(mode="after")
    def validate_hardware_contract(self) -> "ServiceConfig":
        """Validate driver-specific fields and the normalized UPS measurements."""

        measurement_names = [measurement.name for measurement in self.measurements]
        if len(set(measurement_names)) != len(measurement_names):
            raise ValueError("measurements[].name values must be unique within a service")

        serial_pipe_driver_id = "labpulse.serial_pipe"
        x1200_driver_id = "labpulse.x1200"

        if (
            self.driver.type == x1200_driver_id
            and self.power_detection is None
        ):
            raise ValueError("labpulse.x1200 services require power_detection")

        if self.power_detection is not None:
            required = {"voltage", "battery_level", "mains_present"}
            missing = sorted(required.difference(measurement_names))
            if missing:
                raise ValueError(
                    "power_detection requires measurements named: " + ", ".join(missing)
                )
            if self.driver.type not in {
                x1200_driver_id,
                serial_pipe_driver_id,
            }:
                raise ValueError(
                    "power_detection requires the live X1200 driver "
                    "or the fake serial UPS driver"
                )
            if (
                self.driver.type == x1200_driver_id
                and self.read_interval_seconds not in (None, 1.0)
            ):
                raise ValueError(
                    "X1200 power monitoring requires read_interval_seconds: 1"
                )

            if any(measurement.setups is not None for measurement in self.measurements):
                raise ValueError(
                    "dedicated power measurements must omit setups because power is "
                    "not grouped as an experimental setup"
                )
            alarmed_values = {measurement.alarmed for measurement in self.measurements}
            if len(alarmed_values) > 1:
                raise ValueError(
                    "dedicated power measurements must all use the same alarmed value "
                    "because they form one composite power alarm"
                )
        elif any(measurement.setups is None for measurement in self.measurements):
            raise ValueError(
                "every ordinary measurement must declare a non-empty setups list"
            )

        return self

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
    def validate_setup_membership(self) -> "LabPulseConfig":
        """Validate dashboard/setup IDs and every logical reference."""

        for dashboard_id in self.dashboards:
            validate_dashboard_id(dashboard_id)
            if dashboard_id == "main":
                raise ValueError(
                    "dashboard ID 'main' is reserved for the built-in Monitor tab"
                )

        for setup_id, setup in self.setups.items():
            validate_setup_id(setup_id)
            if setup.dashboard != "main" and setup.dashboard not in self.dashboards:
                raise ValueError(
                    f"setup {setup_id} references unknown dashboard: {setup.dashboard}"
                )

        available = set(self.setups)
        for service_name, service in self.services.items():
            for measurement in service.measurements:
                scope = measurement.setups
                if scope is None:
                    continue
                missing = sorted(set(scope.setup_ids).difference(available))
                if missing:
                    raise ValueError(
                        f"{service_name}.{measurement.name} references unknown setups: "
                        + ", ".join(missing)
                    )

        if self.custom_measurements and "custom" in self.services:
            raise ValueError(
                "service ID 'custom' is reserved when custom measurements are configured"
            )
        for custom_id, measurement in self.custom_measurements.items():
            if not custom_id or slug(custom_id) != custom_id:
                raise ValueError(
                    "custom measurement IDs must use lowercase letters, numbers, and underscores"
                )
            virtual_service_id = f"custom_{custom_id}"
            if virtual_service_id in self.services:
                raise ValueError(
                    f"service ID '{virtual_service_id}' conflicts with custom "
                    f"measurement {custom_id} alarm identities"
                )
            missing = sorted(set(measurement.setups.setup_ids).difference(available))
            if missing:
                raise ValueError(
                    f"custom measurement {custom_id} references unknown setups: "
                    + ", ".join(missing)
                )
            for alias, reference in measurement.inputs.items():
                service_name, measurement_name = reference.split(".", 1)
                source_service = self.services.get(service_name)
                if source_service is None:
                    raise ValueError(
                        f"custom measurement {custom_id} input {alias} references "
                        f"unknown physical service: {service_name}"
                    )
                if measurement_name not in {
                    item.name for item in source_service.measurements
                }:
                    raise ValueError(
                        f"custom measurement {custom_id} input {alias} references "
                        f"unknown physical measurement: {reference}"
                    )
        return self

# ==========================================
# CONFIGURATION LOADERS
# ==========================================

def resolve_path(path: str | Path) -> Path:
    """Expand user markers and return an absolute path."""

    return Path(path).expanduser().resolve()

def resolve_config_relative_path(config_path: str | Path, value: str | Path) -> Path:
    """Resolve a path relative to the directory containing a config file."""

    candidate = Path(value).expanduser()

    if candidate.is_absolute():
        return candidate

    return (resolve_path(config_path).parent / candidate).resolve()


def _single_problem(path: Path, message: str, kind: str) -> ConfigError:
    """Build a root-level configuration error for read and YAML failures."""

    return ConfigError(
        path,
        (ConfigProblem(location=(), message=message, kind=kind),),
    )


def _validate_config(data: object, source: Path) -> ConfigDocument:
    """Validate decoded YAML data into one source-aware configuration document."""

    if not isinstance(data, Mapping):
        if data is None:
            message = "configuration is empty; expected a top-level mapping"
        else:
            message = (
                "configuration root must be a mapping, "
                f"not {type(data).__name__}"
            )
        raise _single_problem(source, message, "invalid_root")

    try:
        config = LabPulseConfig.model_validate(dict(data))
    except ValidationError as error:
        problems = tuple(
            ConfigProblem(
                location=tuple(item["loc"]),
                message=str(item["msg"]),
                kind=str(item["type"]),
            )
            for item in error.errors()
        )
        raise ConfigError(source, problems) from error
    return ConfigDocument(path=source, config=config)


def load_config(
    yaml_path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    text: str | None = None,
) -> ConfigDocument:
    """Read or decode and validate one LabPulse configuration without exiting."""

    config_path = resolve_path(yaml_path)
    if text is None:
        try:
            text = config_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise _single_problem(config_path, str(error), "read_error") from error
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise _single_problem(config_path, str(error), "yaml_error") from error
    return _validate_config(data, config_path)

