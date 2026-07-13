"""Integration checks for generated deployment files after the package move."""

from pathlib import Path
import subprocess
import sys
from typing import Callable
from uuid import uuid4

import yaml


sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
TEST_TMP_DIR = REFACTOR_DIR / "testing" / "tmp"


def embedded_compose_generator() -> str:
    """Return the Python generator embedded in generate_compose.sh."""

    shell_source = (REFACTOR_DIR / "generate_compose.sh").read_text(encoding="utf-8")
    marker = "<<'PY'\n"
    if marker not in shell_source:
        marker = "<<'PY'\r\n"
    generator = shell_source.split(marker, 1)[1]
    return generator.rsplit("\nPY", 1)[0]


def test_fake_usb_compose_contract() -> None:
    """Generate fake-USB Compose and verify stable names, mounts, and commands."""

    TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
    project_dir = TEST_TMP_DIR / f"deployment-{uuid4().hex}"
    project_dir.mkdir()
    try:
        config_path = project_dir / "config.yaml"
        output_path = project_dir / "compose.yaml"
        config_path.write_text(
            """mqtt:
  broker: mosquitto
  port: 1883
sms:
  backend: log
services:
  pressure_monitor:
    enabled: true
    serial_port: /tmp/labpulse-fake-serial/pressure
  disabled_hub:
    enabled: false
""",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                embedded_compose_generator(),
                str(config_path),
                str(output_path),
                str(project_dir),
                "1",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)

        compose = yaml.safe_load(output_path.read_text(encoding="utf-8"))
        services = compose["services"]
        expected_names = {
            "homeassistant",
            "mosquitto",
            "labpulse-sms",
            "labpulse-pressure-monitor",
        }
        if set(services) != expected_names:
            raise AssertionError(f"unexpected Compose services: {set(services)!r}")

        hardware = services["labpulse-pressure-monitor"]
        if hardware["command"] != [
            "python",
            "-m",
            "labpulse_hardware",
            "--service",
            "pressure_monitor",
        ]:
            raise AssertionError(f"unexpected hardware command: {hardware['command']!r}")

        sms = services["labpulse-sms"]
        if sms["command"] != [
            "python",
            "-m",
            "labpulse_sms",
            "--config",
            "/app/config.yaml",
        ]:
            raise AssertionError(f"unexpected SMS command: {sms['command']!r}")

        base_mounts = compose["x-labpulse-python-base"]["volumes"]
        for mount in (
            "/tmp/labpulse-fake-serial:/tmp/labpulse-fake-serial",
            "/tmp/labpulse-fake-dht11:/tmp/labpulse-fake-dht11",
            "/dev/pts:/dev/pts",
        ):
            if mount not in base_mounts:
                raise AssertionError(f"missing fake-USB mount: {mount}")
    finally:
        # Keep cleanup simple and local; repository-wide test cleanup also
        # removes testing/tmp after the full suite.
        for path in sorted(project_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        project_dir.rmdir()


def test_setup_refresh_and_preservation_contract() -> None:
    """Check bootstrap copies all packages and guards user-owned live files."""

    source = (REFACTOR_DIR / "setup_container_fs.sh").read_text(encoding="utf-8")
    required_fragments = (
        'replace_dir "$SCRIPT_DIR/labpulse_common"',
        'replace_dir "$SCRIPT_DIR/labpulse_hardware"',
        'replace_dir "$SCRIPT_DIR/labpulse_sms"',
        'if [ ! -e "$LIVE_CONFIG" ]; then',
        'Preserving existing live config',
        'rm -f "$PROJECT_DIR/labpulse-python/main.py"',
        'mkdir -p /tmp/labpulse-fake-dht11',
        'gpio_sensor: fake_dht11',
        'adafruit-circuitpython-dht',
        'adafruit-blinka',
        'lgpio',
    )
    for fragment in required_fragments:
        if fragment not in source:
            raise AssertionError(f"setup contract missing: {fragment}")

    generator_source = (
        REFACTOR_DIR / "generate_homeassistant_config.sh"
    ).read_text(encoding="utf-8")
    if '--reset-dashboard' not in generator_source or 'RESET_DASHBOARD=0' not in generator_source:
        raise AssertionError("Home Assistant wrapper no longer exposes dashboard preservation")


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("fake USB Compose contract", test_fake_usb_compose_contract),
    ("setup refresh and preservation contract", test_setup_refresh_and_preservation_contract),
]


def main() -> None:
    """Run deployment generation tests without requiring Docker or physical USB."""

    print("Running deployment generation tests")
    print(f"Refactor dir: {REFACTOR_DIR}")
    print()

    passed = 0
    for name, test_func in TESTS:
        try:
            test_func()
        except Exception as error:
            print(f"[FAIL] {name}")
            print(f"  error: {type(error).__name__}: {error}")
            print()
            continue
        print(f"[PASS] {name}")
        print()
        passed += 1

    failed = len(TESTS) - passed
    print(f"Summary: {passed}/{len(TESTS)} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
