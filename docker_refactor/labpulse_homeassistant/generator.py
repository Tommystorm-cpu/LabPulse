import sys

from labpulse_common.config import load_config

from .config_io import parse_args
from .model import build_render_model
from .render import render_all


def main(argv: list[str]) -> int:
    """Generate Home Assistant config from the LabPulse config.

    The generation path is read -> normalize model -> render templates. The
    shell wrapper owns dashboard backup/load behavior before this entry point.
    """

    paths, options = parse_args(argv)
    config = load_config(paths.config_path)
    model = build_render_model(config)
    render_all(paths, options, model)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
