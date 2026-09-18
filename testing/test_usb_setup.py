"""Behavior tests for interactive real USB serial assignment."""

import shutil
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from labpulse import control

REFACTOR_DIR = Path(__file__).resolve().parents[1]
TEST_TMP = REFACTOR_DIR / "testing" / "tmp"
TEST_TMP.mkdir(parents=True, exist_ok=True)

from labpulse.usb import (
    SerialService,
    identify_devices,
    load_serial_services,
    replace_serial_ports,
    write_config,
)


CONFIG = """# preserve this manual comment
mqtt:
  broker: mosquitto
setups: {}
services:
  pressure_monitor:
    label: Air Pressure Sensor Hub
    driver:
      type: labpulse.serial_pipe
      options:
        port: /dev/ttyACM0  # replace only this line
    measurements: {}
  pump_room:
    label: Pump Room Sensor Hub
    driver:
      type: labpulse.serial_pipe
      options:
        port: FAKE_PUMP_ROOM_PORT
    measurements: {}
  room_environment:
    label: Room Sensor
    driver:
      type: labpulse.dht11
      options:
        pin: D4
    measurements: {}
"""


def test_loads_only_enabled_serial_services() -> None:
    """Check assignment order follows enabled serial config order."""

    directory = TEST_TMP / f"usb-{uuid4().hex}"
    directory.mkdir()
    try:
        path = directory / "config.yaml"
        path.write_text(CONFIG, encoding="utf-8")
        services = load_serial_services(path)
    finally:
        path.unlink(missing_ok=True)
        directory.rmdir()
    if [service.name for service in services] != ["pressure_monitor", "pump_room"]:
        raise AssertionError(f"unexpected services: {services!r}")
    if services[0].label != "Air Pressure Sensor Hub":
        raise AssertionError("service label was not used as the operator label")


def test_identifies_unplugged_then_replugged_devices() -> None:
    """Check one disappearing stable path is assigned to each service."""

    services = [
        SerialService("pressure_monitor", "Air Pressure"),
        SerialService("pump_room", "Pump Room"),
    ]
    baseline = {
        "usb-pressure": "/dev/serial/by-id/usb-pressure",
        "usb-pump": "/dev/serial/by-id/usb-pump",
        "usb-unrelated": "/dev/serial/by-id/usb-unrelated",
    }
    snapshots = iter(
        [
            baseline,
            {key: value for key, value in baseline.items() if key != "usb-pressure"},
            baseline,
            {key: value for key, value in baseline.items() if key != "usb-pump"},
            baseline,
        ]
    )
    prompts: list[str] = []
    with patch("labpulse.usb.snapshot_devices", side_effect=lambda _path: next(snapshots)), patch(
        "builtins.input", side_effect=lambda message: prompts.append(message) or ""
    ):
        assignments = identify_devices(services, Path("/dev/serial/by-id"))
    expected = {
        "pressure_monitor": "/dev/serial/by-id/usb-pressure",
        "pump_room": "/dev/serial/by-id/usb-pump",
    }
    if assignments != expected:
        raise AssertionError(f"unexpected assignments: {assignments!r}")
    if "every USB serial device plugged in" not in prompts[0]:
        raise AssertionError("helper does not begin with all devices connected")


def test_rejects_ambiguous_unplug() -> None:
    """Check zero or multiple disappearing endpoints cannot be mislabelled."""

    baseline = {"one": "/fake/one", "two": "/fake/two"}
    snapshots = iter([baseline, {}])
    try:
        with patch("labpulse.usb.snapshot_devices", side_effect=lambda _path: next(snapshots)), patch(
            "builtins.input", return_value=""
        ):
            identify_devices([SerialService("service", "Service")], Path("/fake"))
    except RuntimeError as error:
        if "exactly one" not in str(error):
            raise AssertionError(f"unclear ambiguity error: {error}") from error
    else:
        raise AssertionError("helper accepted two devices disappearing together")


def test_surgical_config_update_and_backup() -> None:
    """Check only nested serial driver ports change and writes keep one backup."""

    assignments = {
        "pressure_monitor": "/dev/serial/by-id/usb-pressure",
        "pump_room": "/dev/serial/by-id/usb-pump",
    }
    updated = replace_serial_ports(CONFIG, assignments, source=Path("config.yaml"))
    if "# preserve this manual comment" not in updated or "type: labpulse.dht11" not in updated:
        raise AssertionError("manual or unrelated config content was lost")
    for port in assignments.values():
        if f'port: "{port}"' not in updated:
            raise AssertionError(f"assignment missing from updated config: {port}")
    if "/dev/ttyACM0" in updated or "FAKE_PUMP_ROOM_PORT" in updated:
        raise AssertionError("old unstable paths remain after replacement")

    directory = TEST_TMP / f"usb-{uuid4().hex}"
    directory.mkdir()
    try:
        path = directory / "config.yaml"
        path.write_text(CONFIG, encoding="utf-8")
        backup = write_config(path, updated)
        if path.read_text(encoding="utf-8") != updated:
            raise AssertionError("atomic write did not install updated config")
        if backup.read_text(encoding="utf-8") != CONFIG:
            raise AssertionError("USB setup backup did not preserve the previous config")
        if backup != directory / "backups" / "config.yaml.usb-setup-backup":
            raise AssertionError(f"USB setup backup was not isolated: {backup}")
        second_update = updated.replace("usb-pressure", "usb-pressure-reassigned")
        second_backup = write_config(path, second_update)
        if second_backup != backup or backup.read_text(encoding="utf-8") != updated:
            raise AssertionError("USB setup did not replace its single rolling backup")
        if len(list((directory / "backups").iterdir())) != 1:
            raise AssertionError("USB setup accumulated more than one backup")
    finally:
        shutil.rmtree(directory)


def test_usb_assignment_validates_external_measurements_without_editing_them() -> None:
    """Keep driver-port surgery in the master while resolving its measurement file."""

    directory = TEST_TMP / f"usb-fragment-{uuid4().hex}"
    (directory / "config.d").mkdir(parents=True)
    path = directory / "config.yaml"
    source = """mqtt: {broker: mosquitto}
setups: {monitor: {}}
services:
  pressure_monitor:
    label: Pressure Monitor
    driver:
      type: labpulse.serial_pipe
      options:
        port: /dev/ttyACM0
    measurement_defaults: {setups: [monitor]}
    measurements_file: config.d/pressure-measurements.yaml
"""
    fragment = directory / "config.d" / "pressure-measurements.yaml"
    path.write_text(source, encoding="utf-8")
    fragment.write_text("pressure: {unit: bar}\n", encoding="utf-8")
    try:
        updated = replace_serial_ports(
            source,
            {"pressure_monitor": "/dev/serial/by-id/usb-pressure"},
            source=path,
        )
        assert 'port: "/dev/serial/by-id/usb-pressure"' in updated
        assert fragment.read_text(encoding="utf-8") == "pressure: {unit: bar}\n"
    finally:
        shutil.rmtree(directory)


@pytest.mark.parametrize("mode", ["save", "yes", "dry-run", "decline", "interrupt", "eof"])
def test_usb_command_guides_assignment_and_only_saves_when_confirmed(
    workspace_tmp_path: Path, mode: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exercise the installed command through detection, preview, and saving."""

    config_path = workspace_tmp_path / "config.yaml"
    config_path.write_text(CONFIG, encoding="utf-8")
    baseline = {
        "pressure": "/dev/serial/by-id/usb-pressure",
        "pump": "/dev/serial/by-id/usb-pump",
    }
    snapshots = [baseline, {"pump": baseline["pump"]}, baseline,
                 {"pressure": baseline["pressure"]}, baseline]
    arguments = ["--live-dir", str(workspace_tmp_path), "usb"]
    if mode in {"yes", "dry-run"}:
        arguments.append(f"--{mode}")
    responses = ["", "", "", "", "", "yes" if mode == "save" else "no"]
    if mode in {"interrupt", "eof"}:
        responses[-1] = KeyboardInterrupt() if mode == "interrupt" else EOFError()

    with (
        patch("labpulse.usb.snapshot_devices", side_effect=snapshots),
        patch("builtins.input", side_effect=responses) as prompt,
        patch.object(control, "notify_if_update_available"),
    ):
        result = control.main(arguments)

    assert result == (130 if mode in {"interrupt", "eof"} else 0)
    output = capsys.readouterr()
    assert "Detected assignments:" in output.out
    assert "/dev/serial/by-id/usb-pressure" in output.out
    assert "Unplug the USB device for Air Pressure Sensor Hub" in prompt.call_args_list[1].args[0]
    backup_path = workspace_tmp_path / "backups/config.yaml.usb-setup-backup"
    if mode in {"save", "yes"}:
        assert backup_path.read_text(encoding="utf-8") == CONFIG
        updated = config_path.read_text(encoding="utf-8")
        assert 'port: "/dev/serial/by-id/usb-pressure"' in updated
        assert 'port: "/dev/serial/by-id/usb-pump"' in updated
        assert "# preserve this manual comment" in updated
        assert "config config.yaml" in output.out
    else:
        assert config_path.read_text(encoding="utf-8") == CONFIG
        assert not backup_path.exists()


@pytest.mark.parametrize("selection", ["default", "environment", "flag"])
def test_usb_command_selects_live_config(
    workspace_tmp_path: Path, monkeypatch: pytest.MonkeyPatch, selection: str
) -> None:
    """Resolve the live config without depending on the current directory."""

    monkeypatch.setattr(control, "DEFAULT_LIVE_DIR", workspace_tmp_path / "default")
    monkeypatch.delenv("LABPULSE_LIVE_DIR", raising=False)
    expected = workspace_tmp_path / "default"
    arguments = ["usb", "--dry-run"]
    if selection in {"environment", "flag"}:
        expected = workspace_tmp_path / "environment"
        monkeypatch.setenv("LABPULSE_LIVE_DIR", str(expected))
    if selection == "flag":
        expected = workspace_tmp_path / "override"
        arguments = ["--live-dir", str(expected), *arguments]
    with patch.object(control, "run_usb_setup", return_value=1) as setup, patch.object(
        control, "notify_if_update_available"
    ):
        assert control.main(arguments) == 1
    setup.assert_called_once_with(
        expected.resolve() / "config.yaml", dry_run=True, assume_yes=False
    )


def test_usb_help_explains_interactive_options(capsys: pytest.CaptureFixture[str]) -> None:
    """Expose USB setup through the normal command help without scanning devices."""

    with patch.object(control, "notify_if_update_available"), patch("builtins.input") as prompt:
        assert control.main(["help", "usb"]) == 0
    prompt.assert_not_called()
    output = capsys.readouterr().out
    assert "unplug/replug" in output
    assert "--dry-run" in output
    assert "--yes" in output
