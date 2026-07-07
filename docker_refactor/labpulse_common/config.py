import json
import logging
import sys
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.yaml"
DEFAULT_THRESHOLDS_PATH = BASE_DIR / "thresholds.json"
logger = logging.getLogger("Config")

# ==========================================
# PYDANTIC SCHEMAS 
# ==========================================

class MqttConfig(BaseModel):
    broker: str
    port: int = Field(default=1883, ge=1, le=65535)

class SmsConfig(BaseModel):
    recipients: list[str] = Field(default_factory=list)

class ServiceConfig(BaseModel):
    enabled: bool = True
    driver: Literal["serial", "gpio", "i2c"]
    parser: str | None = None
    serial_port: str | None = None
    baud_rate: int = Field(default=9600, gt=0)
    device_name: str
    metric_prefix: str

class LabPulseConfig(BaseModel):
    """The Master Configuration Object"""
    mqtt: MqttConfig
    sms: SmsConfig = Field(default_factory=SmsConfig)
    services: dict[str, ServiceConfig]

# ==========================================
# CONFIGURATION LOADERS
# ==========================================

def resolve_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()

def resolve_config_relative_path(config_path: str | Path, value: str | Path) -> Path:
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

def load_all_thresholds(thresholds_path: str | Path = DEFAULT_THRESHOLDS_PATH) -> dict:
    """Reads the dynamic, user-adjustable thresholds from JSON."""
    path = resolve_path(thresholds_path)

    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)

def save_all_thresholds(thresholds_dict: dict, thresholds_path: str | Path = DEFAULT_THRESHOLDS_PATH) -> None:
    """Saves dynamic user adjustments back to JSON."""
    path = resolve_path(thresholds_path)

    with path.open("w", encoding="utf-8") as file:
        json.dump(thresholds_dict, file, indent=4)
