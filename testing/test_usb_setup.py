"""Behavior tests for interactive real USB serial assignment."""

import os
import shutil
import sys
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4


REFACTOR_DIR = Path(__file__).resolve().parents[1]
TEST_TMP = REFACTOR_DIR / "testing" / "tmp"
TEST_TMP.mkdir(parents=True, exist_ok=True)

from setup_usb_devices import (
    SerialService,
    _use_managed_python_when_deployed,
    build_parser,
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


def test_deployed_helper_reexecutes_from_system_python() -> None:
    """Use the managed environment even when both executables resolve alike."""

    directory = TEST_TMP / f"usb-python-{uuid4().hex}"
    python_path = directory / ".venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("fixture", encoding="utf-8")
    script_path = directory / "setup_usb_devices.py"
    try:
        with (
            patch("setup_usb_devices.__file__", str(script_path)),
            patch.object(sys, "prefix", str(directory / "system-python")),
            patch.object(sys, "executable", str(python_path)),
            patch.object(sys, "argv", [str(script_path), "--help"]),
            patch.dict(os.environ, {}, clear=True),
            patch("setup_usb_devices.os.execv") as execute,
        ):
            _use_managed_python_when_deployed()

        execute.assert_called_once_with(
            str(python_path),
            [str(python_path), str(script_path), "--help"],
        )
    finally:
        python_path.unlink(missing_ok=True)
        python_path.parent.rmdir()
        (directory / ".venv").rmdir()
        directory.rmdir()


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
    with patch("setup_usb_devices.snapshot_devices", side_effect=lambda _path: next(snapshots)), patch(
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
        with patch("setup_usb_devices.snapshot_devices", side_effect=lambda _path: next(snapshots)), patch(
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


def test_cli_modes() -> None:
    """Check preview and confirmed-write options remain explicit."""

    parser = build_parser()
    preview = parser.parse_args(["--config", "config.yaml", "--dry-run"])
    if not preview.dry_run:
        raise AssertionError(f"dry-run option was not parsed: {preview!r}")
    real = parser.parse_args(["--config", "config.yaml", "--yes"])
    if not real.yes:
        raise AssertionError(f"real apply options were not parsed: {real!r}")
