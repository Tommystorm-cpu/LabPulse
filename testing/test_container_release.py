"""Contract checks for versioned LabPulse container releases."""

from pathlib import Path
import sys
import tomllib


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

def require(source: str, fragment: str, label: str) -> None:
    """Raise when a release contract fragment is missing."""

    if fragment not in source:
        raise AssertionError(f"{label} is missing: {fragment}")


def main() -> None:
    """Validate image contents, build context, and automated release coupling."""

    metadata = tomllib.loads(
        (REPOSITORY / "pyproject.toml").read_text(encoding="utf-8")
    )
    project = metadata["project"]
    if "version" in project or "version" not in project.get("dynamic", []):
        raise AssertionError("release version must be dynamically derived")
    if "setuptools_scm" not in metadata.get("tool", {}):
        raise AssertionError("setuptools-scm release versioning is not enabled")

    dockerfile = (REPOSITORY / "Dockerfile").read_text(encoding="utf-8")
    for fragment, label in (
        ("FROM python:3.12-slim", "runtime base"),
        ("ARG LABPULSE_VERSION", "version build argument"),
        ("org.opencontainers.image.source", "repository label"),
        ("gpiod", "GPIO system dependency"),
        ("modemmanager", "SMS system dependency"),
        ("labpulse[serial,x1200,dht11]", "hardware dependency extras"),
        ("dist/labpulse-${LABPULSE_VERSION}-py3-none-any.whl", "release wheel"),
    ):
        require(dockerfile, fragment, label)
    if "ARG LABPULSE_VERSION=" in dockerfile:
        raise AssertionError("Dockerfile permits an implicit stale release version")
    if "COPY src" in dockerfile or "COPY labpulse" in dockerfile:
        raise AssertionError("runtime image copies source instead of the release wheel")

    dockerignore = (REPOSITORY / ".dockerignore").read_text(encoding="utf-8")
    for fragment in ("*", "!Dockerfile", "!dist/labpulse-*.whl"):
        require(dockerignore, fragment, "minimal Docker build context")

    workflow = (
        REPOSITORY / ".github" / "workflows" / "release.yml"
    ).read_text(encoding="utf-8")
    for fragment, label in (
        ("release:", "release trigger"),
        ("fetch-depth: 0", "complete Git tag history"),
        ("ref: ${{ github.event.release.tag_name }}", "release-tag checkout"),
        ('scm_version="$(python -m setuptools_scm)"', "SCM version resolution"),
        (
            'if [ "$scm_version" != "$version" ]; then',
            "release-tag version validation",
        ),
        (
            "Release tag determines package version",
            "successful version-check path",
        ),
        ("python -m build", "distribution build"),
        ("python -m twine check", "distribution metadata validation"),
        ('setup --fake-usb', "installed-wheel setup smoke test"),
        ('test ! -d "$RUNNER_TEMP/labpulse-live/labpulse-python"', "source-copy rejection"),
        ("pypa/gh-action-pypi-publish", "trusted package publication"),
        ("name: testpypi", "TestPyPI publishing environment"),
        (
            "repository-url: https://test.pypi.org/legacy/",
            "TestPyPI upload endpoint",
        ),
        ("packages: write", "GHCR permission"),
        ("linux/amd64,linux/arm64", "multi-platform targets"),
        ("ghcr.io/tommystorm-cpu/labpulse", "runtime image repository"),
        ("LABPULSE_VERSION=${{ needs.validate.outputs.version }}", "image version"),
        ("subject-digest: ${{ steps.image.outputs.digest }}", "image attestation"),
    ):
        require(workflow, fragment, label)
    if '["project"]["version"]' in workflow:
        raise AssertionError("workflow still reads a hard-coded package version")

    print("[PASS] Dockerfile installs the versioned release wheel")
    print("[PASS] Docker build context excludes repository-only content")
    print("[PASS] release workflow couples TestPyPI and GHCR versions")
    print("[PASS] release workflow publishes AMD64 and ARM64 images")


if __name__ == "__main__":
    main()
