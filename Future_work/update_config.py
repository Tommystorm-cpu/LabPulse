import os
import sys
import json
import yaml
from typing import Dict, Any, List
from pydantic import BaseModel, Field, ValidationError

# Resolve absolute paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
YAML_PATH = os.path.join(BASE_DIR, 'config.yaml')
JSON_THRESHOLDS_PATH = os.path.join(BASE_DIR, 'thresholds.json')

# ==========================================
# PYDANTIC SCHEMAS 
# ==========================================

class MqttConfig(BaseModel):
    broker: str
    port: int = Field(default=1883, ge=1, le=65535)

class SmsConfig(BaseModel):
    recipients: List[str]

# --- NEW UNIVERSAL SENSOR SCHEMA ---
class SensorConfig(BaseModel):
    """
    Validates the configuration for a single hardware sensor or hub.
    """
    id: str = Field(..., description="Unique identifier (e.g., 'arduino_hub')")
    driver: str = Field(..., description="The type of driver to load (e.g., 'serial', 'i2c', 'gpio')")
    params: Dict[str, Any] = Field(default_factory=dict, description="Hardware-specific parameters (port, address, etc.)")

class LabPulseConfig(BaseModel):
    """The Master Configuration Object"""
    mqtt: MqttConfig
    sms: SmsConfig
    
    # Replaces the hardcoded pump_room, dht11, etc.
    sensors: List[SensorConfig] = Field(default_factory=list, description="List of all connected hardware sensors")

# ==========================================
# CONFIGURATION LOADERS
# ==========================================

def load_config() -> LabPulseConfig:
    """Reads YAML and validates it strictly against the Pydantic schema."""
    if not os.path.exists(YAML_PATH):
        print(f"CRITICAL ERROR: Configuration file missing at {YAML_PATH}")
        sys.exit(1)

    with open(YAML_PATH, 'r') as file:
        try:
            yaml_data = yaml.safe_load(file)
        except yaml.YAMLError as e:
            print(f"CRITICAL ERROR: Invalid YAML formatting in config.yaml.\nDetails: {e}")
            sys.exit(1)

    try:
        # This line forces the dictionary through the validation engine
        validated_config = LabPulseConfig(**yaml_data)
        return validated_config
    except ValidationError as e:
        # Fail Fast: Print exact human-readable errors and kill the script
        print("\n=======================================================")
        print("CONFIGURATION VALIDATION FAILED ")
        print("LabPulse cannot start because config.yaml has errors:")
        for error in e.errors():
            location = " -> ".join([str(loc) for loc in error['loc']])
            print(f"- [ {location} ]: {error['msg']}")
        print("=======================================================\n")
        sys.exit(1)

def load_recipients() -> List[str]:
    """Pulls SMS numbers directly from the validated config object."""
    config = load_config()
    return config.sms.recipients

def load_all_thresholds() -> dict:
    """Reads the dynamic, user-adjustable thresholds from JSON."""
    if not os.path.exists(JSON_THRESHOLDS_PATH):
        return {}
    with open(JSON_THRESHOLDS_PATH, 'r') as file:
        return json.load(file)

def save_all_thresholds(thresholds_dict: dict):
    """Saves dynamic user adjustments back to JSON."""
    with open(JSON_THRESHOLDS_PATH, 'w') as file:
        json.dump(thresholds_dict, file, indent=4)