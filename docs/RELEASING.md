# Releasing LabPulse

A release has two parts: the Python package installed on the Pi and the
container image used by its workers. They need matching versions. Don't ask
users to update until both have been published and checked.

This guide describes the [release workflow](../.github/workflows/release.yml)
in this checkout. Check that file when changing the release process. Publishing
requires access to the project's GitHub releases, package registry, and PyPI
publishing configuration; it isn't part of a normal contributor's test run.

## Prepare the candidate

1. Choose the commit and version, review the changes, and update
   [CHANGELOG](../CHANGELOG.md). Explain changed configuration or behaviour and
   any steps users need to take.
2. Confirm the ordinary CI matrix passes on Python 3.11 and 3.12. Run the
   relevant real-Pi checks and record the results, or explicitly record what
   remains unverified. A cross-platform image build is not a real-device test.
3. Check that new templates, scripts, and examples needed by installations are
   included through `pyproject.toml` and the packaging declarations. A file
   working in a checkout doesn't prove it is present in an installed wheel.
4. Build a candidate wheel and source distribution in a clean checkout. Use
   the [development-image workflow](DEVELOPMENT.md#host-code-and-runtime-images)
   for a local container test.

In the candidate's virtual environment:

```bash
python -m pip install build twine setuptools-scm
python -m pytest
python -m build
python -m twine check dist/*
```

These shell examples use Bash on Linux. Keep `dist/` limited to this candidate's
artifacts so wildcard commands don't accidentally check older builds too.

The version comes from Git tags through `setuptools-scm`, not a version string
you edit in Python. Before tagging, a development version is normal. At the
release tag, `python -m setuptools_scm` must match the tag with its leading
`v` removed.

## Check what users will install

Use two new virtual environments outside the checkout: install the built
wheel in one and the source distribution in the other. Run `labpulse help`
in each. Check that `find_install_assets()` can locate the packaged setup
files, and perform fake setup in a separate directory on the development
Linux host. The release workflow contains the exact smoke-install commands.

Build the container from the candidate wheel, confirm its installed version,
and run the hardware and SMS entry points with `--help`. Then check a running
simulated installation, including Home Assistant discovery and the behaviour
affected by the release. Keep all this separate from the live lab installation.

## Publish and watch both jobs

Confirm that PyPI's Trusted Publisher is configured for owner
`lairdgrouplancaster`, repository `LabPulse`, workflow `release.yml`, and
environment `pypi`. Check the GitHub environment permissions and GHCR package
access too. These account settings aren't established by passing local tests.

Create an unused `vVERSION` tag on the reviewed commit and publish its GitHub
release with the release notes. **Publishing the GitHub release triggers the
workflow; pushing a tag alone does not.** Never move or reuse a published tag.

The workflow runs three jobs:

| Job | What it does |
|---|---|
| `validate` | Checks the tag-derived version, runs tests, builds and checks wheel/sdist, smoke-installs them, performs fake setup, and smoke-tests a local image |
| `publish-python` | Publishes the validated Python artifacts to PyPI |
| `publish-container` | Builds and pushes AMD64 and ARM64 images to GHCR, with provenance and SBOM metadata |

Both publishing jobs depend on validation, but they don't depend on each
other. One can succeed while the other fails. The image receives a full-version
tag and a major.minor tag; the latter can move when a patch release is made.

Before announcing the release, confirm that the exact package version and
matching full-version image are available. Test installation or update of that
version on a development Pi, run Doctor, and check fresh readings. Record the
revision, host, configuration, and result with the release checks.

## If publication only partly succeeds

Read the failed job before taking action. If the problem is permissions or a
temporary registry failure, fix that and rerun only the failed job against the
same release. Check which artifacts already exist; don't attempt to replace a
published PyPI version or overwrite a released version with different code.

If the code, package contents, or version is wrong, make a corrected patch
release with a new tag. Explain the affected version and keep users from being
directed to a package whose matching worker image is missing. Don't describe a
green Python publication job as a successful complete release.

## Keep the status documents honest

Record released behaviour in the changelog, current usage in the guides, and
remaining work in the [roadmap](../ROADMAP.md). Preserve older hardware results
as evidence for their recorded revision, rather than silently extending them
to new hardware or new source. Update [screenshot.md](../screenshot.md) whenever
a visible change means a guide's capture needs refreshing.
