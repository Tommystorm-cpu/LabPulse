"""Load and validate LabPulse service configuration."""

import logging
import sys
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

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

    backend: Literal["log", "mmcli"] = "log"
    recipients: list[str] = Field(default_factory=list)

class ReadingConfig(BaseModel):
    """One named value published by a LabPulse service."""

    name: str
    label: str | None = None
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

class ServiceConfig(BaseModel):
    """Configuration for one independently running LabPulse sensor service."""

    enabled: bool = True
    driver: Literal["serial", "gpio", "i2c"]
    gpio_sensor: Literal["dht11"] | None = None
    gpio_pin: str | None = None
    parser: str | None = None
    serial_port: str | None = None
    baud_rate: int = Field(default=9600, gt=0)
    device_name: str
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    readings: list[ReadingConfig]
    reconnect_interval_seconds: float = Field(default=5.0, gt=0)
    read_interval_seconds: float | None = Field(default=None, gt=0)

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

def load_recipients(yaml_path: str | Path = DEFAULT_CONFIG_PATH) -> list[str]:
    """Pulls SMS numbers directly from the validated config object."""
    config = load_config(yaml_path)
    return config.sms.recipients
