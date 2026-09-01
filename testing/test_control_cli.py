"""Contract tests for the pipx-installed LabPulse operator commands."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import os
import subprocess
from unittest.mock import patch

import pytest

from labpulse import __version__
from labpulse import control


def completed(command: list[str], returncode: int = 0) -> subprocess.CompletedProcess:
    """Return a minimal completed process for a mocked command."""

    return subprocess.CompletedProcess(command, returncode)


@pytest.fixture
def live_dir(workspace_tmp_path: Path) -> Path:
    """Create the files that identify a generated live installation."""

    (workspace_tmp_path / "compose.yaml").write_text(
        "services: {}\n", encoding="utf-8"
    )
    (workspace_tmp_path / "config.yaml").write_text(
        "version: 1\n", encoding="utf-8"
    )
    return workspace_tmp_path


@pytest.mark.parametrize(
    ("docker_command", "arguments", "compose_arguments"),
    [
        (
            "docker",
            ["up", "homeassistant"],
            ["up", "-d", "--pull", "missing", "homeassistant"],
        ),
        (
            "sudo docker",
            ["logs", "--follow", "--tail", "50", "mosquitto"],
            ["logs", "--follow", "--tail", "50", "mosquitto"],
        ),
        (
            "docker",
            ["down", "labpulse-room-environment"],
            ["down", "labpulse-room-environment"],
        ),
        (
            "docker",
            ["restart", "labpulse-room-environment"],
            ["restart", "labpulse-room-environment"],
        ),
        (
            "sudo docker",
            ["restart", "homeassistant"],
            ["restart", "homeassistant"],
        ),
    ],
)
def test_compose_commands_route_to_the_live_installation(
    live_dir: Path,
    docker_command: str,
    arguments: list[str],
    compose_arguments: list[str],
) -> None:
    with patch.dict(
        os.environ, {"LABPULSE_DOCKER_COMMAND": docker_command}, clear=False
    ), patch.object(control.subprocess, "run") as run:
        run.return_value = completed(docker_command.split())

        result = control.main(["--live-dir", str(live_dir), *arguments])

    assert result == 0
    run.assert_called_once_with(
        [*docker_command.split(), "compose", *compose_arguments],
        cwd=live_dir.resolve(),
        check=False,
    )


def test_config_command_routes_through_the_guarded_editor(
    live_dir: Path, repository_root: Path
) -> None:
    with patch.dict(
        os.environ, {"LABPULSE_DOCKER_COMMAND": "docker"}, clear=False
    ), patch.object(
        control.shutil, "which", return_value="/bin/bash"
    ), patch.object(
        control, "find_install_assets", return_value=repository_root
    ), patch.object(control.subprocess, "run") as run:
        run.return_value = completed(["bash"])

        result = control.main(["--live-dir", str(live_dir), "config"])

    assert result == 0
    call = run.call_args
    expected_script = repository_root / "deployment" / "edit_config.sh"
    assert call.args[0] == ["/bin/bash", str(expected_script)]
    assert call.kwargs["env"]["LABPULSE_LIVE_DIR"] == str(live_dir.resolve())
    assert call.kwargs["env"]["LABPULSE_DOCKER_COMMAND"] == "docker"


def test_alias_arguments_preserve_global_options(live_dir: Path) -> None:
    assert control.alias_arguments(
        "logs", ["--live-dir", str(live_dir), "-f", "mosquitto"]
    ) == ["--live-dir", str(live_dir), "logs", "-f", "mosquitto"]


def test_open_command_launches_home_assistant() -> None:
    with patch.object(control.webbrowser, "open", return_value=True) as browser:
        result = control.main(["open"])

    assert result == 0
    browser.assert_called_once_with("http://localhost:8123", new=2)


def test_setup_command_delegates_installer_arguments(live_dir: Path) -> None:
    with patch.object(control, "installer_main", return_value=0) as installer:
        result = control.main(
            ["--live-dir", str(live_dir), "setup", "--fake-usb", "--backup"]
        )

    assert result == 0
    installer.assert_called_once_with(["--fake-usb", "--backup"])


def test_backup_command_delegates_resolved_paths(live_dir: Path) -> None:
    archive = live_dir.parent / "labpulse-state.tar.gz"
    with patch.object(control, "run_backup_command", return_value=0) as backup:
        result = control.main(
            ["--live-dir", str(live_dir), "backup", str(archive), "--force"]
        )

    assert result == 0
    backup.assert_called_once_with(live_dir.resolve(), archive, force=True)


def test_restore_command_delegates_confirmation_choice(live_dir: Path) -> None:
    archive = live_dir.parent / "labpulse-state.tar.gz"
    with patch.object(control, "run_restore_command", return_value=0) as restore:
        result = control.main(
            ["--live-dir", str(live_dir), "restore", str(archive), "--yes"]
        )

    assert result == 0
    restore.assert_called_once_with(live_dir.resolve(), archive, assume_yes=True)


def test_restore_rebuilds_and_validates_the_installation(live_dir: Path) -> None:
    archive = live_dir.parent / "labpulse-state.tar.gz"
    manifest = {"runtime_mode": "real_hardware"}
    with patch.object(
        control, "inspect_backup", return_value=manifest
    ), patch.object(
        control, "docker_command", return_value=["docker"]
    ), patch.object(
        control, "running_services", return_value=("homeassistant", "mosquitto")
    ), patch.object(control, "stop_services") as stop_services, patch.object(
        control, "create_backup"
    ) as create_rollback, patch.object(
        control, "restore_backup", return_value=manifest
    ) as restore_state, patch.object(
        control, "run_setup", return_value=0
    ) as regenerate, patch.object(
        control, "run_compose", return_value=0
    ) as compose, patch.object(
        control, "_wait_for_homeassistant", return_value=True
    ), patch.object(control, "run_doctor", return_value=0) as doctor:
        result = control.run_restore_command(
            live_dir.resolve(), archive, assume_yes=True
        )

    assert result == 0
    stop_services.assert_called_once_with(
        live_dir.resolve(), ["docker"], ("homeassistant", "mosquitto")
    )
    rollback = create_rollback.call_args.args[1]
    assert rollback.parent == live_dir.parent
    assert rollback.name.startswith("labpulse-pre-restore-")
    create_rollback.assert_called_once_with(live_dir.resolve(), rollback, ["docker"], quiesce=False)
    restore_state.assert_called_once_with(live_dir.resolve(), archive)
    regenerate.assert_called_once_with(str(live_dir.resolve()), fake_usb=False, backup=True)
    compose.assert_called_once_with(
        live_dir.resolve(), ("up", "-d", "--pull", "missing")
    )
    doctor.assert_called_once_with(live_dir.resolve(), ["docker"], timeout=5.0)


def test_restore_cancellation_makes_no_changes(live_dir: Path) -> None:
    archive = live_dir.parent / "labpulse-state.tar.gz"
    manifest = {"runtime_mode": "real_hardware"}
    with patch.object(
        control, "inspect_backup", return_value=manifest
    ), patch("builtins.input", return_value="cancel"):
        result = control.run_restore_command(
            live_dir.resolve(), archive, assume_yes=False
        )

    assert result == 2


def test_restore_can_reconstruct_a_blank_installation(
    workspace_tmp_path: Path,
) -> None:
    blank_live = workspace_tmp_path / "blank-installation"
    archive = workspace_tmp_path / "labpulse-state.tar.gz"
    manifest = {"runtime_mode": "real_hardware"}
    with patch.object(
        control, "inspect_backup", return_value=manifest
    ), patch.object(
        control, "run_setup", return_value=0
    ) as scaffold, patch.object(
        control, "docker_command", return_value=["docker"]
    ), patch.object(
        control, "running_services", return_value=()
    ), patch.object(control, "stop_services"), patch.object(
        control, "create_backup"
    ) as unexpected_rollback, patch.object(
        control, "restore_backup", return_value=manifest
    ), patch.object(
        control, "run_compose", return_value=0
    ), patch.object(
        control, "_wait_for_homeassistant", return_value=True
    ), patch.object(control, "run_doctor", return_value=0):
        result = control.run_restore_command(blank_live, archive, assume_yes=True)

    assert result == 0
    scaffold.assert_any_call(str(blank_live), fake_usb=False, backup=True)
    unexpected_rollback.assert_not_called()


def test_failed_restore_regeneration_rolls_back(live_dir: Path) -> None:
    archive = live_dir.parent / "labpulse-state.tar.gz"
    manifest = {"runtime_mode": "real_hardware"}
    with patch.object(
        control, "inspect_backup", return_value=manifest
    ), patch.object(
        control, "docker_command", return_value=["docker"]
    ), patch.object(
        control, "running_services", return_value=("homeassistant",)
    ), patch.object(control, "stop_services"), patch.object(
        control, "create_backup"
    ), patch.object(
        control, "restore_backup", side_effect=(manifest, manifest)
    ) as restore_state, patch.object(
        control, "run_setup", side_effect=(1, 0)
    ) as regeneration, patch.object(control, "start_services") as restart_previous:
        result = control.run_restore_command(
            live_dir.resolve(), archive, assume_yes=True
        )

    assert result == 1
    assert restore_state.call_count == 2
    assert regeneration.call_count == 2
    restart_previous.assert_called_once_with(
        live_dir.resolve(), ["docker"], ("homeassistant",)
    )


def capture_command(arguments: list[str]) -> tuple[int, str]:
    """Run an informational command and return its captured standard output."""

    output = StringIO()
    with redirect_stdout(output):
        result = control.main(arguments)
    return result, output.getvalue()


def test_firmware_command_prints_download_locations() -> None:
    result, output = capture_command(["firmware"])

    assert result == 0
    assert "tree/main/firmware" in output
    assert "archive/refs/heads/main.zip" in output


def test_version_command_reports_the_package_version() -> None:
    result, output = capture_command(["version"])

    assert result == 0
    assert output.strip() == f"LabPulse {__version__}"


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [(["help"], "firmware"), (["help", "firmware"], "tree/main/firmware")],
)
def test_help_commands_include_expected_guidance(
    arguments: list[str], expected: str
) -> None:
    result, output = capture_command(arguments)

    assert result == 0
    assert expected in output


def test_doctor_command_delegates_timeout(live_dir: Path) -> None:
    with patch.object(
        control, "docker_command", return_value=["docker"]
    ), patch.object(control, "run_doctor", return_value=0) as doctor:
        result = control.main(
            ["--live-dir", str(live_dir), "doctor", "--timeout", "2.5"]
        )

    assert result == 0
    doctor.assert_called_once_with(live_dir.resolve(), ["docker"], timeout=2.5)


def test_compose_command_rejects_a_missing_installation(
    repository_root: Path,
) -> None:
    missing = repository_root / "testing" / "definitely-not-a-live-install"

    assert control.main(["--live-dir", str(missing), "ps"]) == 2
