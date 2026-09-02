"""Generate deployment artifacts through the shared configuration pipeline."""

import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile
from uuid import uuid4

from labpulse import __version__
from labpulse.common.config import (
    ConfigDocument,
    ConfigError,
    format_config_error,
    load_config,
)
from labpulse.deployment.compose import (
    build_compose,
    service_slug,
)
from labpulse.homeassistant.generator import generate_homeassistant


def _mount_source(config_path: Path, project_dir: Path) -> str:
    """Return the host-side Compose path for the selected runtime config."""

    try:
        return "./" + config_path.relative_to(project_dir).as_posix()
    except ValueError:
        return config_path.as_posix()


def _replace_text(path: Path, text: str) -> None:
    """Atomically replace one generated text file on its destination filesystem."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".generating",
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(temporary_name, path)
    except Exception:
        try:
            Path(temporary_name).unlink()
        except FileNotFoundError:
            pass
        raise


def generate_deployment(
    config_path: Path,
    compose_output: Path,
    project_dir: Path,
    ha_config_dir: Path,
    runtime_image: str,
    force_simulated: bool = False,
) -> ConfigDocument:
    """Load once, stage every generated artifact, then install owned outputs."""

    config_path = config_path.expanduser().resolve()
    project_dir = project_dir.expanduser().resolve()
    compose_output = compose_output.expanduser().resolve()
    ha_config_dir = ha_config_dir.expanduser().resolve()
    document = load_config(config_path)
    compose_text = build_compose(
        document,
        config_mount_source=_mount_source(config_path, project_dir),
        runtime_image=runtime_image,
        force_simulated=force_simulated,
    )

    project_dir.mkdir(parents=True, exist_ok=True)
    staging_root = project_dir / f".labpulse-generation-{uuid4().hex}"
    staging_root.mkdir()
    try:
        staged_ha_dir = staging_root / "homeassistant" / "config"
        generate_homeassistant(document, staged_ha_dir)

        # No live generated file is touched until both Compose and every owned
        # Home Assistant artifact have been built successfully.
        _replace_text(compose_output, compose_text)
        owned_homeassistant_files = (
            (staged_ha_dir / "configuration.yaml", ha_config_dir / "configuration.yaml"),
            (
                staged_ha_dir / "packages" / "labpulse_generated.yaml",
                ha_config_dir / "packages" / "labpulse_generated.yaml",
            ),
            (staged_ha_dir / "labpulse-dashboard.yaml", ha_config_dir / "labpulse-dashboard.yaml"),
        )
        for staged_path, live_path in owned_homeassistant_files:
            _replace_text(live_path, staged_path.read_text(encoding="utf-8"))

        # These files are user-owned. Home Assistant needs them to exist, but
        # regeneration must never replace them.
        for filename in ("automations.yaml", "scripts.yaml", "scenes.yaml"):
            ui_path = ha_config_dir / filename
            if not ui_path.exists():
                _replace_text(ui_path, "[]\n")
    finally:
        shutil.rmtree(staging_root)

    (project_dir / "logs").mkdir(parents=True, exist_ok=True)
    return document


def main(argv: list[str] | None = None) -> int:
    """Load once and atomically install the requested generated outputs."""

    parser = argparse.ArgumentParser(
        description="Generate deployment files from validated LabPulse configuration"
    )
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", "--compose-output", required=True, dest="compose_output", type=Path)
    parser.add_argument("--project-dir", required=True, type=Path)
    parser.add_argument(
        "--ha-config-dir",
        type=Path,
        help="also generate Home Assistant files from the same config load",
    )
    parser.add_argument("-fake_usb", "--fake-usb", "--fake_usb", action="store_true", dest="fake_usb")
    args = parser.parse_args(argv)
    project_dir = args.project_dir.expanduser().resolve()
    compose_output = args.compose_output.expanduser().resolve()
    runtime_image = os.environ.get(
        "LABPULSE_IMAGE",
        f"ghcr.io/tommystorm-cpu/labpulse:{__version__}",
    ).strip()
    try:
        if args.ha_config_dir is not None:
            document = generate_deployment(
                args.config,
                compose_output,
                project_dir,
                args.ha_config_dir,
                runtime_image,
                args.fake_usb,
            )
        else:
            config_path = args.config.expanduser().resolve()
            document = load_config(config_path)
            compose_text = build_compose(
                document,
                config_mount_source=_mount_source(config_path, project_dir),
                runtime_image=runtime_image,
                force_simulated=args.fake_usb,
            )
            project_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / "logs").mkdir(parents=True, exist_ok=True)
            _replace_text(compose_output, compose_text)
    except ConfigError as error:
        print(format_config_error(error), file=sys.stderr)
        return 1
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Generated {compose_output}")
    print(f"LabPulse runtime image: {runtime_image}")
    print("LabPulse worker containers:")
    for service_name, service in document.config.services.items():
        if service.enabled:
            print(f"  labpulse-{service_slug(service_name)} -> {service_name}")
    if not args.fake_usb:
        for output_name, output in document.config.outputs.items():
            if output.enabled:
                print(f"  labpulse-output-{service_slug(output_name)} -> output {output_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
