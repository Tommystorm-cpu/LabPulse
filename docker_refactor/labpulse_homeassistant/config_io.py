from pathlib import Path
import sys

from .model import GeneratorOptions, GeneratorPaths


def parse_args(argv: list[str]) -> tuple[GeneratorPaths, GeneratorOptions]:
    """Parse the normalized arguments passed by the shell wrapper."""

    if len(argv) != 4:
        print(
            "Usage: python3 -m labpulse_homeassistant.generator "
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
