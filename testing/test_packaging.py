"""Contract checks for the pipx-installable LabPulse distribution."""

from pathlib import Path
import sys
import tomllib


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

import labpulse
from labpulse.installer import ASSET_NAMES, find_install_assets


def main() -> None:
    """Validate package metadata, resources, command, and live-directory naming."""

    metadata = tomllib.loads(
        (REPOSITORY / "pyproject.toml").read_text(encoding="utf-8")
    )
    project = metadata["project"]
    if project["name"] != "labpulse":
        raise AssertionError("distribution name must be labpulse")
    if project["version"] != labpulse.__version__:
        raise AssertionError("package metadata and module versions differ")
    expected_commands = {
        "labpulse": "labpulse.control:main",
        "labpulse-up": "labpulse.control:up_main",
        "labpulse-down": "labpulse.control:down_main",
        "labpulse-restart": "labpulse.control:restart_main",
        "labpulse-ps": "labpulse.control:ps_main",
        "labpulse-logs": "labpulse.control:logs_main",
        "labpulse-edit": "labpulse.control:edit_main",
        "labpulse-open": "labpulse.control:open_main",
        "labpulse-setup": "labpulse.installer:main",
    }
    for command, target in expected_commands.items():
        if project["scripts"].get(command) != target:
            raise AssertionError(f"pipx command is not declared: {command}")

    assets = find_install_assets()
    missing = [name for name in ASSET_NAMES if not (assets / name).is_file()]
    if missing:
        raise AssertionError(f"installer assets are missing: {missing}")

    setup_source = (REPOSITORY / "setup_container_fs.sh").read_text(
        encoding="utf-8"
    )
    for fragment in (
        '$HOME/labpulse-live',
        "LABPULSE_SETUP_ASSET_DIR",
        "LABPULSE_PACKAGE_SOURCE",
        'replace_dir "$PACKAGE_SOURCE"',
    ):
        if fragment not in setup_source:
            raise AssertionError(f"packaged setup contract missing: {fragment}")
    if "labpulse-" + "ha" in setup_source:
        raise AssertionError("old live-directory name remains in setup")

    print("[PASS] package metadata and version")
    print("[PASS] pipx console entry points")
    print("[PASS] packaged setup assets")
    print("[PASS] labpulse-live deployment contract")


if __name__ == "__main__":
    main()
