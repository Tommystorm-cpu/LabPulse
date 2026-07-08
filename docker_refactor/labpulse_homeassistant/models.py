"""Small data containers used by the Home Assistant config generator.

These classes deliberately contain little behavior. They make the handoff
between modules explicit without turning generated Home Assistant dictionaries
into a deep object model.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


JsonDict = dict[str, Any]


@dataclass
class GeneratorPaths:
    """Filesystem paths used by the Home Assistant generator.

    The caller provides only the live LabPulse config and Home Assistant config
    directory. The generated file paths are derived here to avoid recomputing
    string paths throughout the package.
    """

    config_path: Path
    ha_config_dir: Path

    @property
    def packages_dir(self) -> Path:
        """Return the Home Assistant packages directory."""

        return self.ha_config_dir / "packages"

    @property
    def package_path(self) -> Path:
        """Return the generated threshold package path."""

        return self.packages_dir / "labpulse_thresholds.yaml"

    @property
    def dashboard_cards_path(self) -> Path:
        """Return the reference alarm-card YAML path."""

        return self.ha_config_dir / "labpulse_alarm_cards.yaml"

    @property
    def configuration_path(self) -> Path:
        """Return Home Assistant's main configuration path."""

        return self.ha_config_dir / "configuration.yaml"

    @property
    def storage_dir(self) -> Path:
        """Return Home Assistant's hidden UI storage directory."""

        return self.ha_config_dir / ".storage"

    @property
    def lovelace_path(self) -> Path:
        """Return the editable Lovelace dashboard storage file."""

        return self.storage_dir / "lovelace"

    @property
    def entity_registry_path(self) -> Path:
        """Return Home Assistant's entity registry storage file."""

        return self.storage_dir / "core.entity_registry"


@dataclass
class GeneratorOptions:
    """Command-line options passed from the shell wrapper."""

    fresh_homeassistant: bool
    refresh_dashboard: bool


@dataclass
class EntityRegistry:
    """Home Assistant MQTT entity registry lookup data."""

    by_unique_id: dict[str, str]
    mqtt_entries: list[JsonDict]


@dataclass
class ReadingContext:
    """Generated names and IDs for one service reading.

    This is the small bundle of facts needed by dashboard and automation code
    after entity names have been resolved.
    """

    name: str
    key: str
    reading_id: str
    label: str
    mode: str
    entity_id: str
    active_entity: str


@dataclass
class GeneratedConfig:
    """Home Assistant config structures being built in memory."""

    input_numbers: JsonDict = field(default_factory=dict)
    input_booleans: JsonDict = field(default_factory=dict)
    automations: list[JsonDict] = field(default_factory=list)
    dashboard_cards: list[JsonDict] = field(default_factory=list)
    dashboard_sections: list[JsonDict] = field(default_factory=list)
    system_health_cards: list[JsonDict] = field(default_factory=list)
