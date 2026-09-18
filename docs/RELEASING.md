# Releasing LabPulse

A release has two parts: the Python package installed on the Pi and the
container image used by its workers. They need matching versions. Don't ask
users to update until both have been published and checked.

This guide describes the [release workflow](../.github/workflows/release.yml)
in this checkout. Check that file when changing the release process. Publishing
requires access to the project's GitHub releases, package registry, and PyPI
publishing configuration; it isn't part of a normal contributor's test run.

The **wheel** (`.whl`) is the installable Python package; the **source
distribution** (`.tar.gz`, often called an sdist) contains the files needed to
build it. PyPI distributes those Python packages. GHCR, GitHub's container
registry, distributes the worker image. The release workflow builds and checks
both, but publication can still succeed for one and fail for the other.

## Quick guide: GitHub release to updated Pi

Use this for a normal stable release once the repository's publishing access
is configured. The sections below explain the checks and failure cases in
more detail.

### 1. Prepare the version

Commit and push the intended changes, merge them into `main`, and check that
**Actions → Test LabPulse** passes for the commit you intend to release. Update
[CHANGELOG](../CHANGELOG.md) with the changes, any required operator action,
and what was tested on a Pi.

Choose a version higher than the last release which has never been published.
For example, a small fix after `0.3.8` could be `0.3.9`, **if that version is
still unused**. This example does not identify the current next version.
The Git tag supplies the package version; don't edit a Python version constant.

### 2. Publish through GitHub

1. Open [LabPulse Releases](https://github.com/lairdgrouplancaster/LabPulse/releases)
   and select **Draft a new release**.
2. Under **Choose a tag**, enter your new tag, such as `v0.3.9`, and choose
   **Create new tag**. Set **Target** to `main` and verify it contains the
   reviewed commit. If choosing an existing tag, verify the commit it points to.
3. Give it a title such as `LabPulse 0.3.9`. Write short notes covering the
   changes, update instructions, tests, and known limitations. You can start
   with **Generate release notes**, then edit them for users.
4. For a normal stable release, leave **This is a pre-release** unchecked and
   select **Set as latest release**. Review, then select **Publish release**.

These are GitHub's [release creation steps](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).
A saved draft or a pushed tag alone does not trigger LabPulse publication.

### 3. Wait for publication

Open [Actions → Release LabPulse](https://github.com/lairdgrouplancaster/LabPulse/actions/workflows/release.yml)
and select the run for your tag. Wait for all three jobs to succeed:

- **Validate release artifacts**
- **Publish Python distributions to PyPI**
- **Publish multi-platform container**

If the `pypi` environment requires approval, an authorised maintainer must
approve the pending deployment. Confirm your exact version appears on
[PyPI](https://pypi.org/project/labpulse/#history) and as a full-version tag in
the [container package](https://github.com/lairdgrouplancaster/LabPulse/pkgs/container/labpulse).
The GitHub release page can exist before either artifact is ready. Wait for
both before updating a Pi. If a job fails, follow
[partial publication recovery](#if-publication-only-partly-succeeds).

### 4. Update a test Pi, then the live Pi

Use the same Pi user and live directory as the existing installation. Updates
restart services, so choose a suitable time for the live monitor. Record its
notification settings and use **Mute all notifications** if messages should
pause during maintenance.

In the Pi's terminal, run one command at a time:

```bash
labpulse version
mkdir -p ~/labpulse-backups
labpulse backup ~/labpulse-backups/before-update-$(date +%Y%m%d-%H%M%S).tar.gz
labpulse doctor
```

Resolve failures before continuing and review any warnings. Replace `X.Y.Z`
below with the published version, without the tag's leading `v`:

```bash
labpulse update X.Y.Z
labpulse version
labpulse ps --all
labpulse doctor
```

Update preserves the current real or fake-hardware mode and user configuration.
It installs the package, regenerates the deployment, and recreates the
containers. There is no need to uninstall first or run `git pull` on the Pi.
For a non-default directory, put `--live-dir /path/to/installation` before
each LabPulse command.

Check **System Status**, fresh readings, and the behaviour changed by this
release. Home Assistant starts with **Test mode** enabled; deliberately restore
the intended Test mode and mute settings after checking. Once the test Pi
passes, repeat the backup and update steps on the live Pi. See the
[operator update guide](USER_GUIDE.md#updating-labpulse) for recovery if anything
fails; an update does not automatically roll back a partially completed change.

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

Run the commands one at a time and stop at the first failure. A successful
build leaves a wheel and source archive in `dist/`; Twine should report that
their metadata checks passed. Neither result means anything has been published.

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

AMD64 is the architecture used by typical Intel/AMD computers; ARM64 is used
by the 64-bit Pi installation. Provenance records how an image was built, and
the SBOM (software bill of materials) lists its software components.

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
