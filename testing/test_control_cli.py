"""Contract tests for the pipx-installed LabPulse operator commands."""

from contextlib import contextmanager
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
import os
import shutil
import subprocess
import sys
from typing import Iterator
from uuid import uuid4


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from labpulse import control


@contextmanager
def writable_test_directory() -> Iterator[Path]:
    """Create a disposable directory without Windows tempfile ACL surprises."""

    temporary_root = REPOSITORY / "testing" / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    path = temporary_root / f"labpulse-control-{uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path)


def completed(command: list[str], returncode: int = 0) -> subprocess.CompletedProcess:
    """Return a minimal completed process for a mocked command."""

    return subprocess.CompletedProcess(command, returncode)


def main() -> None:
    """Validate command construction, live-directory handling, and edit routing."""

    with writable_test_directory() as live_dir:
        (live_dir / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
        (live_dir / "config.yaml").write_text("version: 1\n", encoding="utf-8")

        with patch.dict(
            os.environ, {"LABPULSE_DOCKER_COMMAND": "docker"}, clear=False
        ), patch.object(control.subprocess, "run") as run:
            run.return_value = completed(["docker"])
            result = control.main(
                [
                    "--live-dir",
                    str(live_dir),
                    "up",
                    "--build",
                    "homeassistant",
                ]
            )
            if result != 0:
                raise AssertionError("up command failed")
            run.assert_called_once_with(
                [
                    "docker",
                    "compose",
                    "up",
                    "-d",
                    "--build",
                    "homeassistant",
                ],
                cwd=live_dir.resolve(),
                check=False,
            )

        with patch.dict(
            os.environ, {"LABPULSE_DOCKER_COMMAND": "sudo docker"}, clear=False
        ), patch.object(control.subprocess, "run") as run:
            run.return_value = completed(["sudo", "docker"])
            result = control.main(
                [
                    "--live-dir",
                    str(live_dir),
                    "logs",
                    "--follow",
                    "--tail",
                    "50",
                    "mosquitto",
                ]
            )
            if result != 0:
                raise AssertionError("logs command failed")
            run.assert_called_once_with(
                [
                    "sudo",
                    "docker",
                    "compose",
                    "logs",
                    "--follow",
                    "--tail",
                    "50",
                    "mosquitto",
                ],
                cwd=live_dir.resolve(),
                check=False,
            )

        with patch.dict(
            os.environ, {"LABPULSE_DOCKER_COMMAND": "sudo docker"}, clear=False
        ), patch.object(control.subprocess, "run") as run:
            run.return_value = completed(["sudo", "docker"])
            result = control.main(
                ["--live-dir", str(live_dir), "restart", "homeassistant"]
            )
            if result != 0:
                raise AssertionError("restart command failed")
            run.assert_called_once_with(
                [
                    "sudo",
                    "docker",
                    "compose",
                    "restart",
                    "homeassistant",
                ],
                cwd=live_dir.resolve(),
                check=False,
            )

        with patch.object(control.shutil, "which", return_value="/bin/bash"), patch.object(
            control, "find_install_assets", return_value=REPOSITORY
        ), patch.object(control.subprocess, "run") as run:
            run.return_value = completed(["bash"])
            result = control.main(["--live-dir", str(live_dir), "edit"])
            if result != 0:
                raise AssertionError("edit command failed")
            call = run.call_args
            if call.args[0] != ["/bin/bash", str(REPOSITORY / "edit_config.sh")]:
                raise AssertionError(f"unexpected edit command: {call.args[0]}")
            if call.kwargs["env"]["LABPULSE_LIVE_DIR"] != str(live_dir.resolve()):
                raise AssertionError("edit command did not target the live directory")

        alias = control.alias_arguments(
            "logs", ["--live-dir", str(live_dir), "-f", "mosquitto"]
        )
        if alias != [
            "--live-dir",
            str(live_dir),
            "logs",
            "-f",
            "mosquitto",
        ]:
            raise AssertionError(f"unexpected alias arguments: {alias}")

        with patch.object(control.webbrowser, "open", return_value=True) as browser:
            result = control.main(["open"])
            if result != 0:
                raise AssertionError("open command failed")
            browser.assert_called_once_with(
                "http://localhost:8123",
                new=2,
            )

        with patch.object(control, "installer_main", return_value=0) as installer:
            result = control.main(
                [
                    "--live-dir",
                    str(live_dir),
                    "setup",
                    "--fake-usb",
                    "--backup",
                ]
            )
            if result != 0:
                raise AssertionError("setup command failed")
            installer.assert_called_once_with(["--fake-usb", "--backup"])

        firmware_output = StringIO()
        with redirect_stdout(firmware_output):
            result = control.main(["firmware"])
        if result != 0:
            raise AssertionError("firmware help command failed")
        firmware_text = firmware_output.getvalue()
        for expected in ("tree/main/firmware", "archive/refs/heads/main.zip"):
            if expected not in firmware_text:
                raise AssertionError(f"firmware help is missing: {expected}")

        general_help = StringIO()
        with redirect_stdout(general_help):
            result = control.main(["help"])
        if result != 0 or "firmware" not in general_help.getvalue():
            raise AssertionError("general help command is incomplete")

        firmware_help = StringIO()
        with redirect_stdout(firmware_help):
            result = control.main(["help", "firmware"])
        if result != 0 or "tree/main/firmware" not in firmware_help.getvalue():
            raise AssertionError("command-specific help is incomplete")

        with patch.object(control, "docker_command", return_value=["docker"]), patch.object(
            control, "run_doctor", return_value=0
        ) as doctor:
            result = control.main(
                ["--live-dir", str(live_dir), "doctor", "--timeout", "2.5"]
            )
            if result != 0:
                raise AssertionError("doctor command failed")
            doctor.assert_called_once_with(
                live_dir.resolve(),
                ["docker"],
                timeout=2.5,
            )

    missing = REPOSITORY / "testing" / "definitely-not-a-live-install"
    if control.main(["--live-dir", str(missing), "ps"]) != 2:
        raise AssertionError("missing live deployment should fail clearly")

    print("[PASS] Docker Compose command routing")
    print("[PASS] Docker Compose restart routing")
    print("[PASS] configurable Docker command prefix")
    print("[PASS] guarded config editor routing")
    print("[PASS] standalone command alias routing")
    print("[PASS] Home Assistant browser routing")
    print("[PASS] unified setup command routing")
    print("[PASS] firmware download guidance")
    print("[PASS] general and command-specific help")
    print("[PASS] doctor command routing")
    print("[PASS] missing installation handling")


if __name__ == "__main__":
    main()
