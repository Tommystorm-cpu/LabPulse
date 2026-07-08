"""Coordinate LabPulse Home Assistant config generation.

This is the module called by `python3 -m labpulse_homeassistant.generator`.
It intentionally stays small: each imported module owns one task, and this file
only wires those tasks together in the order they run.
"""

import sys

from .builder import build_generated_config
from .config_io import load_labpulse_config, parse_args
from .entities import load_entity_registry
from .writer import write_generated_files


def main(argv: list[str]) -> int:
    """Generate Home Assistant config from the LabPulse config.

    The generation path is read -> resolve entity IDs -> build dictionaries ->
    write files. Keeping that sequence explicit makes the setup script easier
    to debug on a Raspberry Pi.
    """

    paths, options = parse_args(argv)
    config = load_labpulse_config(paths.config_path)
    entity_registry = load_entity_registry(paths)
    generated = build_generated_config(config, entity_registry)
    write_generated_files(paths, options, generated)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
