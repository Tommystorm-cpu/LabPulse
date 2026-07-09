from pathlib import Path
import sys

import yaml

from .model import GeneratorOptions, GeneratorPaths, JsonDict


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


def load_labpulse_config(config_path: Path) -> JsonDict:
    """Read the LabPulse YAML config file and return an empty dict if blank."""

    if not config_path.exists():
        print(f"ERROR: config file does not exist: {config_path}", file=sys.stderr)
        sys.exit(1)

    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
