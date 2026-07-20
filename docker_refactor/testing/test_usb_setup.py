"""Behavior tests for interactive real/fake USB serial assignment."""

from pathlib import Path
import sys
from typing import Callable
from uuid import uuid4


REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))
TEST_TMP = REFACTOR_DIR / "testing" / "tmp"
TEST_TMP.mkdir(parents=True, exist_ok=True)

from setup_usb_devices import (
    SerialService,
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
    enabled: true
    driver: serial
    parser: pressure
    serial_port: /dev/ttyACM0  # replace only this line
    device_name: Air Pressure Sensor Hub
    readings: []
  pump_room:
    driver: serial
    parser: pump_room
    serial_port: FAKE_PUMP_ROOM_PORT
    device_name: Pump Room Sensor Hub
    readings: []
  room_environment:
    driver: gpio
    gpio_sensor: dht11
    device_name: Room Sensor
    readings: []
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
        raise AssertionError("device_name was not used as the operator label")


def test_identifies_unplugged_then_replugged_devices() -> None:
    """Check one disappearing stable path is assigned to each service."""

    services = [
        SerialService("pressure_monitor", "Air Pressure", None),
        SerialService("pump_room", "Pump Room", None),
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
    assignments = identify_devices(
        services,
        snapshot=lambda: next(snapshots),
        prompt=lambda message: prompts.append(message) or "",
    )
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
        identify_devices(
            [SerialService("service", "Service", None)],
            snapshot=lambda: next(snapshots),
            prompt=lambda _message: "",
        )
    except RuntimeError as error:
        if "exactly one" not in str(error):
            raise AssertionError(f"unclear ambiguity error: {error}") from error
    else:
        raise AssertionError("helper accepted two devices disappearing together")


def test_surgical_config_update_and_backup() -> None:
    """Check only serial_port assignments change and writes keep one backup."""

    assignments = {
        "pressure_monitor": "/dev/serial/by-id/usb-pressure",
        "pump_room": "/dev/serial/by-id/usb-pump",
    }
    updated = replace_serial_ports(CONFIG, assignments)
    if "# preserve this manual comment" not in updated or "driver: gpio" not in updated:
        raise AssertionError("manual or unrelated config content was lost")
    for port in assignments.values():
        if f'serial_port: "{port}"' not in updated:
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
    finally:
        for child in directory.iterdir():
            child.unlink()
        directory.rmdir()


def test_cli_modes() -> None:
    """Check real and fake workflows expose explicit safe command options."""

    parser = build_parser()
    fake = parser.parse_args(["--config", "config.fake.yaml", "--fake-usb", "--dry-run"])
    if not fake.fake_usb or not fake.dry_run:
        raise AssertionError(f"fake dry-run options were not parsed: {fake!r}")
    real = parser.parse_args(["--config", "config.yaml", "--yes"])
    if real.fake_usb or not real.yes:
        raise AssertionError(f"real apply options were not parsed: {real!r}")


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("loads enabled serial services", test_loads_only_enabled_serial_services),
    ("identifies unplug/replug devices", test_identifies_unplugged_then_replugged_devices),
    ("rejects ambiguous unplug", test_rejects_ambiguous_unplug),
    ("surgical config update and backup", test_surgical_config_update_and_backup),
    ("CLI modes", test_cli_modes),
]


def main() -> None:
    """Run USB setup tests without requiring real hardware or pseudo-terminals."""

    print("Running USB setup helper tests")
    passed = 0
    for name, test in TESTS:
        try:
            test()
        except Exception as error:
            print(f"[FAIL] {name}: {type(error).__name__}: {error}")
            continue
        print(f"[PASS] {name}")
        passed += 1
    print(f"Summary: {passed}/{len(TESTS)} passed")
    if passed != len(TESTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
