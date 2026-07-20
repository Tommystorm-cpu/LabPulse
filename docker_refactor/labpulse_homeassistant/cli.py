from pathlib import Path
import sys

from labpulse_common.config import load_config

from .alarm import render_alarm
from .inventory import build_reading_inventory
from .model_builder import build_render_model
from .paths import GeneratorPaths
from .write_yaml import render_core
from .yaml_dashboard import render_yaml_dashboard


def parse_args(
    argv: list[str],
) -> GeneratorPaths:
    """Parse the normalized arguments passed by the shell wrapper."""

    if len(argv) != 3:
        print(
            "Usage: python3 -m labpulse_homeassistant "
            "CONFIG_PATH HA_CONFIG_DIR",
            file=sys.stderr,
        )
        sys.exit(2)

    return GeneratorPaths(
        config_path=Path(argv[1]).expanduser().resolve(),
        ha_config_dir=Path(argv[2]).expanduser().resolve(),
    )


def main(argv: list[str]) -> int:
    """Generate Home Assistant config from the LabPulse config.

    The generation path is read -> normalize model -> render supported YAML.
    """

    paths = parse_args(argv)
    config = load_config(paths.config_path)
    inventory = build_reading_inventory(config)
    model = build_render_model(config, inventory)
    render_core(paths, model)
    render_alarm(paths, model)
    render_yaml_dashboard(paths, config, inventory, model)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
