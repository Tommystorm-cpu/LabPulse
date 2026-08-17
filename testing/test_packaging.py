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
    if "version" in project:
        raise AssertionError("package version must not be hard-coded")
    if "version" not in project.get("dynamic", []):
        raise AssertionError("package version must be dynamically derived")
    build_requirements = metadata["build-system"]["requires"]
    if not any(requirement.startswith("setuptools-scm") for requirement in build_requirements):
        raise AssertionError("setuptools-scm must provide the package version")
    if "tool" not in metadata or "setuptools_scm" not in metadata["tool"]:
        raise AssertionError("setuptools-scm must be explicitly enabled")
    init_source = (REPOSITORY / "src" / "labpulse" / "__init__.py").read_text(
        encoding="utf-8"
    )
    if 'version("labpulse")' not in init_source:
        raise AssertionError("runtime version must come from installed metadata")
    if not labpulse.__version__:
        raise AssertionError("runtime package version is empty")
    if project.get("license") != "MIT":
        raise AssertionError("package metadata must declare the MIT SPDX licence")
    if project.get("license-files") != ["LICENSE"]:
        raise AssertionError("package metadata must include the root licence")
    licence = (REPOSITORY / "LICENSE").read_text(encoding="utf-8")
    for fragment in (
        "MIT License",
        "Copyright (c) 2026 LabPulse contributors",
        'THE SOFTWARE IS PROVIDED "AS IS"',
    ):
        if fragment not in licence:
            raise AssertionError(f"MIT licence text is incomplete: {fragment}")
    expected_commands = {
        "labpulse": "labpulse.control:main",
        "labpulse-up": "labpulse.control:up_main",
        "labpulse-down": "labpulse.control:down_main",
        "labpulse-restart": "labpulse.control:restart_main",
        "labpulse-ps": "labpulse.control:ps_main",
        "labpulse-logs": "labpulse.control:logs_main",
        "labpulse-config": "labpulse.control:config_main",
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

    homeassistant_data = metadata["tool"]["setuptools"]["package-data"][
        "labpulse.homeassistant"
    ]
    if "templates/*/*/*.j2" not in homeassistant_data:
        raise AssertionError("nested Home Assistant templates are not packaged")
    nested_templates = (
        "alarm/automations/measurement.yaml.j2",
        "alarm/automations/power_reconciliation.yaml.j2",
        "dashboard/alarm_setup/bulk_editor.yaml.j2",
        "dashboard/setup_subviews/measurement_cards.yaml.j2",
    )
    template_root = REPOSITORY / "src" / "labpulse" / "homeassistant" / "templates"
    for relative_path in nested_templates:
        if not (template_root / relative_path).is_file():
            raise AssertionError(f"nested Home Assistant template is missing: {relative_path}")

    setup_source = (REPOSITORY / "deployment" / "setup_container_fs.sh").read_text(
        encoding="utf-8"
    )
    for fragment in (
        '$HOME/labpulse-live',
        "LABPULSE_SETUP_ASSET_DIR",
        "LABPULSE_PACKAGE_PARENT",
        "labpulse-installed-package.pth",
    ):
        if fragment not in setup_source:
            raise AssertionError(f"packaged setup contract missing: {fragment}")
    for forbidden in ("LABPULSE_PACKAGE_SOURCE", "labpulse-python"):
        if forbidden in setup_source:
            raise AssertionError(f"obsolete packaged setup path remains: {forbidden}")
    if "labpulse-" + "ha" in setup_source:
        raise AssertionError("old live-directory name remains in setup")

    print("[PASS] tag-derived package and runtime version")
    print("[PASS] MIT licence metadata and text")
    print("[PASS] pipx console entry points")
    print("[PASS] packaged setup assets")
    print("[PASS] nested Home Assistant templates")
    print("[PASS] labpulse-live deployment contract")


if __name__ == "__main__":
    main()
