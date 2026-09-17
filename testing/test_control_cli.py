"""Contract tests for the pipx-installed LabPulse operator commands."""

from contextlib import redirect_stdout
from io import BytesIO
from io import StringIO
import json
from pathlib import Path
import os
import subprocess
from unittest.mock import call, patch

import pytest

from labpulse import __version__
from labpulse import control


_NOTIFY_IF_UPDATE_AVAILABLE = control.notify_if_update_available


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


@pytest.fixture(autouse=True)
def update_notice() -> object:
    """Prevent command-routing tests from contacting TestPyPI."""

    with patch.object(control, "notify_if_update_available") as notice:
        yield notice


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
    ), patch(
        "builtins.input", return_value="1"
    ), patch.object(control.subprocess, "run") as run:
        run.return_value = completed(["bash"])

        result = control.main(["--live-dir", str(live_dir), "config"])

    assert result == 0
    call = run.call_args
    expected_script = repository_root / "deployment" / "edit_config.sh"
    assert call.args[0] == ["/bin/bash", str(expected_script), "config.yaml"]
    assert call.kwargs["env"]["LABPULSE_LIVE_DIR"] == str(live_dir.resolve())
    assert call.kwargs["env"]["LABPULSE_DOCKER_COMMAND"] == "docker"


def test_config_selector_lists_fragments_and_opens_selected_file(live_dir: Path) -> None:
    """List every editable source file and return the chosen fragment."""

    fragment = live_dir / "config.d" / "triton.yaml"
    fragment.parent.mkdir()
    fragment.write_text("{}\n", encoding="utf-8")
    with patch("builtins.input", return_value="2"), patch(
        "sys.stdout", new_callable=StringIO
    ) as output:
        selected = control.select_config_sources(live_dir)
    assert selected == ("config.d/triton.yaml",)
    assert "config.yaml" in output.getvalue()
    assert "config.d/triton.yaml" in output.getvalue()
    assert "Create a new measurement config" in output.getvalue()


def test_config_selector_creates_yaml_with_master(live_dir: Path) -> None:
    """Open a new measurement file with the master so it can be referenced."""

    with patch("builtins.input", side_effect=["2", "new-fridge"]):
        selected = control.select_config_sources(live_dir)
    assert selected == ("config.yaml", "config.d/new-fridge.yaml")


def test_config_command_passes_selected_source_files(
    live_dir: Path, repository_root: Path
) -> None:
    """Allow the guarded editor to open master and measurement fragments together."""

    with patch.dict(
        os.environ, {"LABPULSE_DOCKER_COMMAND": "docker"}, clear=False
    ), patch.object(
        control.shutil, "which", return_value="/bin/bash"
    ), patch.object(
        control, "find_install_assets", return_value=repository_root
    ), patch.object(control.subprocess, "run") as run:
        run.return_value = completed(["bash"])
        result = control.main([
            "--live-dir",
            str(live_dir),
            "config",
            "config.yaml",
            "config.d/triton-01-measurements.yaml",
        ])

    assert result == 0
    expected_script = repository_root / "deployment" / "edit_config.sh"
    assert run.call_args.args[0] == [
        "/bin/bash",
        str(expected_script),
        "config.yaml",
        "config.d/triton-01-measurements.yaml",
    ]


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


@pytest.mark.parametrize("version", [None, "0.2.0"])
def test_update_command_accepts_an_optional_version(
    live_dir: Path, version: str | None
) -> None:
    """Route both latest and explicitly pinned updates through one workflow."""

    arguments = ["--live-dir", str(live_dir), "update"]
    if version is not None:
        arguments.append(version)
    with patch.object(control, "run_update_command", return_value=0) as update:
        result = control.main(arguments)

    assert result == 0
    update.assert_called_once_with(live_dir.resolve(), version)


def test_latest_version_comes_from_test_pypi_metadata() -> None:
    """Use TestPyPI's project metadata rather than the dependency index."""

    response = BytesIO(b'{"info": {"version": "0.2.0"}}')
    with patch.object(control, "urlopen", return_value=response) as open_url:
        version = control.latest_published_version(timeout=3.0)

    assert version == "0.2.0"
    request = open_url.call_args.args[0]
    assert request.full_url == control.TEST_PYPI_PROJECT_URL
    assert request.get_header("Cache-control") == "no-cache"
    assert request.get_header("Pragma") == "no-cache"
    assert open_url.call_args.kwargs == {"timeout": 3.0}


def test_newer_release_prints_update_notice(
    workspace_tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Recommend the simple update command only for a newer release."""

    with patch.object(control, "distribution_version", return_value="0.9.9"), patch.object(
        control, "latest_published_version", return_value="0.10.0"
    ) as latest:
        _NOTIFY_IF_UPDATE_AVAILABLE(cache_path=workspace_tmp_path / "version-check.json")

    assert capsys.readouterr().out == (
        "\nA newer LabPulse version is available: 0.10.0 "
        "(installed: 0.9.9). Run 'labpulse update'.\n"
    )
    latest.assert_called_once_with(timeout=control.UPDATE_CHECK_TIMEOUT_SECONDS)


@pytest.mark.parametrize("published", ["0.9.9", "0.9.8", "0.9.9rc1"])
def test_current_or_older_release_prints_no_notice(
    published: str, workspace_tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Do not describe equal or older releases as updates."""

    with patch.object(control, "distribution_version", return_value="0.9.9"), patch.object(
        control, "latest_published_version", return_value=published
    ):
        _NOTIFY_IF_UPDATE_AVAILABLE(cache_path=workspace_tmp_path / "version-check.json")

    assert capsys.readouterr().out == ""


def test_failed_update_check_is_silent(
    workspace_tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An offline version check must not interfere with an operator command."""

    with patch.object(
        control,
        "latest_published_version",
        side_effect=RuntimeError("network unavailable"),
    ):
        cache_path = workspace_tmp_path / "version-check.json"
        _NOTIFY_IF_UPDATE_AVAILABLE(cache_path=cache_path)

    assert capsys.readouterr().out == ""
    assert json.loads(cache_path.read_text(encoding="utf-8"))["latest"] is None


def test_post_command_update_check_reuses_cached_metadata(
    workspace_tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Avoid another network delay while continuing to print the update notice."""

    cache_path = workspace_tmp_path / "version-check.json"
    with patch.object(control, "distribution_version", return_value="0.9.9"), patch.object(
        control, "latest_published_version", return_value="0.10.0"
    ) as latest:
        _NOTIFY_IF_UPDATE_AVAILABLE(cache_path=cache_path)
        _NOTIFY_IF_UPDATE_AVAILABLE(cache_path=cache_path)

    assert capsys.readouterr().out.count("A newer LabPulse version is available") == 2
    latest.assert_called_once_with(timeout=control.UPDATE_CHECK_TIMEOUT_SECONDS)


def test_commands_run_the_post_command_update_check(update_notice: object) -> None:
    """Run the shared check after an ordinary command finishes."""

    with patch.object(control.webbrowser, "open", return_value=True):
        assert control.main(["open"]) == 0

    update_notice.assert_called_once_with(force_refresh=False)


def test_update_does_not_run_a_second_post_command_version_check(
    live_dir: Path, update_notice: object
) -> None:
    """Keep update resolution inside one workflow so results cannot conflict."""

    with patch.object(control, "run_update_command", return_value=0):
        assert control.main(["--live-dir", str(live_dir), "update"]) == 0

    update_notice.assert_not_called()


@pytest.mark.parametrize("fake_usb", [False, True])
def test_update_installs_refreshes_and_recreates_every_container(
    live_dir: Path, fake_usb: bool
) -> None:
    """Hand setup to the new CLI and retain the active hardware mode."""

    config_mount = (
        "    volumes:\n    - ./config.fake.yaml:/app/config.yaml:ro\n"
        if fake_usb
        else ""
    )
    worker_config = config_mount or "    image: example/labpulse\n"
    (live_dir / "compose.yaml").write_text(
        "services:\n"
        "  homeassistant: {}\n"
        "  mosquitto: {}\n"
        "  labpulse-sms: {}\n"
        "  labpulse-pressure:\n"
        f"{worker_config}",
        encoding="utf-8",
    )

    commands = {
        "pipx": "/usr/bin/pipx",
        "labpulse": "/home/lab/.local/bin/labpulse",
    }
    with patch.object(control, "__version__", "0.1.1"), patch.object(
        control, "latest_published_version", return_value="0.2.0"
    ), patch.object(
        control.shutil, "which", side_effect=lambda command: commands.get(command)
    ), patch.object(
        control.subprocess,
        "run",
        side_effect=(completed(["pipx"]), completed(["labpulse", "setup"]), completed(["labpulse", "doctor"])),
    ) as run, patch.object(
        control, "run_compose", return_value=0
    ) as compose, patch.object(
        control, "_wait_for_homeassistant", return_value=True
    ) as wait:
        result = control.run_update_command(live_dir.resolve(), None)

    assert result == 0
    install = run.call_args_list[0]
    assert install.args[0] == [
        "/usr/bin/pipx",
        "install",
        "--force",
        "--index-url",
        "https://test.pypi.org/simple/",
        "--pip-args=--no-cache-dir --extra-index-url https://pypi.org/simple/",
        "labpulse==0.2.0",
    ]
    setup = run.call_args_list[1]
    expected_setup = [
        "/home/lab/.local/bin/labpulse",
        "--live-dir",
        str(live_dir.resolve()),
        "setup",
        "--backup",
    ]
    if fake_usb:
        expected_setup.append("--fake-usb")
    assert setup.args[0] == expected_setup
    assert compose.call_args_list == [
        call(
            live_dir.resolve(),
            (
                "up",
                "-d",
                "--pull",
                "missing",
                "--remove-orphans",
                "--force-recreate",
            ),
        ),
    ]
    wait.assert_called_once_with()
    doctor = run.call_args_list[2]
    assert doctor.args[0] == [
        "/home/lab/.local/bin/labpulse",
        "--live-dir",
        str(live_dir.resolve()),
        "doctor",
        "--timeout",
        "5",
    ]


def test_update_does_nothing_when_latest_is_installed(live_dir: Path) -> None:
    """Avoid setup and container downtime when TestPyPI matches the CLI."""

    with patch.object(control, "__version__", "0.2.0"), patch.object(
        control, "latest_published_version", return_value="0.2.0"
    ) as latest, patch.object(
        control.shutil,
        "which",
        side_effect=lambda command: f"/usr/bin/{command}",
    ) as find_command, patch.object(control.subprocess, "run") as run, patch.object(
        control, "run_compose"
    ) as compose:
        result = control.run_update_command(live_dir.resolve(), None)

    assert result == 0
    assert latest.call_count == 2
    find_command.assert_not_called()
    run.assert_not_called()
    compose.assert_not_called()


def test_update_rechecks_equal_metadata_and_uses_newly_visible_release(live_dir: Path) -> None:
    """Handle TestPyPI propagation without reporting contradictory results."""

    commands = {"pipx": "/usr/bin/pipx", "labpulse": "/home/lab/.local/bin/labpulse"}
    with patch.object(control, "__version__", "0.3.0"), patch.object(
        control, "latest_published_version", side_effect=("0.3.0", "0.3.1")
    ) as latest, patch.object(
        control.shutil, "which", side_effect=lambda command: commands.get(command)
    ), patch.object(
        control.subprocess,
        "run",
        side_effect=(completed(["pipx"]), completed(["labpulse", "setup"]), completed(["labpulse", "doctor"])),
    ) as run, patch.object(
        control, "run_compose", return_value=0
    ), patch.object(
        control, "_wait_for_homeassistant", return_value=True
    ):
        result = control.run_update_command(live_dir.resolve(), None)

    assert result == 0
    assert latest.call_count == 2
    assert run.call_args_list[0].args[0][-1] == "labpulse==0.3.1"


def test_update_waits_for_homeassistant_and_skips_early_diagnostics(
    live_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Do not diagnose the reconstructed stack before Home Assistant is listening."""

    commands = {"pipx": "/usr/bin/pipx", "labpulse": "/home/lab/.local/bin/labpulse"}
    with patch.object(control, "__version__", "0.1.1"), patch.object(
        control, "latest_published_version", return_value="0.2.0"
    ), patch.object(
        control.shutil, "which", side_effect=lambda command: commands.get(command)
    ), patch.object(
        control.subprocess,
        "run",
        side_effect=(completed(["pipx"]), completed(["labpulse", "setup"])),
    ) as run, patch.object(
        control, "run_compose", return_value=0
    ), patch.object(
        control, "_wait_for_homeassistant", return_value=False
    ) as wait:
        result = control.run_update_command(live_dir.resolve(), None)

    assert result == 1
    wait.assert_called_once_with()
    assert len(run.call_args_list) == 2
    output = capsys.readouterr()
    assert "Waiting for Home Assistant" in output.out
    assert "did not become ready within 120 seconds" in output.err


def test_explicit_current_version_does_not_recheck(live_dir: Path) -> None:
    """Treat an explicit version as authoritative without querying metadata."""

    with patch.object(control, "__version__", "0.2.0"), patch.object(
        control, "latest_published_version"
    ) as latest, patch.object(control.shutil, "which") as find_command:
        result = control.run_update_command(live_dir.resolve(), "0.2.0")

    assert result == 0
    latest.assert_not_called()
    find_command.assert_not_called()


def test_update_reports_compose_failure_without_suppressing_notifications(
    live_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failed recreation leaves no retained mute or stopped SMS worker."""

    commands = {"pipx": "/usr/bin/pipx", "labpulse": "/home/lab/.local/bin/labpulse"}
    with patch.object(control, "__version__", "0.1.1"), patch.object(
        control, "latest_published_version", return_value="0.2.0"
    ), patch.object(
        control.shutil, "which", side_effect=lambda command: commands.get(command)
    ), patch.object(
        control.subprocess, "run",
        side_effect=(completed(["pipx"]), completed(["labpulse", "setup"])),
    ), patch.object(control, "run_compose", return_value=7) as compose:
        result = control.run_update_command(live_dir.resolve(), None)

    assert result == 7
    compose.assert_called_once_with(
        live_dir.resolve(),
        ("up", "-d", "--pull", "missing", "--remove-orphans", "--force-recreate"),
    )
    assert "stack could not be recreated" in capsys.readouterr().err


def test_starting_sms_is_ordinary_compose_up(live_dir: Path) -> None:
    """Starting the SMS worker needs no separate notification handshake."""

    with patch.object(control, "run_compose", return_value=0) as compose:
        result = control.main(["--live-dir", str(live_dir), "up", "labpulse-sms"])

    assert result == 0
    compose.assert_called_once_with(live_dir.resolve(), ["up", "-d", "--pull", "missing", "labpulse-sms"])



def test_failed_pipx_update_leaves_setup_and_containers_alone(live_dir: Path) -> None:
    """Stop immediately when the new command could not be installed."""

    commands = {
        "pipx": "/usr/bin/pipx",
        "labpulse": "/home/lab/.local/bin/labpulse",
    }
    with patch.object(control, "__version__", "0.1.1"), patch.object(
        control, "latest_published_version", return_value="0.2.0"
    ), patch.object(
        control.shutil, "which", side_effect=lambda command: commands.get(command)
    ), patch.object(
        control.subprocess, "run", return_value=completed(["pipx"], returncode=1)
    ) as run, patch.object(control, "run_compose") as compose:
        result = control.run_update_command(live_dir.resolve(), None)

    assert result == 1
    assert run.call_count == 1
    compose.assert_not_called()


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


def test_uninstall_command_delegates_confirmation_choice(
    live_dir: Path, update_notice: object
) -> None:
    """Route uninstall through its destructive-operation guard."""

    with patch.object(control, "run_uninstall_command", return_value=0) as uninstall:
        result = control.main(["--live-dir", str(live_dir), "uninstall", "--yes"])

    assert result == 0
    uninstall.assert_called_once_with(live_dir.resolve(), assume_yes=True)
    update_notice.assert_not_called()


def test_uninstall_cancellation_preserves_installation(live_dir: Path) -> None:
    """Require the exact confirmation word before stopping or deleting anything."""

    with patch("builtins.input", return_value="no"), patch.object(control, "run_compose") as compose:
        result = control.run_uninstall_command(live_dir, assume_yes=False)

    assert result == 2
    assert live_dir.is_dir()
    compose.assert_not_called()


def test_uninstall_removes_compose_resources_directory_and_cache(
    workspace_tmp_path: Path,
) -> None:
    """Remove Docker resources before deleting all local deployment state."""

    live_dir = workspace_tmp_path / "live"
    live_dir.mkdir()
    (live_dir / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    cache = workspace_tmp_path / "cache" / "labpulse" / "update-check.json"
    cache.parent.mkdir(parents=True)
    cache.write_text("{}", encoding="utf-8")
    with patch.object(control, "run_compose", return_value=0) as compose, patch.object(
        control, "update_check_cache_path", return_value=cache
    ):
        result = control.run_uninstall_command(live_dir, assume_yes=True)

    assert result == 0
    compose.assert_called_once_with(live_dir, ("down", "--remove-orphans", "--volumes"))
    assert not live_dir.exists()
    assert not cache.exists()


def test_uninstall_keeps_files_when_docker_cleanup_fails(live_dir: Path) -> None:
    """Do not orphan a running stack by deleting its Compose project first."""

    with patch.object(control, "run_compose", return_value=1):
        result = control.run_uninstall_command(live_dir, assume_yes=True)

    assert result == 1
    assert live_dir.is_dir()


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
