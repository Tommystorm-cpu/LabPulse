"""Load and validate LabPulse service configuration."""

import logging
import re
import sys
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from labpulse_common.identity import slug, title

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yaml"
logger = logging.getLogger("Config")

# ==========================================
# PYDANTIC SCHEMAS
# ==========================================

class MqttConfig(BaseModel):
    """MQTT broker connection settings used by LabPulse publishers."""

    broker: str
    port: int = Field(default=1883, ge=1, le=65535)

class SmsConfig(BaseModel):
    """SMS delivery settings used by the LabPulse SMS service."""

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


class SetupConfig(BaseModel):
    """Presentation metadata for one logical experimental setup."""

    model_config = ConfigDict(extra="forbid")

    label: str | None = None
    icon: str = "mdi:flask-outline"
    order: int = Field(default=100, ge=0, le=10000)

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

class MeasurementConfig(BaseModel):
    """One named value published by a LabPulse service."""

    model_config = ConfigDict(extra="forbid")

    name: str
    label: str | None = None
    subcategory: str | None = None
    setups: SetupScope | None = None
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = "measurement"

    @field_validator("setups", mode="before")
    @classmethod
    def normalize_setups(cls, value: object) -> SetupScope | None:
        """Normalize an explicit non-empty setup-ID list."""

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

    @property
    def display_label(self) -> str:
        """Return the configured label or the shared readable-name fallback."""

        return self.label or title(self.name)

class PowerDetectionConfig(BaseModel):
    """Direct Geekworm X1200 external-power detection settings."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["x1200_gpio"] = "x1200_gpio"
    gpio_chip: str = "/dev/gpiochip0"
    gpio_line: int = Field(default=6, ge=0, le=53)
    mains_present_active_high: bool = True
    outage_confirm_seconds: int = Field(default=3, ge=1, le=3600)
    restore_confirm_seconds: int = Field(default=5, ge=1, le=3600)

    @field_validator("gpio_chip")
    @classmethod
    def validate_gpio_chip(cls, gpio_chip: str) -> str:
        """Require an explicit gpiochip device path for safe container mapping."""

        normalized = gpio_chip.strip()
        chip_number = normalized.removeprefix("/dev/gpiochip")
        if not chip_number.isdigit():
            raise ValueError("gpio_chip must be a /dev/gpiochip device path")
        return normalized

class ServiceConfig(BaseModel):
    """Configuration for one independently running LabPulse sensor service."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    driver: Literal["serial", "gpio", "i2c"]
    gpio_sensor: Literal["dht11"] | None = None
    gpio_pin: str | None = None
    i2c_sensor: Literal["x1200_ups"] | None = None
    i2c_bus: int | None = Field(default=None, ge=0, le=255)
    i2c_address: int | None = Field(default=None, ge=0x03, le=0x77)
    serial_port: str | None = None
    baud_rate: int = Field(default=9600, gt=0)
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

        if self.driver == "i2c":
            if self.i2c_sensor != "x1200_ups":
                raise ValueError("I2C services currently require i2c_sensor: x1200_ups")
            if self.i2c_bus is None:
                raise ValueError("X1200 services require i2c_bus")
            if self.i2c_address is None:
                raise ValueError("X1200 services require i2c_address")
            if self.i2c_address != 0x36:
                raise ValueError("X1200 services require i2c_address: 0x36")
            if self.power_detection is None:
                raise ValueError("X1200 services require power_detection")
        elif any(
            value is not None
            for value in (
                self.i2c_sensor,
                self.i2c_bus,
                self.i2c_address,
            )
        ):
            raise ValueError("X1200/I2C settings require driver: i2c")

        if self.power_detection is not None:
            required = {"voltage", "battery_level", "mains_present"}
            missing = sorted(required.difference(measurement_names))
            if missing:
                raise ValueError(
                    "power_detection requires measurements named: " + ", ".join(missing)
                )
            if self.driver not in {"i2c", "serial"}:
                raise ValueError(
                    "x1200_gpio power_detection requires the live X1200 driver "
                    "or the fake serial UPS driver"
                )
            if self.driver == "i2c" and self.read_interval_seconds not in (None, 1.0):
                raise ValueError(
                    "X1200 power monitoring requires read_interval_seconds: 1"
                )

            if any(measurement.setups is not None for measurement in self.measurements):
                raise ValueError(
                    "dedicated power measurements must omit setups because power is "
                    "not grouped as an experimental setup"
                )
        elif any(measurement.setups is None for measurement in self.measurements):
            raise ValueError(
                "every ordinary measurement must declare a non-empty setups list"
            )

        return self

class LabPulseConfig(BaseModel):
    """Validated top-level LabPulse configuration object."""

    mqtt: MqttConfig
    sms: SmsConfig = Field(default_factory=SmsConfig)
    service_health: ServiceHealthConfig = Field(default_factory=ServiceHealthConfig)
    setups: dict[str, SetupConfig]
    services: dict[str, ServiceConfig]

    @model_validator(mode="after")
    def validate_setup_membership(self) -> "LabPulseConfig":
        """Validate setup IDs and every measurement's logical references."""

        for setup_id in self.setups:
            validate_setup_id(setup_id)

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

def load_config(yaml_path: str | Path = DEFAULT_CONFIG_PATH) -> LabPulseConfig:
    """Reads YAML and validates it strictly against the Pydantic schema."""
    config_path = resolve_path(yaml_path)

    if not config_path.exists():
        logger.critical("Configuration file missing at %s", config_path)
        sys.exit(1)

    with config_path.open("r", encoding="utf-8") as file:
        try:
            yaml_data = yaml.safe_load(file)
        except yaml.YAMLError as e:
            logger.critical("Invalid YAML formatting in %s. Details: %s", config_path, e)
            sys.exit(1)

    try:
        # This line forces the dictionary through the validation engine
        validated_config = LabPulseConfig(**yaml_data)
        return validated_config
    except ValidationError as e:
        # Fail Fast: Print exact human-readable errors and kill the script
        logger.critical("CONFIGURATION VALIDATION FAILED")
        logger.critical("LabPulse cannot start because %s has errors:", config_path)
        for error in e.errors():
            location = " -> ".join([str(loc) for loc in error['loc']])
            logger.critical("[ %s ]: %s", location, error["msg"])
        sys.exit(1)

def get_service_config(config: LabPulseConfig, service_name: str) -> ServiceConfig:
    """Return one service config, exiting with a readable error if missing."""

    try:
        return config.services[service_name]
    except KeyError:
        available = ", ".join(sorted(config.services))
        logger.critical(
            "Unknown service '%s'. Available services: %s",
            service_name,
            available,
        )
        sys.exit(1)

