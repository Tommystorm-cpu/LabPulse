"""Contract checks for the pipx-installable LabPulse distribution."""

from pathlib import Path, PurePosixPath
import tomllib

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
        "gpiod>=2,<3",
        "lgpio>=0.2,<1",
    ]


def test_mit_license_metadata_and_file() -> None:
    """Require valid MIT metadata and a non-empty declared licence file."""

    project = metadata()["project"]
    assert project["license"] == "MIT"
    assert project["license-files"] == ["LICENSE"]
    assert (REPOSITORY / "LICENSE").read_text(encoding="utf-8").strip()


def test_public_console_entry_points() -> None:
    """Require the installed command surface to resolve to public entry points."""

    expected = dict(
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
        )
    )

    project = metadata()["project"]
    assert project["scripts"] == expected


def test_packaged_installer_assets_exist() -> None:
    """Require every declared installer asset to exist in the source tree."""

    assets = find_install_assets()
    assert [name for name in ASSET_NAMES if not (assets / name).is_file()] == []


def test_homeassistant_package_data_covers_every_template() -> None:
    """Require package-data patterns to cover the complete template tree."""

    tool = metadata()["tool"]
    patterns = tool["setuptools"]["package-data"]["labpulse.homeassistant"]
    template_root = REPOSITORY / "src/labpulse/homeassistant/templates"
    templates = [
        PurePosixPath("templates") / path.relative_to(template_root).as_posix()
        for path in template_root.rglob("*")
        if path.is_file() and path.suffix in {".j2", ".yaml"}
    ]
    uncovered = [
        str(path)
        for path in templates
        if not any(path.match(pattern) for pattern in patterns)
    ]
    assert uncovered == []
