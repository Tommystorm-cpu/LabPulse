"""Load and validate the authoritative LabPulse configuration source bundle."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from ipaddress import AddressValueError, IPv4Address
from pathlib import Path, PureWindowsPath
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
import yaml

from labpulse.common.identity import slug, title
from labpulse.common.measurement_config import CustomMeasurementConfig, validate_setup_id
from labpulse.common.output_config import OutputConfig
from labpulse.common.service_config import ServiceConfig


# The models below are the trusted form used after raw YAML crosses the
# configuration boundary. Pydantic calls @field_validator for individual values
# and @model_validator after the fields have been assembled into one model.

class ExternalMqttListenerConfig(BaseModel):
    """Optional authenticated TLS listener for off-Pi measurement publishers."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=False, strict=True)
    bind_addresses: list[str] = Field(
        default_factory=lambda: ["0.0.0.0"],
        min_length=1,
    )
    port: int = Field(default=8883, ge=1, le=65535)

    @field_validator("bind_addresses")
    @classmethod
    def validate_bind_addresses(cls, values: list[str]) -> list[str]:
        """Require unique IPv4 interface addresses understood by Compose."""

        normalized: list[str] = []
        for value in values:
            try:
                normalized.append(str(IPv4Address(value)))
            except AddressValueError as error:
                raise ValueError(
                    "entries must be IPv4 addresses, for example 10.50.1.1"
                ) from error
        if len(normalized) != len(set(normalized)):
            raise ValueError("entries must be unique")
        if "0.0.0.0" in normalized and len(normalized) > 1:
            raise ValueError("0.0.0.0 cannot be combined with specific addresses")
        return normalized


class MqttConfig(BaseModel):
    """MQTT broker connection settings used by LabPulse publishers."""

    model_config = ConfigDict(extra="forbid")

    broker: str
    port: int = Field(default=1883, ge=1, le=65535)
    external_listener: ExternalMqttListenerConfig = Field(
        default_factory=ExternalMqttListenerConfig
    )


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

    offline_confirm_seconds: int = Field(default=10, ge=1, le=3600)
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
    outputs: dict[str, OutputConfig] = Field(default_factory=dict)
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

        for output_id, output in self.outputs.items():
            if not output_id or slug(output_id) != output_id:
                raise ValueError("output IDs must use lowercase letters, numbers, and underscores")
            missing = sorted(set(output.setups).difference(self.setups))
            if missing:
                raise ValueError(
                    f"output {output_id} references unknown setups: "
                    + ", ".join(missing)
                )

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

        # A GPIO character device can be shared by containers, but an
        # individual line can have only one owner. Catch exact configured line
        # collisions before Docker starts competing workers.
        gpio_owners: dict[tuple[str, int], str] = {}
        configured_workers = [
            (f"service {name}", service)
            for name, service in self.services.items()
            if service.enabled
        ]
        configured_workers.extend(
            (f"output {name}", output)
            for name, output in self.outputs.items()
            if output.enabled
        )
        for owner, worker in configured_workers:
            chip = getattr(worker.driver.options, "gpio_chip", None)
            line = getattr(worker.driver.options, "gpio_line", None)
            if not isinstance(chip, str) or not isinstance(line, int):
                continue
            key = (chip, line)
            previous = gpio_owners.get(key)
            if previous is not None:
                raise ValueError(
                    f"{owner} and {previous} both use {chip} line {line}"
                )
            gpio_owners[key] = owner
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
    source_path: Path | None = None


class ConfigError(Exception):
    """Report one or more failures while reading or validating configuration."""

    def __init__(self, path: Path, problems: tuple[ConfigProblem, ...]) -> None:
        """Store the normalized source path and immutable problem collection."""

        self.path = path
        self.problems = problems
        super().__init__(format_config_error(self))


@dataclass(frozen=True)
class ConfigDocument:
    """One resolved configuration together with its operator-owned sources."""

    path: Path
    config: LabPulseConfig
    resolved_data: dict[str, object]
    source_paths: tuple[Path, ...]
    measurement_sources: tuple[tuple[str, Path], ...] = ()


def format_config_error(error: ConfigError) -> str:
    """Render a consistent multi-line configuration failure for CLI consumers."""

    lines = [f"Configuration validation failed for {error.path}:"]
    for problem in error.problems:
        location = " -> ".join(str(item) for item in problem.location) or "root"
        source = f"{problem.source_path}: " if problem.source_path is not None else ""
        lines.append(f"{source}[ {location} ]: {problem.message}")
    return "\n".join(lines)


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that refuses silent replacement of duplicate keys."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    """Construct one mapping while reporting the second occurrence of a key."""

    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _decode_yaml(text: str, source_path: Path) -> object:
    """Decode one YAML source with duplicate-key and source-aware errors."""

    try:
        return yaml.load(text, Loader=_UniqueKeyLoader)
    except yaml.YAMLError as error:
        raise ConfigError(
            source_path,
            (ConfigProblem((), str(error)),),
        ) from error


def _measurement_fragment_path(master_path: Path, value: object) -> Path:
    """Validate and resolve one measurement fragment beneath config.d."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError("measurements_file must be a non-blank relative YAML path")
    raw = value.strip()
    relative = Path(raw)
    if (
        relative.is_absolute()
        or PureWindowsPath(raw).is_absolute()
        or raw.startswith(("/", "\\"))
    ):
        raise ValueError("measurements_file must be relative to config.yaml")
    if relative.suffix.lower() not in {".yaml", ".yml"}:
        raise ValueError("measurements_file must name a .yaml or .yml file")
    if not relative.parts or relative.parts[0] != "config.d" or ".." in relative.parts:
        raise ValueError("measurements_file must stay beneath config.d")

    candidate = master_path.parent.joinpath(*relative.parts)
    current = master_path.parent
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"measurements_file must not use symlinks: {relative.as_posix()}")
    resolved = candidate.resolve()
    fragment_root = (master_path.parent / "config.d").resolve()
    if not resolved.is_relative_to(fragment_root):
        raise ValueError("measurements_file must stay beneath config.d")
    if not candidate.exists():
        raise ValueError(f"measurements_file does not exist: {relative.as_posix()}")
    if not candidate.is_file():
        raise ValueError(f"measurements_file is not a regular file: {relative.as_posix()}")
    return resolved


def _resolve_measurement_files(
    data: Mapping[object, object],
    master_path: Path,
) -> tuple[dict[str, object], tuple[Path, ...], tuple[tuple[str, Path], ...]]:
    """Replace only per-service measurement-file references with their mappings."""

    resolved_data = deepcopy(dict(data))
    services = resolved_data.get("services")
    if not isinstance(services, Mapping):
        return resolved_data, (master_path,), ()

    source_paths: list[Path] = [master_path]
    measurement_sources: list[tuple[str, Path]] = []
    resolved_services = dict(services)
    resolved_data["services"] = resolved_services
    for service_name, raw_service in services.items():
        if not isinstance(service_name, str) or not isinstance(raw_service, Mapping):
            continue
        service = dict(raw_service)
        has_inline = "measurements" in service
        has_file = "measurements_file" in service
        if has_inline and has_file:
            raise ConfigError(
                master_path,
                (ConfigProblem(
                    ("services", service_name),
                    "define exactly one of measurements or measurements_file, not both",
                ),),
            )
        if not has_file:
            continue
        try:
            fragment_path = _measurement_fragment_path(master_path, service["measurements_file"])
            fragment_text = fragment_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError, ValueError) as error:
            raise ConfigError(
                master_path,
                (ConfigProblem(
                    ("services", service_name, "measurements_file"),
                    str(error),
                ),),
            ) from error
        fragment = _decode_yaml(fragment_text, fragment_path)
        if not isinstance(fragment, Mapping):
            kind = "empty" if fragment is None else type(fragment).__name__
            raise ConfigError(
                master_path,
                (ConfigProblem(
                    ("services", service_name, "measurements_file"),
                    f"measurement file root must be a non-empty mapping, not {kind}",
                    source_path=fragment_path,
                ),),
            )
        if not fragment:
            raise ConfigError(
                master_path,
                (ConfigProblem(
                    ("services", service_name, "measurements_file"),
                    "measurement file root must be a non-empty mapping",
                    source_path=fragment_path,
                ),),
            )
        service.pop("measurements_file")
        service["measurements"] = dict(fragment)
        resolved_services[service_name] = service
        if fragment_path not in source_paths:
            source_paths.append(fragment_path)
        measurement_sources.append((service_name, fragment_path))
    return resolved_data, tuple(source_paths), tuple(measurement_sources)


def render_resolved_config(document: ConfigDocument) -> str:
    """Render one standalone runtime document without source-file references."""

    return (
        "# GENERATED BY LABPULSE.\n"
        "# Changes to this file are overwritten by configuration regeneration.\n"
        "# Edit config.yaml and files beneath config.d instead.\n"
        + yaml.safe_dump(document.resolved_data, sort_keys=False, allow_unicode=True)
    )


def validate_resolved_config(text: str, output_path: str | Path) -> ConfigDocument:
    """Validate rendered runtime YAML independently of its source document."""

    document = load_config(output_path, text=text)
    if document.measurement_sources:
        raise ConfigError(
            document.path,
            (ConfigProblem((), "resolved configuration contains measurements_file"),),
        )
    return document


def load_config(yaml_path: str | Path = DEFAULT_CONFIG_PATH, *, text: str | None = None) -> ConfigDocument:
    """Read, resolve measurement fragments, and validate one source bundle."""

    config_path = Path(yaml_path).expanduser().resolve()
    if text is None:
        try:
            text = config_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ConfigError(config_path, (ConfigProblem((), str(error)),)) from error
    data = _decode_yaml(text, config_path)

    if not isinstance(data, Mapping):
        if data is None:
            message = "configuration is empty; expected a top-level mapping"
        else:
            message = f"configuration root must be a mapping, not {type(data).__name__}"
        raise ConfigError(config_path, (ConfigProblem((), message),))

    resolved_data, source_paths, measurement_sources = _resolve_measurement_files(
        data,
        config_path,
    )
    measurement_source_map = dict(measurement_sources)
    try:
        config = LabPulseConfig.model_validate(resolved_data)
    except ValidationError as error:
        problems = tuple(
            ConfigProblem(
                location=tuple(item["loc"]),
                message=str(item["msg"]),
                source_path=(
                    measurement_source_map.get(str(item["loc"][1]))
                    if len(item["loc"]) >= 2
                    and item["loc"][0] == "services"
                    and str(item["loc"][1]) in measurement_source_map
                    else None
                ),
            )
            for item in error.errors()
        )
        raise ConfigError(config_path, problems) from error
    return ConfigDocument(
        config_path,
        config,
        resolved_data,
        source_paths,
        measurement_sources,
    )
