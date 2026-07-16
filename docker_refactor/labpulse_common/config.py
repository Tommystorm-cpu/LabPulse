"""Load and validate LabPulse service configuration."""

import logging
import sys
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from labpulse_common.identity import title

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

class ReadingConfig(BaseModel):
    """One named value published by a LabPulse service."""

    name: str
    label: str | None = None
    group: str | None = None
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = "measurement"

    @property
    def display_label(self) -> str:
        """Return the configured label or the shared readable-name fallback."""

        return self.label or title(self.name)

class DisplayConfig(BaseModel):
    """Dashboard display hints for one LabPulse service."""

    section: str | None = None
    icon: str | None = None
    order: int = 100


class PowerDetectionConfig(BaseModel):
    """Voltage-transition power-inference settings for the installed UPS gauge."""

    source: Literal["ups_transition_inference"] = "ups_transition_inference"
    low_voltage_threshold: float = Field(default=4.05, ge=2.0, le=5.0)
    outage_drop_volts: float = Field(default=0.05, gt=0.0, le=1.0)
    recovery_rise_volts: float = Field(default=0.062, gt=0.0, le=1.0)
    transition_window_seconds: int = Field(default=5, ge=2, le=300)
    recovery_lockout_seconds: int = Field(default=17, ge=0, le=3600)
    recovery_charge_rise_percent: float | None = Field(default=None, gt=0.0, le=100.0)
    recovery_charge_window_seconds: int = Field(default=120, ge=10, le=86400)
    outage_confirm_seconds: int = Field(default=3, ge=1, le=3600)
    restore_confirm_seconds: int = Field(default=15, ge=1, le=3600)
    maximum_reading_age_seconds: int = Field(default=15, ge=2, le=86400)

class ServiceConfig(BaseModel):
    """Configuration for one independently running LabPulse sensor service."""

    enabled: bool = True
    driver: Literal["serial", "gpio", "i2c"]
    gpio_sensor: Literal["dht11"] | None = None
    gpio_pin: str | None = None
    i2c_sensor: Literal["max17043_ups"] | None = None
    i2c_bus: int | None = Field(default=None, ge=0, le=255)
    i2c_address: int | None = Field(default=None, ge=0x03, le=0x77)
    parser: str | None = None
    serial_port: str | None = None
    baud_rate: int = Field(default=9600, gt=0)
    device_name: str
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    readings: list[ReadingConfig]
    reconnect_interval_seconds: float = Field(default=5.0, gt=0)
    read_interval_seconds: float | None = Field(default=None, gt=0)
    maximum_reading_age_seconds: int = Field(default=300, ge=2, le=86400)
    power_detection: PowerDetectionConfig | None = None

    @model_validator(mode="after")
    def validate_hardware_contract(self) -> "ServiceConfig":
        """Validate driver-specific fields and the normalized UPS readings."""

        reading_names = [reading.name for reading in self.readings]
        if len(set(reading_names)) != len(reading_names):
            raise ValueError("readings[].name values must be unique within a service")

        if self.driver == "i2c":
            if self.i2c_sensor != "max17043_ups":
                raise ValueError("I2C services currently require i2c_sensor: max17043_ups")
            if self.i2c_bus is None:
                raise ValueError("MAX17043 services require i2c_bus")
            if self.i2c_address is None:
                raise ValueError("MAX17043 services require i2c_address")
            if self.i2c_address != 0x36:
                raise ValueError("MAX17043 services require i2c_address: 0x36")
        elif any(
            value is not None
            for value in (
                self.i2c_sensor,
                self.i2c_bus,
                self.i2c_address,
            )
        ):
            raise ValueError("MAX17043/I2C settings require driver: i2c")

        if self.power_detection is not None:
            required = {"voltage", "battery_level"}
            missing = sorted(required.difference(reading_names))
            if missing:
                raise ValueError(
                    "power_detection requires readings named: " + ", ".join(missing)
                )
            if self.driver == "i2c" and self.read_interval_seconds not in (None, 1.0):
                raise ValueError(
                    "MAX17043 power monitoring requires read_interval_seconds: 1"
                )

        return self

    @property
    def display_label(self) -> str:
        """Return the user-facing label for this hardware service."""

        return self.device_name

    @property
    def dashboard_section(self) -> str:
        """Return the normalized Home Assistant dashboard section label."""

        return self.display.section or self.display_label

    @property
    def dashboard_icon(self) -> str:
        """Return the normalized Home Assistant dashboard section icon."""

        return self.display.icon or "mdi:chip"

class LabPulseConfig(BaseModel):
    """Validated top-level LabPulse configuration object."""

    mqtt: MqttConfig
    sms: SmsConfig = Field(default_factory=SmsConfig)
    services: dict[str, ServiceConfig]

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

