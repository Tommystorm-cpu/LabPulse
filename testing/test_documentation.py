"""Keep maintained documentation links and complete examples executable."""

from pathlib import Path
import re
from urllib.parse import unquote

import pytest

from labpulse.deployment.generate import generate_deployment


DOCUMENTATION_EXAMPLES = (
    "calculated-measurement.yaml",
    "minimal-serial.yaml",
    "mqtt-input.yaml",
)

FINAL_DOCS = {
    "ARCHITECTURE.md",
    "CONFIGURATION.md",
    "DEVELOPMENT.md",
    "HARDWARE.md",
    "INSTALLATION.md",
    "README.md",
    "USER_GUIDE.md",
}

README_PATHS = {
    "README.md",
    "deployment/README.md",
    "docs/README.md",
    "firmware/README.md",
    "src/labpulse/README.md",
    "src/labpulse/common/README.md",
    "src/labpulse/deployment/README.md",
    "src/labpulse/hardware/README.md",
    "src/labpulse/hardware/drivers/README.md",
    "src/labpulse/homeassistant/README.md",
    "src/labpulse/homeassistant/templates/README.md",
    "src/labpulse/output/README.md",
    "src/labpulse/sms/README.md",
    "testing/README.md",
    "testing/real_hardware/README.md",
}

REMOVED_GUIDES = {
    "CODE_GUIDE.md",
    "DRIVER_DEVELOPMENT.md",
    "HOME_ASSISTANT.md",
    "OPERATIONS.md",
    "PRODUCT_SCOPE.md",
    "REPOSITORY.md",
    "SERIAL_PROTOCOL.md",
    "SMS.md",
    "SUPPORT.md",
    "TROUBLESHOOTING.md",
}

SIGNIFICANT_MODULES = {
    "src/labpulse/README.md": ("backup.py", "control.py", "doctor.py", "installer.py"),
    "src/labpulse/common/README.md": (
        "config.py",
        "fake_config.py",
        "generated_files.py",
        "identity.py",
        "logging_config.py",
        "measurement_config.py",
        "mqtt_contracts.py",
        "output_config.py",
        "service_config.py",
        "sms_templates.py",
    ),
    "src/labpulse/deployment/README.md": ("compose.py", "generate.py"),
    "src/labpulse/hardware/README.md": (
        "driver.py",
        "homeassistant_publisher.py",
        "registry.py",
        "runner.py",
    ),
    "src/labpulse/hardware/drivers/README.md": (
        "_gpio.py",
        "dht11.py",
        "gpio_input.py",
        "gpio_output.py",
        "mqtt_json.py",
        "serial_pipe.py",
        "sht40.py",
        "x1200.py",
    ),
    "src/labpulse/homeassistant/README.md": ("alarm.py", "generator.py"),
    "src/labpulse/output/README.md": ("service.py",),
    "src/labpulse/sms/README.md": ("sender.py", "subscriber.py"),
}


def _maintained_markdown_files(repository_root: Path) -> tuple[Path, ...]:
    """Return current guides while excluding historical and generated trees."""

    root_guides = (
        repository_root / "README.md",
        repository_root / "CHANGELOG.md",
        repository_root / "CONTRIBUTING.md",
        repository_root / "ROADMAP.md",
    )
    readmes = tuple(repository_root / path for path in sorted(README_PATHS - {"README.md"}))
    return (*root_guides, *readmes, *sorted((repository_root / "docs").glob("*.md")))


def test_documentation_structure_is_intentional(repository_root: Path) -> None:
    """Keep the agreed guide set and README ownership hierarchy exact."""

    assert {path.name for path in (repository_root / "docs").glob("*.md")} == FINAL_DOCS

    ignored_parts = {".git", ".venv", "legacy", "tmp", "__pycache__"}
    actual_readmes = {
        path.relative_to(repository_root).as_posix()
        for path in repository_root.rglob("README.md")
        if not ignored_parts.intersection(path.relative_to(repository_root).parts)
    }
    assert actual_readmes == README_PATHS

    installation = (repository_root / "docs" / "INSTALLATION.md").read_text(encoding="utf-8")
    assert installation.rstrip().split("\n## ")[-1].startswith("Troubleshooting")


def test_removed_guides_are_absent_and_unreferenced(repository_root: Path) -> None:
    """Prevent links from drifting back to pages absorbed by the new owners."""

    for filename in REMOVED_GUIDES:
        assert not (repository_root / "docs" / filename).exists()

    references = "\n".join(
        path.read_text(encoding="utf-8") for path in _maintained_markdown_files(repository_root)
    )
    for filename in REMOVED_GUIDES:
        assert filename not in references


@pytest.mark.parametrize(("readme_path", "modules"), SIGNIFICANT_MODULES.items())
def test_package_readme_accounts_for_significant_modules(
    readme_path: str,
    modules: tuple[str, ...],
    repository_root: Path,
) -> None:
    """Require local package guides to name their important immediate modules."""

    readme = (repository_root / readme_path).read_text(encoding="utf-8")
    for module in modules:
        assert (repository_root / readme_path).parent.joinpath(module).is_file()
        assert f"`{module}`" in readme


def test_maintained_markdown_has_no_common_mojibake(repository_root: Path) -> None:
    """Reject common signs that UTF-8 documentation was decoded incorrectly."""

    suspicious = ("\ufffd", "Ã", "Â", "â€", "â€™", "â€“", "â€”")
    for path in _maintained_markdown_files(repository_root):
        content = path.read_text(encoding="utf-8")
        assert not any(marker in content for marker in suspicious), path


def _github_anchor(heading: str) -> str:
    """Approximate GitHub's stable anchor for the headings used in this repo."""

    without_tags = re.sub(r"<[^>]+>", "", heading.lower())
    without_punctuation = re.sub(r"[^\w\s-]", "", without_tags)
    return re.sub(r"\s+", "-", without_punctuation.strip())


def _heading_anchors(markdown: str) -> set[str]:
    """Collect anchors outside fenced examples, including duplicate suffixes."""

    anchors: set[str] = set()
    occurrences: dict[str, int] = {}
    in_fence = False
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match is None:
            continue
        base = _github_anchor(match.group(1))
        occurrence = occurrences.get(base, 0)
        occurrences[base] = occurrence + 1
        anchors.add(base if occurrence == 0 else f"{base}-{occurrence}")
    return anchors


def test_repository_relative_documentation_links_resolve(repository_root: Path) -> None:
    """Require every maintained local Markdown path and heading to exist."""

    markdown_files = _maintained_markdown_files(repository_root)
    anchors_by_path = {
        path.resolve(): _heading_anchors(path.read_text(encoding="utf-8"))
        for path in markdown_files
    }
    failures: list[str] = []

    for source in markdown_files:
        markdown = source.read_text(encoding="utf-8")
        for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", markdown):
            target = match.group(1)
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path_text, separator, fragment = target.partition("#")
            destination = (source.parent / unquote(path_text)).resolve() if path_text else source.resolve()
            if not destination.exists():
                failures.append(f"{source.relative_to(repository_root)} -> {target}: missing path")
                continue
            if separator and destination.suffix.lower() == ".md":
                anchors = anchors_by_path.get(destination)
                if anchors is None:
                    anchors = _heading_anchors(destination.read_text(encoding="utf-8"))
                if unquote(fragment).lower() not in anchors:
                    failures.append(f"{source.relative_to(repository_root)} -> {target}: missing heading")

    if failures:
        raise AssertionError("Broken documentation links:\n" + "\n".join(failures))


@pytest.mark.parametrize("filename", DOCUMENTATION_EXAMPLES)
def test_complete_configuration_example_generates(
    filename: str,
    repository_root: Path,
    workspace_tmp_path: Path,
) -> None:
    """Validate each advertised example through the complete generation path."""

    config_path = repository_root / "docs" / "examples" / filename
    project_dir = workspace_tmp_path / config_path.stem
    generate_deployment(
        config_path=config_path,
        compose_output=project_dir / "compose.yaml",
        project_dir=project_dir,
        ha_config_dir=project_dir / "homeassistant" / "config",
        runtime_image="local/labpulse:documentation-test",
    )

    assert (project_dir / "compose.yaml").is_file()
    assert (project_dir / "homeassistant" / "config" / "labpulse-dashboard.yaml").is_file()
