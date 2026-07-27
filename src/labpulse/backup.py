"""Create and restore guarded LabPulse state archives."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import tarfile
from typing import Any, Iterator
from uuid import uuid4


BACKUP_FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
PAYLOAD_DIRECTORY = "payload"
SNAPSHOT_PATHS = (
    "config.yaml",
    "homeassistant/config",
    "mosquitto/data",
    "logs/sms_subscriptions.json",
    "logs/sms_processed_requests.json",
)
MANDATORY_PATHS = ("config.yaml", "homeassistant/config")
CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class BackupError(RuntimeError):
    """Raised when a backup or restore cannot complete safely."""


@dataclass(frozen=True)
class BackupResult:
    """Created archive and its validated manifest."""

    archive_path: Path
    manifest: dict[str, Any]


@contextmanager
def _temporary_directory(parent: Path, prefix: str) -> Iterator[Path]:
    """Create a private disposable directory without tempfile ACL surprises."""

    path = parent / f".{prefix}{uuid4().hex}"
    path.mkdir(parents=True)
    if os.name != "nt":
        path.chmod(0o700)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=False)


def _package_version() -> str:
    """Return the installed LabPulse version without requiring package metadata."""

    try:
        return version("labpulse")
    except PackageNotFoundError:
        return "source-checkout"


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest of one regular file."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _capture_host_command(command: Sequence[str]) -> str:
    """Capture one optional host-setting command without failing backup creation."""

    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return f"unavailable: {error}"
    output = (result.stdout or result.stderr).strip()
    return output or f"exit {result.returncode}"


def _host_report(docker_prefix: Sequence[str]) -> dict[str, str]:
    """Record reconstruction context without copying host credentials."""

    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "docker_command": " ".join(docker_prefix),
        "clock": _capture_host_command(
            (
                "timedatectl",
                "show",
                "--property=Timezone",
                "--property=NTPSynchronized",
            )
        ),
        "watchdog": _capture_host_command(
            (
                "systemctl",
                "show",
                "--property=RuntimeWatchdogUSec",
                "--value",
            )
        ),
    }


def _compose(
    live_dir: Path,
    docker_prefix: Sequence[str],
    arguments: Sequence[str],
    runner: CommandRunner,
) -> subprocess.CompletedProcess[str]:
    """Run one bounded Compose command or raise an actionable error."""

    command = [*docker_prefix, "compose", *arguments]
    try:
        result = runner(
            command,
            cwd=live_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise BackupError(f"Cannot run {' '.join(command)}: {error}") from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise BackupError(
            f"{' '.join(command)} failed: {detail or f'exit {result.returncode}'}"
        )
    return result


def running_services(
    live_dir: Path,
    docker_prefix: Sequence[str],
    runner: CommandRunner = subprocess.run,
) -> tuple[str, ...]:
    """Return the currently running Compose services in stable order."""

    result = _compose(
        live_dir,
        docker_prefix,
        ("ps", "--status", "running", "--services"),
        runner,
    )
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


def stop_services(
    live_dir: Path,
    docker_prefix: Sequence[str],
    services: Sequence[str],
    runner: CommandRunner = subprocess.run,
) -> None:
    """Stop selected services for a consistent state snapshot."""

    if services:
        _compose(live_dir, docker_prefix, ("stop", *services), runner)


def start_services(
    live_dir: Path,
    docker_prefix: Sequence[str],
    services: Sequence[str],
    runner: CommandRunner = subprocess.run,
) -> None:
    """Restart exactly the services stopped for a snapshot."""

    if services:
        _compose(live_dir, docker_prefix, ("start", *services), runner)


def _copy_snapshot_path(source: Path, destination: Path) -> None:
    """Copy one state path while rejecting links and special files."""

    if source.is_symlink():
        raise BackupError(f"Refusing to follow state symlink: {source}")
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return
    if not source.is_dir():
        raise BackupError(f"Unsupported state path type: {source}")

    destination.mkdir(parents=True, exist_ok=True)
    for child in sorted(source.iterdir(), key=lambda item: item.name):
        if child.is_symlink():
            raise BackupError(f"Refusing to follow state symlink: {child}")
        target = destination / child.name
        if child.is_dir():
            _copy_snapshot_path(child, target)
        elif child.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)
        else:
            raise BackupError(f"Unsupported state path type: {child}")


def _runtime_mode(live_dir: Path) -> str:
    """Infer whether generated Compose currently mounts the fake runtime config."""

    compose_path = live_dir / "compose.yaml"
    try:
        compose_text = compose_path.read_text(encoding="utf-8")
    except OSError:
        return "real_hardware"
    return "fake_usb" if "config.fake.yaml:/app/config.yaml" in compose_text else "real_hardware"


def _assemble_snapshot(
    live_dir: Path,
    staging_root: Path,
    docker_prefix: Sequence[str],
) -> dict[str, Any]:
    """Copy selected state and write its checksum manifest."""

    payload_root = staging_root / PAYLOAD_DIRECTORY
    included: list[str] = []
    for relative in SNAPSHOT_PATHS:
        source = live_dir / relative
        if not source.exists():
            if relative in MANDATORY_PATHS:
                raise BackupError(f"Required backup state is missing: {source}")
            continue
        _copy_snapshot_path(source, payload_root / relative)
        included.append(relative)

    checksums = {
        path.relative_to(staging_root).as_posix(): _sha256(path)
        for path in sorted(payload_root.rglob("*"))
        if path.is_file()
    }
    manifest: dict[str, Any] = {
        "format_version": BACKUP_FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "labpulse_version": _package_version(),
        "source_live_directory": str(live_dir),
        "runtime_mode": _runtime_mode(live_dir),
        "included_paths": included,
        "files": checksums,
        "host": _host_report(docker_prefix),
    }
    (staging_root / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _inside(path: Path, parent: Path) -> bool:
    """Return whether a resolved path is inside a resolved parent."""

    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def create_backup(
    live_dir: Path,
    archive_path: Path,
    docker_prefix: Sequence[str],
    *,
    force: bool = False,
    quiesce: bool = True,
    runner: CommandRunner = subprocess.run,
) -> BackupResult:
    """Create one checksummed private archive, restarting quiesced services."""

    live_dir = live_dir.expanduser().resolve()
    archive_path = archive_path.expanduser().resolve()
    if not live_dir.is_dir() or not (live_dir / "compose.yaml").is_file():
        raise BackupError(
            f"LabPulse is not set up at {live_dir}; run 'labpulse setup' first"
        )
    if _inside(archive_path, live_dir):
        raise BackupError("Backup archive must be stored outside the live directory")
    if archive_path.exists() and not force:
        raise BackupError(f"Backup archive already exists: {archive_path}")
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    active_services: tuple[str, ...] = ()
    if quiesce:
        active_services = running_services(live_dir, docker_prefix, runner)

    temporary_archive = archive_path.parent / (
        f".{archive_path.name}.creating-{uuid4().hex}"
    )
    try:
        if quiesce:
            stop_services(live_dir, docker_prefix, active_services, runner)
        with _temporary_directory(
            archive_path.parent,
            "labpulse-backup-",
        ) as staging_root:
            manifest = _assemble_snapshot(live_dir, staging_root, docker_prefix)
            with tarfile.open(temporary_archive, "w:gz") as archive:
                archive.add(staging_root / MANIFEST_NAME, arcname=MANIFEST_NAME)
                archive.add(staging_root / PAYLOAD_DIRECTORY, arcname=PAYLOAD_DIRECTORY)
        os.chmod(temporary_archive, 0o600)
        os.replace(temporary_archive, archive_path)
    finally:
        if temporary_archive.exists():
            temporary_archive.unlink()
        if quiesce:
            start_services(live_dir, docker_prefix, active_services, runner)

    return BackupResult(archive_path=archive_path, manifest=manifest)


def _safe_member_name(name: str) -> bool:
    """Accept only normalized manifest and payload archive paths."""

    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        return False
    return name == MANIFEST_NAME or (
        bool(path.parts) and path.parts[0] == PAYLOAD_DIRECTORY
    )


def _load_manifest(archive: tarfile.TarFile) -> dict[str, Any]:
    """Read and minimally validate the archive manifest."""

    try:
        member = archive.getmember(MANIFEST_NAME)
        stream = archive.extractfile(member)
    except (KeyError, tarfile.TarError) as error:
        raise BackupError("Backup manifest is missing") from error
    if stream is None or not member.isreg():
        raise BackupError("Backup manifest is not a regular file")
    try:
        manifest = json.load(stream)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackupError(f"Backup manifest is invalid: {error}") from error
    if not isinstance(manifest, dict):
        raise BackupError("Backup manifest must be a JSON object")
    if manifest.get("format_version") != BACKUP_FORMAT_VERSION:
        raise BackupError(
            f"Unsupported backup format: {manifest.get('format_version')!r}"
        )
    if manifest.get("runtime_mode") not in {"real_hardware", "fake_usb"}:
        raise BackupError("Backup manifest has an invalid runtime mode")
    files = manifest.get("files")
    included = manifest.get("included_paths")
    if not isinstance(files, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in files.items()
    ):
        raise BackupError("Backup manifest has invalid file checksums")
    if not isinstance(included, list) or not all(
        isinstance(value, str) for value in included
    ):
        raise BackupError("Backup manifest has invalid included paths")
    for mandatory in MANDATORY_PATHS:
        if mandatory not in included:
            raise BackupError(f"Backup is incomplete: missing {mandatory}")
    return manifest


def inspect_backup(archive_path: Path) -> dict[str, Any]:
    """Validate archive structure and every payload checksum."""

    archive_path = archive_path.expanduser().resolve()
    if not archive_path.is_file():
        raise BackupError(f"Backup archive does not exist: {archive_path}")
    try:
        archive = tarfile.open(archive_path, "r:*")
    except (OSError, tarfile.TarError) as error:
        raise BackupError(f"Cannot open backup archive: {error}") from error

    with archive:
        manifest = _load_manifest(archive)
        checksums: dict[str, str] = manifest["files"]
        archive_files: set[str] = set()
        for member in archive.getmembers():
            if not _safe_member_name(member.name):
                raise BackupError(f"Unsafe archive path: {member.name}")
            if not (member.isdir() or member.isreg()):
                raise BackupError(f"Unsafe archive member type: {member.name}")
            if member.isreg() and member.name.startswith(f"{PAYLOAD_DIRECTORY}/"):
                archive_files.add(member.name)
                if member.name not in checksums:
                    raise BackupError(f"Unmanifested backup file: {member.name}")
                stream = archive.extractfile(member)
                if stream is None:
                    raise BackupError(f"Cannot read backup file: {member.name}")
                digest = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
                if digest.hexdigest() != checksums[member.name]:
                    raise BackupError(f"Checksum mismatch: {member.name}")
        if archive_files != set(checksums):
            missing = sorted(set(checksums) - archive_files)
            raise BackupError("Backup payload is missing: " + ", ".join(missing))
    return manifest


def _extract_validated(archive_path: Path, destination: Path) -> dict[str, Any]:
    """Validate and manually extract regular payload files."""

    manifest = inspect_backup(archive_path)
    with tarfile.open(archive_path, "r:*") as archive:
        members = archive.getmembers()
        for member in members:
            if not member.isdir():
                continue
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            target.mkdir(parents=True, exist_ok=True)
        for member in members:
            if not member.isreg():
                continue
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = archive.extractfile(member)
            if stream is None:
                raise BackupError(f"Cannot extract backup file: {member.name}")
            with target.open("wb") as output:
                shutil.copyfileobj(stream, output)
            try:
                os.chmod(target, member.mode & 0o777)
            except OSError:
                pass
    return manifest


def _remove_path(path: Path) -> None:
    """Remove one exact file, link, or directory target."""

    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _copy_local_path(source: Path, destination: Path) -> None:
    """Copy a staged or rollback path without following stored symlinks."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        destination.symlink_to(os.readlink(source))
    elif source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination, follow_symlinks=False)


def _apply_payload(live_dir: Path, payload_root: Path) -> None:
    """Replace snapshot-owned paths and roll back the filesystem on failure."""

    with _temporary_directory(
        live_dir.parent,
        "labpulse-restore-rollback-",
    ) as local_rollback:
        existing: list[str] = []
        for relative in SNAPSHOT_PATHS:
            target = live_dir / relative
            if target.exists() or target.is_symlink():
                _copy_local_path(target, local_rollback / relative)
                existing.append(relative)

        try:
            for relative in SNAPSHOT_PATHS:
                target = live_dir / relative
                _remove_path(target)
                source = payload_root / relative
                if source.exists() or source.is_symlink():
                    _copy_local_path(source, target)
        except Exception as error:
            for relative in SNAPSHOT_PATHS:
                _remove_path(live_dir / relative)
            for relative in existing:
                _copy_local_path(local_rollback / relative, live_dir / relative)
            raise BackupError(f"Restore failed and local state was rolled back: {error}") from error


def restore_backup(live_dir: Path, archive_path: Path) -> dict[str, Any]:
    """Validate and apply archive state to an existing scaffolded live directory."""

    live_dir = live_dir.expanduser().resolve()
    archive_path = archive_path.expanduser().resolve()
    if not live_dir.is_dir():
        raise BackupError(f"Restore target does not exist: {live_dir}")
    with _temporary_directory(
        live_dir.parent,
        "labpulse-restore-",
    ) as extracted:
        manifest = _extract_validated(archive_path, extracted)
        _apply_payload(live_dir, extracted / PAYLOAD_DIRECTORY)
    return manifest
