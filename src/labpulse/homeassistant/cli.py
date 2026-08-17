from pathlib import Path
import sys

from labpulse.common.config import ConfigDocument, ConfigError, format_config_error, load_config

from .alarm_package import render_alarm
from .measurement_catalog import build_measurement_catalog
from .render_model import RenderModel
from .paths import GeneratorPaths
from .core_config import render_core
from .dashboard_writer import render_yaml_dashboard


def parse_args(
    argv: list[str],
) -> GeneratorPaths:
    """Parse the normalized arguments passed by the shell wrapper."""

    # Require the config path and Home Assistant output directory.
    if len(argv) != 3:
        print(
            "Usage: python3 -m labpulse.homeassistant "
            "CONFIG_PATH HA_CONFIG_DIR",
            file=sys.stderr,
        )
        sys.exit(2)

    # Normalize both command-line paths before the generator uses them.
    return GeneratorPaths(
        config_path=Path(argv[1]).expanduser().resolve(),
        ha_config_dir=Path(argv[2]).expanduser().resolve(),
    )


def generate_homeassistant(document: ConfigDocument, paths: GeneratorPaths) -> None:
    """Generate all owned Home Assistant files from one validated document."""

    config = document.config
    measurement_catalog = build_measurement_catalog(config)
    render_model = RenderModel.from_config(config, measurement_catalog)
    render_core(paths)
    render_alarm(paths, render_model)
    render_yaml_dashboard(paths, config, measurement_catalog, render_model)


def main(argv: list[str]) -> int:
    """Generate Home Assistant config from the LabPulse config.

    The generation path is read -> normalize model -> render supported YAML.
    """

    # Load and validate the single LabPulse configuration source.
    paths = parse_args(argv)
    try:
        document = load_config(paths.config_path)
    except ConfigError as error:
        print(format_config_error(error), file=sys.stderr)
        return 1
    generate_homeassistant(document, paths)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
