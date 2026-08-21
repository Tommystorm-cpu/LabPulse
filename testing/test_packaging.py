"""Contract checks for the pipx-installable LabPulse distribution."""

from pathlib import Path
import tomllib

import pytest

import labpulse
from labpulse.installer import ASSET_NAMES, find_install_assets


REPOSITORY = Path(__file__).resolve().parents[1]


def metadata() -> dict[str, object]:
    """Return the decoded project metadata."""

    return tomllib.loads((REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"))


def test_package_version_comes_from_installed_metadata() -> None:
    """Require one dynamic version source for builds and runtime reporting."""

    data = metadata()
    project = data["project"]
    assert isinstance(project, dict)
    assert project["name"] == "labpulse"
    assert "version" not in project
    assert "version" in project.get("dynamic", [])
    build_system = data["build-system"]
    assert isinstance(build_system, dict)
    build_requirements = build_system["requires"]
    assert any(item.startswith("setuptools-scm") for item in build_requirements)
    tool = data.get("tool")
    assert isinstance(tool, dict) and "setuptools_scm" in tool
    init_source = (REPOSITORY / "src/labpulse/__init__.py").read_text(encoding="utf-8")
    assert 'version("labpulse")' in init_source
    assert labpulse.__version__


def test_hardware_dependencies_are_grouped_by_transport() -> None:
    """Keep shared connection libraries independent of individual drivers."""

    project = metadata()["project"]
    extras = project["optional-dependencies"]
    assert set(extras) == {"serial", "i2c", "gpio", "dev"}
    assert extras["serial"] == ["pyserial>=3.5,<4"]
    assert extras["i2c"] == ["smbus2>=0.5,<1"]
    assert extras["gpio"] == [
        "adafruit-blinka>=8,<9",
        "adafruit-circuitpython-dht>=4,<5",
        "lgpio>=0.2,<1",
    ]


@pytest.mark.parametrize(
    "fragment",
    ("MIT License", "Copyright (c) 2026 LabPulse contributors", 'THE SOFTWARE IS PROVIDED "AS IS"'),
)
def test_mit_license_metadata_and_text(fragment: str) -> None:
    """Require valid MIT metadata and one canonical licence fragment."""

    project = metadata()["project"]
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert fragment in (REPOSITORY / "LICENSE").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("command", "target"),
    (
        ("labpulse", "labpulse.control:main"),
        ("labpulse-up", "labpulse.control:up_main"),
        ("labpulse-down", "labpulse.control:down_main"),
        ("labpulse-restart", "labpulse.control:restart_main"),
        ("labpulse-ps", "labpulse.control:ps_main"),
        ("labpulse-logs", "labpulse.control:logs_main"),
        ("labpulse-config", "labpulse.control:config_main"),
        ("labpulse-open", "labpulse.control:open_main"),
        ("labpulse-setup", "labpulse.installer:main"),
    ),
)
def test_console_entry_point(command: str, target: str) -> None:
    """Require one installed command to resolve to its public entry point."""

    project = metadata()["project"]
    assert project["scripts"].get(command) == target


def test_packaged_installer_assets_exist() -> None:
    """Require every declared installer asset to exist in the source tree."""

    assets = find_install_assets()
    assert [name for name in ASSET_NAMES if not (assets / name).is_file()] == []


@pytest.mark.parametrize(
    "relative_path",
    (
        "alarm/automations/measurement.yaml.j2",
        "alarm/automations/power_reconciliation.yaml.j2",
        "dashboard/alarm_setup/bulk_editor.yaml.j2",
        "dashboard/setup_subviews/measurement_cards.yaml.j2",
    ),
)
def test_nested_homeassistant_template_is_packaged(relative_path: str) -> None:
    """Require nested template globs and one representative source file."""

    tool = metadata()["tool"]
    package_data = tool["setuptools"]["package-data"]["labpulse.homeassistant"]
    assert "templates/*/*/*.j2" in package_data
    template_root = REPOSITORY / "src/labpulse/homeassistant/templates"
    assert (template_root / relative_path).is_file()


@pytest.mark.parametrize(
    "fragment",
    ("$HOME/labpulse-live", "LABPULSE_SETUP_ASSET_DIR", "LABPULSE_PACKAGE_PARENT", "labpulse-installed-package.pth"),
)
def test_live_setup_contract(fragment: str) -> None:
    """Require one supported live-installation setup fragment."""

    setup_source = (REPOSITORY / "deployment/setup_container_fs.sh").read_text(encoding="utf-8")
    assert fragment in setup_source


@pytest.mark.parametrize("fragment", ("LABPULSE_PACKAGE_SOURCE", "labpulse-python"))
def test_live_setup_has_no_obsolete_source_copy(fragment: str) -> None:
    """Reject obsolete live-installation source paths."""

    setup_source = (REPOSITORY / "deployment/setup_container_fs.sh").read_text(encoding="utf-8")
    assert fragment not in setup_source
    assert "labpulse-" + "ha" not in setup_source
