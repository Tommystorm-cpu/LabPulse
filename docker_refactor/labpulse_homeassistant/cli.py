from pathlib import Path
import os
import sys

from labpulse_common.config import load_config

from .alarm import render_alarm
from .dashboard import render_dashboard
from .data_models import GeneratorPaths, build_render_model
from .entity_registry import fetch_entity_registry, resolve_model_entities
from .write_yaml import load_previous_entity_ids, render_core


def parse_args(
    argv: list[str],
) -> tuple[GeneratorPaths, bool, bool, bool, str]:
    """Parse the normalized arguments passed by the shell wrapper."""

    if len(argv) not in {4, 7}:
        print(
            "Usage: python3 -m labpulse_homeassistant "
            "CONFIG_PATH HA_CONFIG_DIR RESET_DASHBOARD "
            "[RESOLVE_ENTITIES SYNC_DASHBOARD_ENTITIES HA_URL]",
            file=sys.stderr,
        )
        sys.exit(2)

    resolve_entities = len(argv) == 7 and argv[4] == "1"
    sync_dashboard_entities = len(argv) == 7 and argv[5] == "1"
    home_assistant_url = argv[6] if len(argv) == 7 else "http://127.0.0.1:8123"
    if sync_dashboard_entities and not resolve_entities:
        print("ERROR: Dashboard entity sync requires entity resolution.", file=sys.stderr)
        sys.exit(2)

    return (
        GeneratorPaths(
            config_path=Path(argv[1]).expanduser().resolve(),
            ha_config_dir=Path(argv[2]).expanduser().resolve(),
        ),
        argv[3] == "1",
        resolve_entities,
        sync_dashboard_entities,
        home_assistant_url,
    )


def main(argv: list[str]) -> int:
    """Generate Home Assistant config from the LabPulse config.

    The generation path is read -> normalize model -> render templates. The
    shell wrapper owns dashboard backup/load behavior before this entry point.
    """

    (
        paths,
        reset_dashboard,
        resolve_entities,
        sync_dashboard_entities,
        home_assistant_url,
    ) = parse_args(argv)
    config = load_config(paths.config_path)
    model = build_render_model(config)
    replacements: dict[str, str] = {}

    if resolve_entities:
        access_token = os.environ.get("LABPULSE_HA_TOKEN", "")
        if not access_token:
            print(
                "ERROR: --resolve-entities requires LABPULSE_HA_TOKEN.",
                file=sys.stderr,
            )
            return 1
        previous_entity_ids = load_previous_entity_ids(paths.entity_map_path)
        try:
            snapshot = fetch_entity_registry(home_assistant_url, access_token)
            report = resolve_model_entities(model, snapshot, strict=True)
        except Exception as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(report.summary())
        replacements = report.replacements(previous_entity_ids)

    render_core(paths, model)
    render_alarm(paths, model)
    render_dashboard(
        paths,
        reset_dashboard,
        model,
        sync_entity_ids=sync_dashboard_entities,
        replacements=replacements,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
