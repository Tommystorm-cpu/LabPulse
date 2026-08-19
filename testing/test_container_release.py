"""Contract checks for versioned LabPulse container releases."""

from pathlib import Path
import tomllib

import pytest


REPOSITORY = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    """Read one repository contract file."""

    return (REPOSITORY / path).read_text(encoding="utf-8")


def test_release_version_is_tag_derived() -> None:
    """Require package and image releases to derive one immutable version."""

    metadata = tomllib.loads(source("pyproject.toml"))
    project = metadata["project"]
    assert "version" not in project
    assert "version" in project.get("dynamic", [])
    assert "setuptools_scm" in metadata.get("tool", {})


@pytest.mark.parametrize(
    ("fragment", "label"),
    (
        ("FROM python:3.12-slim", "runtime base"),
        ("ARG LABPULSE_VERSION", "version build argument"),
        ("org.opencontainers.image.source", "repository label"),
        ("gpiod", "GPIO system dependency"),
        ("modemmanager", "SMS system dependency"),
        ("labpulse[serial,x1200,dht11]", "hardware dependency extras"),
        ("dist/labpulse-${LABPULSE_VERSION}-py3-none-any.whl", "release wheel"),
    ),
)
def test_dockerfile_contains_release_contract(fragment: str, label: str) -> None:
    """Require one versioned runtime-image contract fragment."""

    assert fragment in source("Dockerfile"), f"{label} is missing: {fragment}"


def test_dockerfile_installs_only_the_release_wheel() -> None:
    """Reject implicit versions and source copies in the runtime image."""

    dockerfile = source("Dockerfile")
    assert "ARG LABPULSE_VERSION=" not in dockerfile
    assert "COPY src" not in dockerfile
    assert "COPY labpulse" not in dockerfile


@pytest.mark.parametrize("fragment", ("*", "!Dockerfile", "!dist/labpulse-*.whl"))
def test_docker_build_context_is_minimal(fragment: str) -> None:
    """Include only the Dockerfile and built wheel in the image context."""

    assert fragment in source(".dockerignore")


@pytest.mark.parametrize(
    ("fragment", "label"),
    (
        ("release:", "release trigger"),
        ("fetch-depth: 0", "complete Git tag history"),
        ("ref: ${{ github.event.release.tag_name }}", "release-tag checkout"),
        ('scm_version="$(python -m setuptools_scm)"', "SCM version resolution"),
        ('if [ "$scm_version" != "$version" ]; then', "tag validation"),
        ("Release tag determines package version", "successful version check"),
        ("python -m build", "distribution build"),
        ("python -m twine check", "metadata validation"),
        ("setup --fake-usb", "installed-wheel setup smoke test"),
        ('test ! -d "$RUNNER_TEMP/labpulse-live/labpulse-python"', "source-copy rejection"),
        ("pypa/gh-action-pypi-publish", "trusted package publication"),
        ("name: testpypi", "TestPyPI environment"),
        ("repository-url: https://test.pypi.org/legacy/", "TestPyPI endpoint"),
        ("packages: write", "GHCR permission"),
        ("linux/amd64,linux/arm64", "multi-platform targets"),
        ("ghcr.io/tommystorm-cpu/labpulse", "runtime image repository"),
        ("LABPULSE_VERSION=${{ needs.validate.outputs.version }}", "image version"),
        ("subject-digest: ${{ steps.image.outputs.digest }}", "image attestation"),
    ),
)
def test_release_workflow_contains_distribution_contract(
    fragment: str,
    label: str,
) -> None:
    """Require one package/container release workflow contract fragment."""

    workflow = source(".github/workflows/release.yml")
    assert fragment in workflow, f"{label} is missing: {fragment}"


def test_release_workflow_has_no_hard_coded_project_version() -> None:
    """Reject obsolete workflow reads of a static project version."""

    assert '["project"]["version"]' not in source(".github/workflows/release.yml")


@pytest.mark.parametrize(
    "fragment",
    (
        "pull_request:",
        'python-version: ["3.11", "3.12"]',
        'python -m pip install --editable ".[dev]"',
        "python -m pytest",
    ),
)
def test_pull_request_workflow_runs_the_supported_test_matrix(fragment: str) -> None:
    """Keep pull-request validation aligned with local pytest commands."""

    assert fragment in source(".github/workflows/test.yml")
