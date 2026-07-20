"""Filesystem locations written by the Home Assistant generator."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GeneratorPaths:
    """Filesystem paths used by the Home Assistant generator."""

    config_path: Path
    ha_config_dir: Path

    @property
    def packages_dir(self) -> Path:
        """Return the Home Assistant packages directory."""

        return self.ha_config_dir / "packages"

    @property
    def package_path(self) -> Path:
        """Return the generated package YAML path."""

        return self.packages_dir / "labpulse_generated.yaml"

    @property
    def entity_map_path(self) -> Path:
        """Return the generated deterministic entity map path."""

        return self.ha_config_dir / "labpulse_entity_map.yaml"

    @property
    def configuration_path(self) -> Path:
        """Return Home Assistant's main configuration path."""

        return self.ha_config_dir / "configuration.yaml"

    @property
    def dashboard_path(self) -> Path:
        """Return the generated YAML-mode LabPulse dashboard path."""

        return self.ha_config_dir / "labpulse-dashboard.yaml"

    @property
    def ui_automations_path(self) -> Path:
        """Return the Home Assistant UI-managed automations path."""

        return self.ha_config_dir / "automations.yaml"

    @property
    def ui_scripts_path(self) -> Path:
        """Return the Home Assistant UI-managed scripts path."""

        return self.ha_config_dir / "scripts.yaml"

    @property
    def ui_scenes_path(self) -> Path:
        """Return the Home Assistant UI-managed scenes path."""

        return self.ha_config_dir / "scenes.yaml"
