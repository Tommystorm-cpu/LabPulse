from pathlib import Path
import sys

from labpulse_common.config import load_config

from .alarm import render_alarm
from .dashboard import render_dashboard
from .data_models import GeneratorOptions, GeneratorPaths, build_render_model
from .write_yaml import render_core


def parse_args(argv: list[str]) -> tuple[GeneratorPaths, GeneratorOptions]:
    """Parse the normalized arguments passed by the shell wrapper."""

    if len(argv) != 4:
        print(
            "Usage: python3 -m labpulse_homeassistant "
            "CONFIG_PATH HA_CONFIG_DIR RESET_DASHBOARD",
            file=sys.stderr,
        )
        sys.exit(2)

    return (
        GeneratorPaths(
            config_path=Path(argv[1]).expanduser().resolve(),
            ha_config_dir=Path(argv[2]).expanduser().resolve(),
        ),
        GeneratorOptions(
            reset_dashboard=argv[3] == "1",
        ),
    )


def main(argv: list[str]) -> int:
    """Generate Home Assistant config from the LabPulse config.

    The generation path is read -> normalize model -> render templates. The
    shell wrapper owns dashboard backup/load behavior before this entry point.
    """

    paths, options = parse_args(argv)
    config = load_config(paths.config_path)
    model = build_render_model(config)
    render_core(paths, model)
    render_alarm(paths, model)
    render_dashboard(paths, options, model)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
