"""Integration checks for generated deployment files after the package move."""

from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Callable
from uuid import uuid4

import yaml


sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
TEST_TMP_DIR = REFACTOR_DIR / "testing" / "tmp"
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_homeassistant.cli import main as generate_homeassistant


@contextmanager
def test_directory(prefix: str) -> Iterator[Path]:
    """Create and remove one accessible, uniquely named test directory."""

    root = TEST_TMP_DIR / f"{prefix}-{uuid4().hex}"
    root.mkdir()
    try:
        yield root
    finally:
        shutil.rmtree(root)


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
        config_path = project_dir / "config.fake.yaml"
        output_path = project_dir / "compose.yaml"
        config_path.write_text(
            """mqtt:
  broker: mosquitto
  port: 1883
sms:
  dry_run: true
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
        if sms.get("privileged") is True:
            raise AssertionError("dry-run SMS worker unexpectedly has privileged access")
        if "/run/dbus:/run/dbus:ro" in sms["volumes"]:
            raise AssertionError("dry-run SMS worker unexpectedly has the D-Bus mount")

        hardware_mounts = hardware["volumes"]
        for mount in (
            "/tmp/labpulse-fake-serial:/tmp/labpulse-fake-serial",
            "/dev/pts:/dev/pts",
        ):
            if mount not in hardware_mounts:
                raise AssertionError(f"missing fake-USB mount: {mount}")
        if hardware.get("privileged") is True or hardware.get("devices"):
            raise AssertionError("fake serial service unexpectedly has real-device access")
        expected_config_mount = "./config.fake.yaml:/app/config.yaml:ro"
        if expected_config_mount not in hardware_mounts:
            raise AssertionError("fake hardware does not mount the derived runtime config")
        if expected_config_mount not in sms["volumes"]:
            raise AssertionError("fake SMS worker does not mount the derived runtime config")
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
        'copy_file "$SCRIPT_DIR/simulate_serial.py"',
        'copy_file "$SCRIPT_DIR/setup_usb_devices.py"',
        'if [ ! -e "$LIVE_CONFIG" ]; then',
        'Preserving existing live config',
        'rm -f "$PROJECT_DIR/labpulse-python/main.py"',
        'serial_port: "/tmp/labpulse-fake-serial/room_environment"',
        'parser: pipe',
        'adafruit-circuitpython-dht',
        'adafruit-blinka',
        'lgpio',
        'smbus2',
        'gpiod modemmanager',
        '"FAKE_UPS_PORT": "/tmp/labpulse-fake-serial/ups_monitor"',
        'convert_power_service_to_fake_serial',
        'RUNTIME_CONFIG="$PROJECT_DIR/config.fake.yaml"',
        '--config "$RUNTIME_CONFIG"',
        'including UPS power',
        '$PROJECT_DIR/homeassistant/config/labpulse-dashboard.yaml',
    )
    for fragment in required_fragments:
        if fragment not in source:
            raise AssertionError(f"setup contract missing: {fragment}")
    if "alarm_defaults.json" in source:
        raise AssertionError("setup still deploys the removed alarm defaults file")
    generator_source = (
        REFACTOR_DIR / "generate_homeassistant_config.sh"
    ).read_text(encoding="utf-8")
    required_generator_fragments = (
        'homeassistant/config/labpulse-dashboard.yaml',
        'Generation is offline',
    )
    for fragment in required_generator_fragments:
        if fragment not in generator_source:
            raise AssertionError(f"Home Assistant wrapper contract missing: {fragment}")
    forbidden_generator_fragments = (
        "alarm_defaults.json",
        ".storage",
        "lovelace_dashboards",
        "dashboard_storage_path",
        "--reset-dashboard",
        "--backup-dashboard",
        "--load-dashboard",
        "--sync-dashboard-entities",
        "homeassistant_backups",
        "--resolve-entities",
        "--ha-url",
        "LABPULSE_HA_TOKEN",
        "LABPULSE_HA_URL",
    )
    for fragment in forbidden_generator_fragments:
        if fragment in generator_source:
            raise AssertionError(f"legacy dashboard wrapper code remains: {fragment}")


def test_offline_dashboard_generation_is_deterministic() -> None:
    """Regenerate only owned files offline while preserving UI and helper state."""

    TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
    with test_directory("ha-offline") as root:
        config_path = root / "config.yaml"
        config_path.write_text(
            (REFACTOR_DIR / "config.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        ha_dir = root / "homeassistant" / "config"
        restore_state = ha_dir / ".storage" / "core.restore_state"
        restore_state.parent.mkdir(parents=True)
        restore_state.write_text('{"helper_values": "user-owned"}\n', encoding="utf-8")

        result = generate_homeassistant(
            ["generator", str(config_path), str(ha_dir)]
        )
        if result != 0:
            raise AssertionError("clean offline generation failed")

        generated_names = (
            "configuration.yaml",
            "labpulse-dashboard.yaml",
            "labpulse_entity_map.yaml",
            "packages/labpulse_generated.yaml",
        )
        first = {
            name: (ha_dir / name).read_bytes()
            for name in generated_names
        }
        dashboard = yaml.safe_load(
            (ha_dir / "labpulse-dashboard.yaml").read_text(encoding="utf-8")
        )
        visible_views = [
            view for view in dashboard["views"] if not view.get("subview")
        ]
        if [view["title"] for view in visible_views] != [
            "Monitor",
            "Alarm Setup",
            "Diagnostics",
        ]:
            raise AssertionError("offline visible dashboard view contract changed")
        subviews = [view for view in dashboard["views"] if view.get("subview")]
        if not subviews or any(
            view.get("back_path") != "/labpulse-monitor/alarm-setup"
            for view in subviews
        ):
            raise AssertionError("offline alarm subview contract changed")

        ui_markers = {
            "automations.yaml": "- id: user-owned-automation\n",
            "scripts.yaml": "user_owned_script: {}\n",
            "scenes.yaml": "- id: user-owned-scene\n",
        }
        for name, content in ui_markers.items():
            (ha_dir / name).write_text(content, encoding="utf-8")
        (ha_dir / "labpulse-dashboard.yaml").write_text(
            "user edit that must be regenerated\n", encoding="utf-8"
        )

        result = generate_homeassistant(
            ["generator", str(config_path), str(ha_dir)]
        )
        if result != 0:
            raise AssertionError("offline regeneration failed")
        for name, expected in first.items():
            if (ha_dir / name).read_bytes() != expected:
                raise AssertionError(f"generated output is not deterministic: {name}")
        for name, expected in ui_markers.items():
            if (ha_dir / name).read_text(encoding="utf-8") != expected:
                raise AssertionError(f"regeneration replaced UI-owned {name}")
        if restore_state.read_text(encoding="utf-8") != '{"helper_values": "user-owned"}\n':
            raise AssertionError("regeneration changed Home Assistant helper state")


def test_fake_test_pi_dashboard_generation() -> None:
    """Generate the fake UPS test-Pi dashboard without hardware or Home Assistant."""

    TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
    with test_directory("ha-test-pi") as root:
        config_path = root / "config.yaml"
        config_path.write_text(
            (REFACTOR_DIR / "testing" / "ups_test_pi_config.yaml").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        ha_dir = root / "homeassistant" / "config"
        result = generate_homeassistant(
            ["generator", str(config_path), str(ha_dir)]
        )
        if result != 0:
            raise AssertionError("fake test-Pi generation failed")
        rendered = (ha_dir / "labpulse-dashboard.yaml").read_text(encoding="utf-8")
        for expected in (
            "UPS Monitor",
            "Power Monitoring",
            "Power Lifecycle",
            "sensor.labpulse_ups_monitor_voltage",
        ):
            if expected not in rendered:
                raise AssertionError(f"fake test-Pi dashboard lacks {expected}")

def test_real_x1200_compose_is_least_privilege() -> None:
    """Expose only configured I2C and GPIO nodes to the X1200 service."""

    TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
    project_dir = TEST_TMP_DIR / f"i2c-deployment-{uuid4().hex}"
    project_dir.mkdir()
    try:
        config_path = project_dir / "config.yaml"
        output_path = project_dir / "compose.yaml"
        config_path.write_text(
            """mqtt: {broker: mosquitto}
sms: {dry_run: true}
services:
  ups_monitor:
    enabled: true
    driver: i2c
    i2c_bus: 1
    power_detection:
      source: x1200_gpio
      gpio_chip: /dev/gpiochip0
""",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, "-c", embedded_compose_generator(), str(config_path), str(output_path), str(project_dir), "0"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr or result.stdout)
        service = yaml.safe_load(output_path.read_text(encoding="utf-8"))["services"]["labpulse-ups-monitor"]
        if service.get("devices") != [
            "/dev/i2c-1:/dev/i2c-1",
            "/dev/gpiochip0:/dev/gpiochip0",
        ]:
            raise AssertionError(f"unexpected X1200 device mapping: {service.get('devices')!r}")
        if service.get("privileged") is True or "/dev:/dev" in service.get("volumes", []):
            raise AssertionError("I2C service received broad device privileges")
    finally:
        for path in sorted(project_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        project_dir.rmdir()


def test_sms_delivery_mode_controls_modem_access() -> None:
    """Give only real-delivery SMS workers the modem-specific Compose settings."""

    TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
    project_dir = TEST_TMP_DIR / f"sms-deployment-{uuid4().hex}"
    project_dir.mkdir()
    try:
        config_path = project_dir / "config.yaml"
        output_path = project_dir / "compose.yaml"
        config_path.write_text(
            """mqtt:
  broker: mosquitto
sms:
  dry_run: false
  recipients:
    - "+447700900000"
services:
  pressure_monitor:
    enabled: true
    serial_port: /tmp/labpulse-fake-serial/pressure
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

        sms = yaml.safe_load(output_path.read_text(encoding="utf-8"))["services"][
            "labpulse-sms"
        ]
        if sms.get("privileged") is not True:
            raise AssertionError("real SMS delivery is missing privileged modem access")
        for mount in ("/run/dbus:/run/dbus:ro", "/dev:/dev"):
            if mount not in sms["volumes"]:
                raise AssertionError(f"real SMS delivery is missing mount: {mount}")
    finally:
        for path in sorted(project_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        project_dir.rmdir()


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("fake USB Compose contract", test_fake_usb_compose_contract),
    ("real X1200 Compose least privilege", test_real_x1200_compose_is_least_privilege),
    ("SMS delivery mode controls modem access", test_sms_delivery_mode_controls_modem_access),
    ("setup refresh and preservation contract", test_setup_refresh_and_preservation_contract),
    ("deterministic offline HA generation", test_offline_dashboard_generation_is_deterministic),
    ("fake test-Pi dashboard generation", test_fake_test_pi_dashboard_generation),
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
