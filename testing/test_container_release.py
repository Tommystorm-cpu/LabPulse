"""Small public-contract checks for versioned container releases."""

from pathlib import Path
import tomllib


REPOSITORY = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    """Read one repository release file."""

    return (REPOSITORY / path).read_text(encoding="utf-8")


def test_release_version_is_tag_derived() -> None:
    """Require package and image releases to derive one immutable version."""

    metadata = tomllib.loads(source("pyproject.toml"))
    project = metadata["project"]
    assert "version" not in project
    assert "version" in project.get("dynamic", [])
    assert "setuptools_scm" in metadata.get("tool", {})


def test_runtime_image_uses_the_versioned_distribution() -> None:
    """Build the runtime from one selected wheel without copying source code."""

    dockerfile = source("Dockerfile")
    copy_instructions = [
        line.strip() for line in dockerfile.splitlines() if line.startswith("COPY ")
    ]

    assert dockerfile.startswith("FROM python:3.12-slim\n")
    assert "ARG LABPULSE_VERSION\n" in dockerfile
    assert copy_instructions == [
        "COPY dist/labpulse-${LABPULSE_VERSION}-py3-none-any.whl /tmp/"
    ]
    assert '"labpulse[serial,i2c,gpio] @ file:///tmp/labpulse-${LABPULSE_VERSION}-py3-none-any.whl"' in dockerfile


def test_container_build_context_contains_only_release_inputs() -> None:
    """Keep unrelated source and local state outside the container build context."""

    rules = {
        line.strip()
        for line in source(".dockerignore").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert rules == {"*", "!Dockerfile", "!dist/", "!dist/labpulse-*.whl"}


def test_release_workflow_validates_and_publishes_both_artifact_types() -> None:
    """Retain the release outcomes without pinning every workflow step."""

    workflow = source(".github/workflows/release.yml")
    assert "release:" in workflow
    assert "python -m pytest" in workflow
    assert "python -m build" in workflow
    assert "python -m twine check" in workflow
    assert "pypa/gh-action-pypi-publish" in workflow
    assert "docker/build-push-action" in workflow
    assert "linux/amd64,linux/arm64" in workflow
    assert "LABPULSE_VERSION=${{ needs.validate.outputs.version }}" in workflow
