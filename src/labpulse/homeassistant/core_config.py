"""Write core Home Assistant configuration and preserve UI-owned files."""

from pathlib import Path

from .paths import GeneratorPaths
from .template_utils import render_template_file


TEMPLATE_DIR = Path(__file__).resolve().parent / "templates" / "core"


def render_core(paths: GeneratorPaths) -> None:
    """Write shared Home Assistant configuration and UI-owned files."""

    # Create the Home Assistant config directory before writing its files.
    paths.ha_config_dir.mkdir(parents=True, exist_ok=True)

    # Render the main configuration that connects packages and the dashboard.
    render_template_file(
        TEMPLATE_DIR / "configuration.yaml.j2",
        paths.configuration_path,
        {"body": ""},
    )
    # Preserve existing UI files and create only those that are missing.
    ensure_ui_yaml_files(paths)

    print(f"Generated {paths.configuration_path}")


def ensure_ui_yaml_files(paths: GeneratorPaths) -> None:
    """Create Home Assistant UI-managed YAML files if they are missing.

    Home Assistant's automation/script/scene editors write to these files.
    They must be included by configuration.yaml, but the generator should never
    overwrite them once a user has made UI edits.
    """

    for path in (
        paths.ui_automations_path,
        paths.ui_scripts_path,
        paths.ui_scenes_path,
    ):
        # Initialize a missing UI file without overwriting user-created entries.
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")
            print(f"Created {path}")
