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

def _maintained_markdown_files(repository_root: Path) -> tuple[Path, ...]:
    """Return current guides while excluding historical and generated trees."""

    root_guides = (
        repository_root / "README.md",
        repository_root / "CHANGELOG.md",
        repository_root / "CONTRIBUTING.md",
        repository_root / "ROADMAP.md",
        repository_root / "SECURITY.md",
    )
    readmes = tuple(repository_root / path for path in sorted(README_PATHS - {"README.md"}))
    return (*root_guides, *readmes, *sorted((repository_root / "docs").glob("*.md")))


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
