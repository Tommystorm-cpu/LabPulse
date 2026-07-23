"""Launch the packaged Raspberry Pi filesystem bootstrap."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Sequence


ASSET_NAMES = (
    "config.yaml",
    "deployment/edit_config.sh",
    "deployment/generate_compose.sh",
    "deployment/generate_homeassistant_config.sh",
    "requirements-host.txt",
    "deployment/setup_container_fs.sh",
    "setup_usb_devices.py",
    "simulate_serial.py",
)


def find_install_assets() -> Path:
    """Find deployment files in an installed wheel or source checkout."""

    candidates = (
        Path(__file__).resolve().parents[2],
        Path(sys.prefix) / "share" / "labpulse",
    )
    for candidate in candidates:
        if all((candidate / name).is_file() for name in ASSET_NAMES):
            return candidate
    searched = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(
        "LabPulse installation assets are missing. "
        f"Reinstall the package with pipx. Searched: {searched}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the packaged filesystem setup with assets and package source."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    bash = shutil.which("bash")
    if bash is None:
        print(
            "ERROR: LabPulse setup requires Bash and is supported on "
            "Raspberry Pi OS/Linux.",
            file=sys.stderr,
        )
        return 1

    try:
        assets = find_install_assets()
    except FileNotFoundError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    environment = os.environ.copy()
    environment["LABPULSE_SETUP_ASSET_DIR"] = str(assets)
    environment["LABPULSE_PACKAGE_SOURCE"] = str(Path(__file__).resolve().parent)
    environment.setdefault("LABPULSE_SETUP_COMMAND", "labpulse-setup")

    result = subprocess.run(
        [bash, str(assets / "deployment" / "setup_container_fs.sh"), *arguments],
        env=environment,
        check=False,
    )
    return result.returncode
