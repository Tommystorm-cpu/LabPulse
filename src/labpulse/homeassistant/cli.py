"""Command-line interface for Home Assistant configuration generation."""

from __future__ import annotations

import argparse
from argparse import Namespace
from pathlib import Path
import sys

from labpulse.common.config import ConfigError, format_config_error, load_config

from .generator import generate_homeassistant


def parse_args(argv: list[str] | None = None) -> Namespace:
    """Parse paths for Home Assistant configuration generation."""

    parser = argparse.ArgumentParser(
        description="Generate Home Assistant files from LabPulse configuration"
    )
    parser.add_argument("config", type=Path, help="Path to LabPulse config YAML")
    parser.add_argument(
        "ha_config_dir",
        type=Path,
        help="Home Assistant configuration directory",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Load one config file and generate Home Assistant managed output."""

    args = parse_args(argv)
    try:
        # Use the same config reader as the rest of LabPulse so every command
        # accepts and rejects the same settings.
        document = load_config(args.config.expanduser().resolve())
        generate_homeassistant(document, args.ha_config_dir)
    except ConfigError as error:
        # Show where the config is wrong without printing a Python traceback.
        print(format_config_error(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
