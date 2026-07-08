"""Command-line and LabPulse config loading helpers.

The shell wrapper owns user-facing flags. It passes a compact normalized set of
arguments here so the Python package can focus on structured YAML/JSON work.
"""

from pathlib import Path
import sys

import yaml

from .models import GeneratorOptions, GeneratorPaths, JsonDict


def parse_args(argv: list[str]) -> tuple[GeneratorPaths, GeneratorOptions]:
    """Parse the normalized arguments passed by the shell wrapper."""

    if len(argv) != 5:
        print(
            "Usage: generate_homeassistant_config.py CONFIG_PATH HA_CONFIG_DIR "
            "FRESH_HOMEASSISTANT REFRESH_DASHBOARD",
            file=sys.stderr,
        )
        sys.exit(2)

    return (
        GeneratorPaths(
            config_path=Path(argv[1]).expanduser().resolve(),
            ha_config_dir=Path(argv[2]).expanduser().resolve(),
        ),
        GeneratorOptions(
            fresh_homeassistant=argv[3] == "1",
            refresh_dashboard=argv[4] == "1",
        ),
    )


def load_labpulse_config(config_path: Path) -> JsonDict:
    """Read the LabPulse YAML config file and return an empty dict if blank."""

    if not config_path.exists():
        print(f"ERROR: config file does not exist: {config_path}", file=sys.stderr)
        sys.exit(1)

    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
