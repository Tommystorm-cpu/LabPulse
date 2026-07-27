"""Round-trip and safety tests for LabPulse state archives."""

from __future__ import annotations

from contextlib import contextmanager
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from typing import Iterator
from uuid import uuid4


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from labpulse.backup import (
    BackupError,
    create_backup,
    inspect_backup,
    restore_backup,
)


@contextmanager
def state_tree() -> Iterator[tuple[Path, Path]]:
    """Create one complete disposable live state tree and archive destination."""

    root = REPOSITORY / "testing" / "tmp" / f"backup-{uuid4().hex}"
    live = root / "labpulse-live"
    (live / "homeassistant" / "config" / ".storage").mkdir(parents=True)
    (live / "mosquitto" / "data").mkdir(parents=True)
    (live / "logs").mkdir(parents=True)
    (live / "compose.yaml").write_text(
        "services:\n"
        "  homeassistant:\n"
        "    volumes:\n"
        "      - ./homeassistant/config:/config\n",
        encoding="utf-8",
    )
    (live / "config.yaml").write_text("site: accepted\n", encoding="utf-8")
    (live / "homeassistant" / "config" / "configuration.yaml").write_text(
        "homeassistant:\n",
        encoding="utf-8",
    )
    (live / "homeassistant" / "config" / ".storage" / "core.config").write_text(
        '{"latitude": 1}\n',
        encoding="utf-8",
    )
    (live / "homeassistant" / "config" / "home-assistant_v2.db").write_bytes(
        b"sqlite-state"
    )
    (live / "mosquitto" / "data" / "mosquitto.db").write_bytes(b"mqtt-state")
    (live / "logs" / "sms_subscriptions.json").write_text(
        '{"+447700900000": false}\n',
        encoding="utf-8",
    )
    (live / "logs" / "sms_processed_requests.json").write_text(
        '{"request-1": 123}\n',
        encoding="utf-8",
    )
    try:
        yield live.resolve(), (root / "accepted-backup.tar.gz").resolve()
    finally:
        shutil.rmtree(root)


class ComposeRunner:
    """Emulate service inspection, quiescing, and restart."""

    def __init__(self) -> None:
        """Start with a known set of running services."""

        self.commands: list[list[str]] = []

    def __call__(
        self,
        command: list[str],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        """Record commands and return deterministic Compose output."""

        self.commands.append(command)
        stdout = ""
        if command[-4:] == ["ps", "--status", "running", "--services"]:
            stdout = "homeassistant\nlabpulse-sms\nmosquitto\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise an informative assertion when values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_complete_round_trip() -> None:
    """Archive, mutate, and exactly restore all snapshot-owned state."""

    with state_tree() as (live, archive):
        runner = ComposeRunner()
        result = create_backup(live, archive, ["docker"], runner=runner)
        assert_equal(result.archive_path, archive, "archive path")
        if os.name != "nt" and archive.stat().st_mode & 0o077:
            raise AssertionError("backup archive permissions are not private")

        manifest = inspect_backup(archive)
        assert_equal(manifest["format_version"], 1, "format version")
        assert_equal(manifest["runtime_mode"], "real_hardware", "runtime mode")
        for required in (
            "config.yaml",
            "homeassistant/config",
            "mosquitto/data",
            "logs/sms_subscriptions.json",
            "logs/sms_processed_requests.json",
        ):
            if required not in manifest["included_paths"]:
                raise AssertionError(f"manifest omitted {required}")

        assert_equal(
            runner.commands,
            [
                [
                    "docker",
                    "compose",
                    "ps",
                    "--status",
                    "running",
                    "--services",
                ],
                [
                    "docker",
                    "compose",
                    "stop",
                    "homeassistant",
                    "labpulse-sms",
                    "mosquitto",
                ],
                [
                    "docker",
                    "compose",
                    "start",
                    "homeassistant",
                    "labpulse-sms",
                    "mosquitto",
                ],
            ],
            "service quiescing",
        )

        (live / "config.yaml").write_text("site: mutated\n", encoding="utf-8")
        shutil.rmtree(live / "homeassistant" / "config")
        (live / "homeassistant" / "config").mkdir(parents=True)
        (live / "homeassistant" / "config" / "stale.yaml").write_text(
            "stale: true\n",
            encoding="utf-8",
        )
        (live / "mosquitto" / "data" / "mosquitto.db").write_bytes(b"mutated")
        (live / "logs" / "sms_subscriptions.json").write_text(
            "{}\n",
            encoding="utf-8",
        )

        restored_manifest = restore_backup(live, archive)
        assert_equal(restored_manifest["created_at"], manifest["created_at"], "manifest")
        assert_equal(
            (live / "config.yaml").read_text(encoding="utf-8"),
            "site: accepted\n",
            "source config",
        )
        assert_equal(
            (live / "homeassistant" / "config" / ".storage" / "core.config").read_text(
                encoding="utf-8"
            ),
            '{"latitude": 1}\n',
            "Home Assistant storage",
        )
        if (live / "homeassistant" / "config" / "stale.yaml").exists():
            raise AssertionError("restore retained state absent from the archive")
        assert_equal(
            (live / "mosquitto" / "data" / "mosquitto.db").read_bytes(),
            b"mqtt-state",
            "Mosquitto state",
        )
        assert_equal(
            (live / "logs" / "sms_subscriptions.json").read_text(encoding="utf-8"),
            '{"+447700900000": false}\n',
            "SMS subscriptions",
        )


def test_refuses_overwrite_and_live_directory_output() -> None:
    """Require explicit replacement and keep archives outside live state."""

    with state_tree() as (live, archive):
        create_backup(live, archive, ["docker"], quiesce=False)
        try:
            create_backup(live, archive, ["docker"], quiesce=False)
        except BackupError as error:
            if "already exists" not in str(error):
                raise
        else:
            raise AssertionError("existing backup was silently overwritten")

        inside = live / "backup.tar.gz"
        try:
            create_backup(live, inside, ["docker"], quiesce=False)
        except BackupError as error:
            if "outside the live directory" not in str(error):
                raise
        else:
            raise AssertionError("backup inside live state was accepted")


def _write_member(
    archive: tarfile.TarFile,
    name: str,
    payload: bytes,
) -> None:
    """Write one in-memory regular tar member."""

    info = tarfile.TarInfo(name)
    info.size = len(payload)
    archive.addfile(info, BytesIO(payload))


def test_checksum_and_traversal_protection() -> None:
    """Reject tampered payloads and archive paths outside the staging root."""

    with state_tree() as (live, archive):
        create_backup(live, archive, ["docker"], quiesce=False)
        manifest = inspect_backup(archive)

        tampered = archive.parent / "tampered.tar.gz"
        with tarfile.open(tampered, "w:gz") as output:
            _write_member(
                output,
                "manifest.json",
                (json.dumps(manifest) + "\n").encode(),
            )
            for name in manifest["files"]:
                payload = b"tampered" if name == "payload/config.yaml" else b""
                _write_member(output, name, payload)
        try:
            inspect_backup(tampered)
        except BackupError as error:
            if "Checksum mismatch" not in str(error):
                raise
        else:
            raise AssertionError("tampered backup passed checksum validation")

        unsafe = archive.parent / "unsafe.tar.gz"
        with tarfile.open(unsafe, "w:gz") as output:
            _write_member(
                output,
                "manifest.json",
                (json.dumps(manifest) + "\n").encode(),
            )
            _write_member(output, "../outside", b"unsafe")
        try:
            inspect_backup(unsafe)
        except BackupError as error:
            if "Unsafe archive path" not in str(error):
                raise
        else:
            raise AssertionError("path-traversal backup was accepted")


TESTS = [
    ("complete backup/restore round trip", test_complete_round_trip),
    ("overwrite and output guards", test_refuses_overwrite_and_live_directory_output),
    ("checksum and traversal protection", test_checksum_and_traversal_protection),
]


def main() -> None:
    """Run all backup and restore contract tests."""

    passed = 0
    for name, test in TESTS:
        try:
            test()
        except Exception as error:
            print(f"[FAIL] {name}: {type(error).__name__}: {error}")
        else:
            print(f"[PASS] {name}")
            passed += 1
    print(f"Summary: {passed}/{len(TESTS)} passed")
    if passed != len(TESTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
