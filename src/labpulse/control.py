"""Operator commands for the installed LabPulse Docker deployment."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as distribution_version
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import webbrowser

from packaging.version import InvalidVersion, Version

from labpulse import __version__
from labpulse.backup import (
    BackupError,
    create_backup,
    inspect_backup,
    restore_backup,
    running_services,
    start_services,
    stop_services,
)
from labpulse.installer import find_install_assets, main as installer_main
from labpulse.doctor import run_doctor


DEFAULT_LIVE_DIR = Path("~/labpulse-live")
HOME_ASSISTANT_URL = "http://localhost:8123"
FIRMWARE_SOURCE_URL = "https://github.com/lairdgrouplancaster/LabPulse/tree/main/firmware"
FIRMWARE_ARCHIVE_URL = "https://github.com/lairdgrouplancaster/LabPulse/archive/refs/heads/main.zip"
TEST_PYPI_INDEX_URL = "https://test.pypi.org/simple/"
PYPI_INDEX_URL = "https://pypi.org/simple/"
TEST_PYPI_PROJECT_URL = "https://test.pypi.org/pypi/labpulse/json"
UPDATE_CHECK_TIMEOUT_SECONDS = 2.0
UPDATE_CHECK_CACHE_SECONDS = 6 * 60 * 60
UPDATE_CHECK_FAILURE_CACHE_SECONDS = 10 * 60
FIRMWARE_HELP = f"""\
LabPulse firmware is currently distributed through the project repository.

Browse the firmware:
  {FIRMWARE_SOURCE_URL}

Download the complete repository ZIP:
  {FIRMWARE_ARCHIVE_URL}

After extracting the ZIP, open the firmware/ directory. It contains the
reusable Arduino library, example sketches, and firmware documentation.

Automatic version-matched firmware downloads are planned for a future release.
"""


def live_directory(override: str | None = None) -> Path:
    """Return the configured live deployment directory."""

    configured = override or os.environ.get("LABPULSE_LIVE_DIR")
    return Path(configured or DEFAULT_LIVE_DIR).expanduser().resolve()


def docker_command() -> list[str]:
    """Return the Docker command prefix used for operator actions.

    ``sudo docker`` matches the Raspberry Pi installation documentation. Root
    users run Docker directly. Advanced installations can set
    ``LABPULSE_DOCKER_COMMAND`` (for example, to ``docker`` when their account
    belongs to the Docker group).
    """

    configured = os.environ.get("LABPULSE_DOCKER_COMMAND")
    if configured:
        command = shlex.split(configured)
        if not command:
            raise ValueError("LABPULSE_DOCKER_COMMAND cannot be empty")
        return command

    get_effective_user = getattr(os, "geteuid", None)
    if get_effective_user is not None and get_effective_user() == 0:
        return ["docker"]
    if shutil.which("sudo"):
        return ["sudo", "docker"]
    return ["docker"]


def run_compose(live_dir: Path, arguments: Sequence[str]) -> int:
    """Run one Docker Compose operation from the live deployment directory."""

    compose_path = live_dir / "compose.yaml"
    if not compose_path.is_file():
        print(
            f"ERROR: LabPulse is not set up at {live_dir} "
            f"(missing {compose_path.name}). Run 'labpulse setup' first.",
            file=sys.stderr,
        )
        return 2

    try:
        command = [*docker_command(), "compose", *arguments]
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    try:
        return subprocess.run(command, cwd=live_dir, check=False).returncode
    except FileNotFoundError as error:
        print(
            f"ERROR: Cannot run {error.filename!r}. "
            "Install Docker or correct LABPULSE_DOCKER_COMMAND.",
            file=sys.stderr,
        )
        return 127


def run_config_editor(live_dir: Path, source_files: Sequence[str] = ()) -> int:
    """Run the packaged guarded config editor against the live deployment."""

    if not (live_dir / "config.yaml").is_file():
        print(
            f"ERROR: LabPulse is not set up at {live_dir} "
            "(missing config.yaml). Run 'labpulse setup' first.",
            file=sys.stderr,
        )
        return 2

    selected_files = tuple(source_files)
    if not selected_files:
        selection = select_config_sources(live_dir)
        if selection is None:
            print("Configuration edit cancelled.")
            return 0
        selected_files = selection

    bash = shutil.which("bash")
    if bash is None:
        print(
            "ERROR: labpulse config requires Bash and is supported on "
            "Raspberry Pi OS/Linux.",
            file=sys.stderr,
        )
        return 127

    try:
        edit_script = find_install_assets() / "deployment" / "edit_config.sh"
    except FileNotFoundError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment["LABPULSE_LIVE_DIR"] = str(live_dir)
    try:
        environment["LABPULSE_DOCKER_COMMAND"] = shlex.join(docker_command())
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    try:
        return subprocess.run(
            [bash, str(edit_script), *selected_files],
            cwd=live_dir,
            env=environment,
            check=False,
        ).returncode
    except FileNotFoundError as error:
        print(f"ERROR: Cannot run {error.filename!r}.", file=sys.stderr)
        return 127


def select_config_sources(live_dir: Path) -> tuple[str, ...] | None:
    """Ask which source config to edit or create beneath ``config.d``."""

    config_dir = live_dir / "config.d"
    fragments = (
        sorted(
            path.relative_to(live_dir).as_posix()
            for path in config_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}
        )
        if config_dir.is_dir()
        else []
    )
    choices = ["config.yaml", *fragments]

    while True:
        print("Which configuration file do you want to edit?")
        for number, path in enumerate(choices, start=1):
            print(f"  {number}. {path}")
        print(f"  {len(choices) + 1}. Create a new measurement config")
        print("  q. Cancel")
        try:
            answer = input("Selection: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if answer.lower() == "q":
            return None
        try:
            selected = int(answer)
        except ValueError:
            print("Enter a listed number or q.")
            continue
        if 1 <= selected <= len(choices):
            return (choices[selected - 1],)
        if selected != len(choices) + 1:
            print("Enter a listed number or q.")
            continue

        try:
            name = input("New measurement config name: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if name.startswith("config.d/"):
            name = name[len("config.d/"):]
        relative = Path(name)
        if not name or relative.is_absolute() or "\\" in name or ".." in relative.parts:
            print("Use a relative filename beneath config.d.")
            continue
        if relative.suffix == "":
            relative = relative.with_suffix(".yaml")
        if relative.suffix.lower() not in {".yaml", ".yml"}:
            print("The filename must end in .yaml or .yml.")
            continue
        target = config_dir / relative
        if target.exists():
            print(f"{target.relative_to(live_dir).as_posix()} already exists; select it from the list.")
            continue
        return ("config.yaml", f"config.d/{relative.as_posix()}")


def open_homeassistant() -> int:
    """Open the local Home Assistant interface in the default browser."""

    print(f"Opening Home Assistant: {HOME_ASSISTANT_URL}")
    if webbrowser.open(HOME_ASSISTANT_URL, new=2):
        return 0
    print(
        "ERROR: No graphical browser could be opened. "
        f"Open {HOME_ASSISTANT_URL} manually.",
        file=sys.stderr,
    )
    return 1


def show_firmware_help() -> int:
    """Explain where the current LabPulse firmware can be downloaded."""

    print(FIRMWARE_HELP)
    return 0


def run_backup_command(live_dir: Path, output: Path, *, force: bool) -> int:
    """Create a consistent private archive of user-owned runtime state."""

    try:
        archive_path = create_backup(live_dir, output, docker_command(), force=force)
    except (BackupError, OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Backup created: {archive_path}")
    print("This archive contains credentials, tokens, and phone-number state.")
    print("Store it with the same care as a password.")
    return 0


def run_uninstall_command(live_dir: Path, *, assume_yes: bool) -> int:
    """Remove one LabPulse deployment and its Docker resources."""

    if not live_dir.is_dir():
        print(f"ERROR: LabPulse is not installed at {live_dir}.", file=sys.stderr)
        return 2
    filesystem_root = Path(live_dir.anchor).resolve()
    home = Path.home().resolve()
    if live_dir in {filesystem_root, home}:
        print(f"ERROR: Refusing to remove unsafe installation path: {live_dir}", file=sys.stderr)
        return 2

    if not assume_yes:
        print(f"LabPulse installation: {live_dir}")
        print("This permanently removes its configuration, Home Assistant data, logs, backups, and Docker resources.")
        if input("Type UNINSTALL to continue: ").strip() != "UNINSTALL":
            print("Uninstall cancelled; no changes were made.")
            return 2

    if (live_dir / "compose.yaml").is_file():
        result = run_compose(live_dir, ("down", "--remove-orphans", "--volumes"))
        if result != 0:
            print(
                "ERROR: Docker cleanup failed; the installation directory was not removed.",
                file=sys.stderr,
            )
            return result

    try:
        shutil.rmtree(live_dir)
    except OSError as error:
        print(f"ERROR: Could not remove LabPulse installation: {error}", file=sys.stderr)
        return 1

    try:
        cache_path = update_check_cache_path()
        cache_path.unlink(missing_ok=True)
        try:
            cache_path.parent.rmdir()
        except OSError:
            pass
    except OSError as error:
        print(f"WARNING: Deployment was removed, but its update cache could not be removed: {error}", file=sys.stderr)

    print(f"Removed LabPulse deployment: {live_dir}")
    print("The pipx-installed labpulse command remains available. Remove it with 'pipx uninstall labpulse' if required.")
    return 0


def _homeassistant_http_ready(timeout: float = 2.0) -> bool:
    """Return whether Home Assistant is serving a non-error HTTP response."""

    request = Request(
        "http://127.0.0.1:8123/",
        headers={"User-Agent": f"LabPulse/{__version__} readiness probe"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status < 500
    except HTTPError as error:
        # An authentication or routing response still proves that Home
        # Assistant's HTTP server is running. Server errors do not.
        return error.code < 500
    except (OSError, TimeoutError, URLError):
        return False


def _wait_for_homeassistant(
    timeout: float = 120.0,
    *,
    stable_for: float = 10.0,
    poll_interval: float = 2.0,
) -> bool:
    """Wait until Home Assistant serves HTTP continuously for a stable period."""

    deadline = time.monotonic() + timeout
    ready_since: float | None = None
    while time.monotonic() < deadline:
        if _homeassistant_http_ready():
            checked_at = time.monotonic()
            if ready_since is None:
                ready_since = checked_at
            elif checked_at - ready_since >= stable_for:
                return True
        else:
            # Home Assistant may briefly bind its port and then restart while
            # loading configuration. Any failed probe restarts the stability
            # window so final diagnostics cannot run during that gap.
            ready_since = None

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval, remaining))
    return False


def run_restore_command(
    live_dir: Path,
    archive: Path,
    *,
    assume_yes: bool,
) -> int:
    """Restore, regenerate, start, and diagnose one LabPulse installation."""

    archive = archive.expanduser().resolve()
    try:
        manifest = inspect_backup(archive)
    except BackupError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if not assume_yes:
        print(f"Restore archive: {archive}")
        print(f"Target installation: {live_dir}")
        print("Current LabPulse state will be replaced after a rollback archive is made.")
        if input("Type RESTORE to continue: ").strip() != "RESTORE":
            print("Restore cancelled; no files were changed.")
            return 2

    # A restore may target an empty machine. Build the normal live directory
    # first so the restored state has the same structure as a fresh install.
    had_user_state = (live_dir / "config.yaml").exists() or (live_dir / "homeassistant" / "config").exists()
    if not (live_dir / "compose.yaml").is_file():
        if run_setup(str(live_dir), fake_usb=manifest.get("runtime_mode") == "fake_usb", backup=True) != 0:
            print("ERROR: Could not scaffold the restore target.", file=sys.stderr)
            return 1

    # Stop only the services that are currently running. Their names are kept
    # so a failed restore can return the installation to its previous state.
    try:
        docker_prefix = docker_command()
        active_services = running_services(live_dir, docker_prefix)
        stop_services(live_dir, docker_prefix, active_services)
    except (BackupError, ValueError) as error:
        print(f"ERROR: Could not quiesce the current installation: {error}", file=sys.stderr)
        return 1

    rollback_path: Path | None = None
    restored = False
    try:
        # The user's current state gets its own full archive before it is
        # replaced, even though the incoming archive has already been checked.
        if had_user_state:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            rollback_path = live_dir.parent / f"labpulse-pre-restore-{timestamp}.tar.gz"
            create_backup(live_dir, rollback_path, docker_prefix, quiesce=False)
            print(f"Pre-restore rollback archive: {rollback_path}")

        restore_backup(live_dir, archive)
        restored = True
        # Restored config is the source of truth. Recreate generated files from
        # it instead of trusting potentially stale generated files in a backup.
        if run_setup(str(live_dir), fake_usb=manifest.get("runtime_mode") == "fake_usb", backup=True) != 0:
            raise BackupError("setup/regeneration failed after restoring state")
        if run_compose(live_dir, ("up", "-d", "--pull", "missing")) != 0:
            raise BackupError("versioned Compose stack did not start")
    except (BackupError, OSError) as error:
        print(f"ERROR: Restore did not complete: {error}", file=sys.stderr)
        if restored and rollback_path is not None:
            print("Restoring the automatic rollback snapshot...", file=sys.stderr)
            try:
                rollback_manifest = restore_backup(live_dir, rollback_path)
                if run_setup(
                    str(live_dir),
                    fake_usb=rollback_manifest.get("runtime_mode") == "fake_usb",
                    backup=True,
                ) != 0:
                    raise BackupError("setup/regeneration failed during rollback")
            except (BackupError, OSError) as rollback_error:
                print(
                    f"ERROR: Automatic rollback also failed: {rollback_error}",
                    file=sys.stderr,
                )
        try:
            start_services(live_dir, docker_prefix, active_services)
        except BackupError as start_error:
            print(f"ERROR: Could not restart prior services: {start_error}", file=sys.stderr)
        return 1

    print("State restored and the versioned stack was started.")
    print("Waiting for Home Assistant before final diagnostics...")
    if not _wait_for_homeassistant():
        print(
            "ERROR: Restore succeeded, but Home Assistant did not become ready "
            "within 120 seconds. Inspect its logs.",
            file=sys.stderr,
        )
        return 1
    doctor_result = run_doctor(live_dir, docker_prefix, timeout=5.0)
    if doctor_result != 0:
        print(
            "ERROR: Restore succeeded, but final diagnostics reported failures.",
            file=sys.stderr,
        )
        return doctor_result
    print("Restore and post-restore diagnostics completed successfully.")
    print("Review timezone, watchdog, Docker-group, modem, and physical wiring settings.")
    return 0


def run_setup(
    live_dir_override: str | None,
    *,
    fake_usb: bool,
    backup: bool,
) -> int:
    """Run the packaged installer through the unified command interface."""

    installer_arguments: list[str] = []
    if fake_usb:
        installer_arguments.append("--fake-usb")
    if backup:
        installer_arguments.append("--backup")

    previous_setup_command = os.environ.get("LABPULSE_SETUP_COMMAND")
    previous_live_dir = os.environ.get("LABPULSE_LIVE_DIR")
    # The shell installer reads these environment variables. Restore their old
    # values in finally so calling setup cannot alter later commands in this
    # Python process.
    os.environ["LABPULSE_SETUP_COMMAND"] = "labpulse setup"
    if live_dir_override is not None:
        os.environ["LABPULSE_LIVE_DIR"] = str(live_directory(live_dir_override))
    try:
        return installer_main(installer_arguments)
    finally:
        if previous_setup_command is None:
            os.environ.pop("LABPULSE_SETUP_COMMAND", None)
        else:
            os.environ["LABPULSE_SETUP_COMMAND"] = previous_setup_command
        if live_dir_override is not None:
            if previous_live_dir is None:
                os.environ.pop("LABPULSE_LIVE_DIR", None)
            else:
                os.environ["LABPULSE_LIVE_DIR"] = previous_live_dir


def latest_published_version(*, timeout: float = 15.0) -> str:
    """Return the latest LabPulse version reported by TestPyPI."""

    request = Request(
        TEST_PYPI_PROJECT_URL,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": f"LabPulse/{__version__}",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except (OSError, URLError, json.JSONDecodeError) as error:
        raise RuntimeError(f"could not check TestPyPI: {error}") from error

    info = payload.get("info") if isinstance(payload, dict) else None
    version = info.get("version") if isinstance(info, dict) else None
    if not isinstance(version, str) or not version.strip():
        raise RuntimeError("TestPyPI returned no latest LabPulse version")
    return version.strip()


def update_check_cache_path() -> Path:
    """Return the per-user cache file used by post-command version checks."""

    configured_root = os.environ.get("XDG_CACHE_HOME")
    cache_root = Path(configured_root).expanduser() if configured_root else Path.home() / ".cache"
    return cache_root / "labpulse" / "version-check.json"


def read_update_check_cache(cache_path: Path) -> tuple[bool, str | None]:
    """Return whether a fresh cached check exists and its published version."""

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        checked_at = float(payload["checked_at"])
        latest = payload.get("latest")
        if latest is not None and not isinstance(latest, str):
            return False, None
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False, None

    maximum_age = (
        UPDATE_CHECK_CACHE_SECONDS if latest is not None else UPDATE_CHECK_FAILURE_CACHE_SECONDS
    )
    age = time.time() - checked_at
    return (True, latest) if 0 <= age < maximum_age else (False, None)


def write_update_check_cache(cache_path: Path, latest: str | None) -> None:
    """Best-effort persist a successful or failed remote version check."""

    temporary_path = cache_path.with_suffix(".tmp")
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            json.dumps({"checked_at": time.time(), "latest": latest}) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(cache_path)
    except OSError:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def notify_if_update_available(
    *, force_refresh: bool = False, cache_path: Path | None = None
) -> None:
    """Print a cached, best-effort notice when a newer release exists."""

    selected_cache_path = cache_path or update_check_cache_path()
    cache_is_fresh, latest = read_update_check_cache(selected_cache_path)
    try:
        if force_refresh or not cache_is_fresh:
            latest = latest_published_version(timeout=UPDATE_CHECK_TIMEOUT_SECONDS)
            write_update_check_cache(selected_cache_path, latest)
        if latest is None:
            return
        try:
            installed = distribution_version("labpulse")
        except PackageNotFoundError:
            installed = __version__
        installed_version = Version(installed)
        latest_version = Version(latest)
    except (RuntimeError, InvalidVersion):
        write_update_check_cache(selected_cache_path, None)
        return

    if latest_version > installed_version:
        print(
            f"\nA newer LabPulse version is available: {latest} "
            f"(installed: {installed}). Run 'labpulse update'."
        )




def run_update_command(live_dir: Path, requested_version: str | None) -> int:
    """Install one release, regenerate the deployment, and recreate the stack."""

    compose_path = live_dir / "compose.yaml"
    config_path = live_dir / "config.yaml"
    if not compose_path.is_file() or not config_path.is_file():
        print(
            f"ERROR: LabPulse is not set up at {live_dir}. "
            "Run 'labpulse setup' first.",
            file=sys.stderr,
        )
        return 2

    try:
        target_version = requested_version or latest_published_version()
        if requested_version is None and target_version == __version__:
            # TestPyPI metadata can briefly differ between cache edges just
            # after a release. Recheck before declaring the installation current.
            target_version = latest_published_version()
        compose_text = compose_path.read_text(encoding="utf-8")
    except (OSError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if target_version == __version__:
        print(f"LabPulse {__version__} is already the latest requested version.")
        return 0

    pipx = shutil.which("pipx")
    fresh_labpulse = shutil.which("labpulse")
    if pipx is None:
        print("ERROR: Cannot update because pipx is not on PATH.", file=sys.stderr)
        return 127
    if fresh_labpulse is None:
        print(
            "ERROR: Cannot locate the pipx-installed labpulse command on PATH.",
            file=sys.stderr,
        )
        return 127

    fake_usb = "config.fake.yaml:/app/config.yaml" in compose_text
    print(f"Updating LabPulse {__version__} -> {target_version}...")
    install_command = [
        pipx,
        "install",
        "--force",
        "--index-url",
        TEST_PYPI_INDEX_URL,
        f"--pip-args=--no-cache-dir --extra-index-url {PYPI_INDEX_URL}",
        f"labpulse=={target_version}",
    ]
    try:
        install_result = subprocess.run(install_command, check=False).returncode
    except FileNotFoundError as error:
        print(f"ERROR: Cannot run {error.filename!r}.", file=sys.stderr)
        return 127
    if install_result != 0:
        print("ERROR: pipx could not install the requested release.", file=sys.stderr)
        return install_result

    # The current Python process still contains the old package. Run setup via
    # the replaced entry point so all generated files come from the new release.
    setup_command = [
        fresh_labpulse,
        "--live-dir",
        str(live_dir),
        "setup",
        "--backup",
    ]
    if fake_usb:
        setup_command.append("--fake-usb")
    try:
        setup_result = subprocess.run(setup_command, check=False).returncode
    except FileNotFoundError as error:
        print(f"ERROR: Cannot run updated command {error.filename!r}.", file=sys.stderr)
        return 127
    if setup_result != 0:
        print(
            "ERROR: The package was updated, but setup failed. "
            "The existing containers were not deliberately recreated.",
            file=sys.stderr,
        )
        return setup_result

    # Recreate the generated stack as one Compose operation. Confirmed outages
    # during the update use the same notification policy as any other outage.
    recreate_result = run_compose(
        live_dir,
        ("up", "-d", "--pull", "missing", "--remove-orphans", "--force-recreate"),
    )
    if recreate_result != 0:
        print(
            "ERROR: Generated files were updated, but the stack could not be recreated.",
            file=sys.stderr,
        )
        return recreate_result

    print("Waiting for Home Assistant before final diagnostics...")
    if not _wait_for_homeassistant():
        print(
            "ERROR: The update completed, but Home Assistant did not become ready "
            "within 120 seconds. Inspect its logs.",
            file=sys.stderr,
        )
        return 1

    try:
        doctor_result = subprocess.run(
            [fresh_labpulse, "--live-dir", str(live_dir), "doctor", "--timeout", "5"],
            check=False,
        ).returncode
    except FileNotFoundError as error:
        print(f"ERROR: Cannot run updated command {error.filename!r}.", file=sys.stderr)
        return 127
    if doctor_result != 0:
        print(
            "ERROR: The update completed, but final diagnostics reported failures.",
            file=sys.stderr,
        )
        return doctor_result

    print(f"LabPulse {target_version} is installed and all containers were recreated.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the operator command-line parser."""

    parser = argparse.ArgumentParser(prog="labpulse", description="Control the installed LabPulse Docker deployment.")
    parser.add_argument("--live-dir", metavar="DIR", help="live deployment directory (default: ~/labpulse-live)")
    commands = parser.add_subparsers(dest="action", required=True)

    setup_parser = commands.add_parser("setup", help="create or refresh the live LabPulse installation")
    setup_parser.add_argument(
        "-fake_usb",
        "--fake-usb",
        "--fake_usb",
        dest="fake_usb",
        action="store_true",
        help="configure simulated USB serial hardware",
    )
    setup_parser.add_argument(
        "--backup",
        action="store_true",
        help="keep one rolling backup of each replaced package-managed file in backups/",
    )

    update_parser = commands.add_parser(
        "update",
        help="install a newer release, refresh setup, and recreate the stack",
    )
    update_parser.add_argument(
        "version",
        nargs="?",
        help="release to install (default: latest version published on TestPyPI)",
    )

    up_parser = commands.add_parser("up", help="start the stack or selected services in the background")
    up_parser.add_argument("services", nargs="*", help="optional service names")

    down_parser = commands.add_parser("down", help="stop and remove containers without deleting persistent data")
    down_parser.add_argument("services", nargs="*", help="optional service names")

    restart_parser = commands.add_parser("restart", help="restart the stack or selected services")
    restart_parser.add_argument("services", nargs="*", help="optional service names")

    backup_parser = commands.add_parser("backup", help="create a checksummed archive of user-owned LabPulse state")
    backup_parser.add_argument("output", help="output .tar.gz archive path")
    backup_parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing archive path",
    )

    restore_parser = commands.add_parser(
        "restore", help="restore, regenerate, start, and diagnose a LabPulse state archive"
    )
    restore_parser.add_argument("archive", help="LabPulse backup archive path")
    restore_parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm replacement without the interactive RESTORE prompt",
    )

    uninstall_parser = commands.add_parser(
        "uninstall",
        help="remove the live deployment and its Docker resources",
    )
    uninstall_parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm permanent removal without the interactive UNINSTALL prompt",
    )

    ps_parser = commands.add_parser("ps", help="show LabPulse container status")
    ps_parser.add_argument(
        "-a", "--all", action="store_true", help="include stopped containers"
    )

    logs_parser = commands.add_parser("logs", help="show container logs")
    logs_parser.add_argument(
        "-f", "--follow", action="store_true", help="continue following new output"
    )
    logs_parser.add_argument(
        "--tail",
        metavar="LINES",
        help="number of lines to show from the end of each log",
    )
    logs_parser.add_argument(
        "-t", "--timestamps", action="store_true", help="show timestamps"
    )
    logs_parser.add_argument("services", nargs="*", help="optional service names")

    config_parser = commands.add_parser(
        "config",
        help="edit, validate, regenerate, and safely apply the configuration source bundle",
    )
    config_parser.add_argument(
        "source_files",
        nargs="*",
        metavar="FILE",
        help="config.yaml or YAML files beneath config.d (default: interactive selection)",
    )
    commands.add_parser("open", help="open Home Assistant at http://localhost:8123")
    doctor_parser = commands.add_parser(
        "doctor",
        help="diagnose the installation, hardware access, and running services",
    )
    doctor_parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="timeout for local MQTT and Home Assistant probes (default: 1)",
    )

    commands.add_parser(
        "firmware",
        help="show where to download LabPulse firmware",
        description=FIRMWARE_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands.add_parser("version", help="show the installed LabPulse version")

    help_topics = tuple(commands.choices)
    help_parser = commands.add_parser("help", help="show general help or help for one command")
    help_parser.add_argument(
        "topic",
        nargs="?",
        choices=help_topics,
        help="command to explain",
    )
    help_parser.set_defaults(help_root_parser=parser, help_command_parsers=commands.choices)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the LabPulse operator command."""

    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.action == "help":
            help_parser = (
                arguments.help_command_parsers.get(arguments.topic)
                if arguments.topic
                else arguments.help_root_parser
            )
            help_parser.print_help()
            return 0
        if arguments.action == "firmware":
            return show_firmware_help()
        if arguments.action == "version":
            print(f"LabPulse {__version__}")
            return 0
        if arguments.action == "setup":
            return run_setup(
                arguments.live_dir,
                fake_usb=arguments.fake_usb,
                backup=arguments.backup,
            )
        if arguments.action == "open":
            return open_homeassistant()

        live_dir = live_directory(arguments.live_dir)
        if arguments.action == "update":
            return run_update_command(live_dir, arguments.version)
        if arguments.action == "backup":
            return run_backup_command(
                live_dir, Path(arguments.output), force=arguments.force
            )
        if arguments.action == "restore":
            return run_restore_command(
                live_dir, Path(arguments.archive), assume_yes=arguments.yes
            )
        if arguments.action == "uninstall":
            return run_uninstall_command(live_dir, assume_yes=arguments.yes)
        if arguments.action == "config":
            return run_config_editor(live_dir, arguments.source_files)
        if arguments.action == "doctor":
            if arguments.timeout <= 0:
                parser.error("doctor --timeout must be greater than zero")
            try:
                docker_prefix = docker_command()
            except ValueError as error:
                print(f"WARNING: {error}", file=sys.stderr)
                docker_prefix = None
            return run_doctor(live_dir, docker_prefix, timeout=arguments.timeout)

        compose_arguments: list[str]
        if arguments.action == "up":
            compose_arguments = ["up", "-d", "--pull", "missing"]
            compose_arguments.extend(arguments.services)
        elif arguments.action == "down":
            compose_arguments = ["down", *arguments.services]
        elif arguments.action == "restart":
            compose_arguments = ["restart", *arguments.services]
        elif arguments.action == "ps":
            compose_arguments = ["ps"]
            if arguments.all:
                compose_arguments.append("--all")
        elif arguments.action == "logs":
            compose_arguments = ["logs"]
            if arguments.follow:
                compose_arguments.append("--follow")
            if arguments.tail is not None:
                compose_arguments.extend(["--tail", arguments.tail])
            if arguments.timestamps:
                compose_arguments.append("--timestamps")
            compose_arguments.extend(arguments.services)
        else:  # pragma: no cover - argparse restricts this value.
            raise AssertionError(f"unsupported action: {arguments.action}")

        compose_result = run_compose(live_dir, compose_arguments)
        return compose_result
    finally:
        # Read distribution metadata in the notifier so a successful update
        # checks the newly installed package rather than this process's import.
        if arguments.action not in {"update", "uninstall"}:
            notify_if_update_available(force_refresh=arguments.action == "update")


def alias_arguments(action: str, arguments: Sequence[str]) -> list[str]:
    """Insert an alias action after the optional global live-directory flag."""

    values = list(arguments)
    if values[:1] == ["--live-dir"] and len(values) >= 2:
        return ["--live-dir", values[1], action, *values[2:]]
    if values[:1] and values[0].startswith("--live-dir="):
        return [values[0], action, *values[1:]]
    return [action, *values]


def up_main() -> int:
    """Run the standalone ``labpulse-up`` alias."""

    return main(alias_arguments("up", sys.argv[1:]))


def down_main() -> int:
    """Run the standalone ``labpulse-down`` alias."""

    return main(alias_arguments("down", sys.argv[1:]))


def restart_main() -> int:
    """Run the standalone ``labpulse-restart`` alias."""

    return main(alias_arguments("restart", sys.argv[1:]))


def ps_main() -> int:
    """Run the standalone ``labpulse-ps`` alias."""

    return main(alias_arguments("ps", sys.argv[1:]))


def logs_main() -> int:
    """Run the standalone ``labpulse-logs`` alias."""

    return main(alias_arguments("logs", sys.argv[1:]))


def config_main() -> int:
    """Run the standalone ``labpulse-config`` alias."""

    return main(alias_arguments("config", sys.argv[1:]))


def open_main() -> int:
    """Run the standalone ``labpulse-open`` alias."""

    return main(alias_arguments("open", sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
