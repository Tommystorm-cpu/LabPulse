"""Integration checks for generated deployment files after the package move."""

from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
import shutil
import sys
from typing import Callable
from uuid import uuid4

import yaml



REFACTOR_DIR = Path(__file__).resolve().parents[1]
TEST_TMP_DIR = REFACTOR_DIR / "testing" / "tmp"

from labpulse import __version__
from labpulse.common.config import load_config
from labpulse.deployment.compose import build_compose
from labpulse.homeassistant.cli import main as generate_homeassistant


@contextmanager
def temporary_test_directory(prefix: str) -> Iterator[Path]:
    """Create and remove one accessible, uniquely named test directory."""

    root = TEST_TMP_DIR / f"{prefix}-{uuid4().hex}"
    root.mkdir()
    try:
        yield root
    finally:
        shutil.rmtree(root)


def compose_document(
    config_path: Path,
    project_dir: Path,
    *,
    force_simulated: bool,
    runtime_image: str | None = None,
) -> dict[str, object]:
    """Build and decode Compose directly from the validated Python generator."""

    document = load_config(config_path)
    compose_text = build_compose(
        document,
        config_mount_source="./" + config_path.relative_to(project_dir).as_posix(),
        runtime_image=(
            runtime_image or f"ghcr.io/tommystorm-cpu/labpulse:{__version__}"
        ),
        force_simulated=force_simulated,
    )
    payload = yaml.safe_load(compose_text)
    if not isinstance(payload, dict):
        raise AssertionError("Compose generator did not return a mapping")
    return payload


def test_fake_usb_compose_contract() -> None:
    """Generate fake-USB Compose and verify stable names, mounts, and commands."""

    TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
    project_dir = TEST_TMP_DIR / f"deployment-{uuid4().hex}"
    project_dir.mkdir()
    try:
        config_path = project_dir / "config.fake.yaml"
        config_path.write_text(
            """mqtt:
  broker: mosquitto
  port: 1883
sms:
  dry_run: true
setups:
  monitor: {}
services:
  pressure_monitor:
    label: Pressure Monitor
    driver:
      type: labpulse.serial_pipe
      options:
        port: /tmp/labpulse-fake-serial/pressure
    measurements:
      pressure:
        setups: [monitor]
  disabled_hub:
    enabled: false
    label: Disabled Hub
    driver:
      type: labpulse.serial_pipe
      options:
        port: /tmp/labpulse-fake-serial/disabled
    measurements:
      unused:
        setups: [monitor]
""",
            encoding="utf-8",
        )

        compose = compose_document(config_path, project_dir, force_simulated=True)
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
        expected_image = f"ghcr.io/tommystorm-cpu/labpulse:{__version__}"
        if hardware.get("image") != expected_image:
            raise AssertionError(
                f"hardware image is not version-coupled: {hardware.get('image')!r}"
            )
        if hardware["command"] != [
            "python",
            "-m",
            "labpulse.hardware",
            "--config",
            "/app/config.yaml",
            "--service",
            "pressure_monitor",
        ]:
            raise AssertionError(f"unexpected hardware command: {hardware['command']!r}")

        sms = services["labpulse-sms"]
        if sms.get("image") != expected_image:
            raise AssertionError(
                f"SMS image is not version-coupled: {sms.get('image')!r}"
            )
        if sms["command"] != [
            "python",
            "-m",
            "labpulse.sms",
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
        for service_name in (
            "homeassistant",
            "mosquitto",
            "labpulse-sms",
            "labpulse-pressure-monitor",
        ):
            if "/etc/localtime:/etc/localtime:ro" not in services[service_name].get(
                "volumes", []
            ):
                raise AssertionError(
                    f"{service_name} does not inherit the host timezone"
                )
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

    source = (REFACTOR_DIR / "deployment" / "setup_container_fs.sh").read_text(
        encoding="utf-8"
    )
    starter = yaml.safe_load(
        (REFACTOR_DIR / "config.yaml").read_text(encoding="utf-8")
    )
    if starter["mqtt"]["broker"] != "mosquitto":
        raise AssertionError("starter config must use the Compose MQTT service name")
    if "text.replace('broker:" in source or 'text.replace("broker:' in source:
        raise AssertionError("setup must not rewrite the user-owned MQTT broker")
    required_fragments = (
        'PACKAGE_PARENT="${LABPULSE_PACKAGE_PARENT:-$ASSET_DIR/src}"',
        "labpulse-installed-package.pth",
        "Linked managed Python to installed LabPulse",
        "from labpulse import __version__",
        'copy_file "$ASSET_DIR/simulate_serial.py"',
        'copy_file "$ASSET_DIR/setup_usb_devices.py"',
        'copy_file "$ASSET_DIR/deployment/edit_config.sh"',
        'copy_file "$ASSET_DIR/testing/real_hardware/hardware_fault_common.sh"',
        'copy_file "$ASSET_DIR/testing/real_hardware/test_x1200_faults.sh"',
        'copy_file "$ASSET_DIR/testing/real_hardware/test_dht11_fault.sh"',
        'copy_file "$HOST_REQUIREMENTS_SOURCE" "$HOST_REQUIREMENTS"',
        'python3 -m venv "$HOST_VENV"',
        '"$HOST_PYTHON" -m pip install',
        "LabPulse requires Pydantic 2",
        'if [ ! -e "$LIVE_CONFIG" ]; then',
        'Preserving existing live config',
        'Real setup never rewrites the',
        'derive_fake_config',
        'RUNTIME_CONFIG="$PROJECT_DIR/config.fake.yaml"',
        '--config "$RUNTIME_CONFIG"',
        "labpulse.deployment",
        'including UPS power',
        '$PROJECT_DIR/homeassistant/config/labpulse-dashboard.yaml',
    )
    for fragment in required_fragments:
        if fragment not in source:
            raise AssertionError(f"setup contract missing: {fragment}")
    for forbidden in (
        "labpulse-python",
        "COPY labpulse ./labpulse",
        'replace_dir "$PACKAGE_SOURCE"',
    ):
        if forbidden in source:
            raise AssertionError(f"obsolete local image build remains: {forbidden}")
    if "alarm_defaults.json" in source:
        raise AssertionError("setup still deploys the removed alarm defaults file")

    x1200_fault_source = (
        REFACTOR_DIR / "testing" / "real_hardware" / "test_x1200_faults.sh"
    ).read_text(encoding="utf-8")
    for fragment in (
        "block-i2c|block-gpio|block-all|restore|status",
        "devices: !override",
        "devices: !reset []",
        "source: /dev/null",
        'fault_restore_service "$OVERRIDE_FILE" "$COMPOSE_SERVICE"',
        'driver.get("type") != "labpulse.x1200"',
    ):
        if fragment not in x1200_fault_source:
            raise AssertionError(f"X1200 fault script contract missing: {fragment}")

    dht11_fault_source = (
        REFACTOR_DIR / "testing" / "real_hardware" / "test_dht11_fault.sh"
    ).read_text(encoding="utf-8")
    for fragment in (
        "block|restore|status",
        "privileged: false",
        'service["driver"]["options"]["pin"] = "D999999"',
        "target: /app/config.yaml",
        'fault_restore_service "$OVERRIDE_FILE" "$COMPOSE_SERVICE" 5',
        'driver.get("type") != "labpulse.dht11"',
    ):
        if fragment not in dht11_fault_source:
            raise AssertionError(f"DHT11 fault script contract missing: {fragment}")
    generator_source = (
        REFACTOR_DIR / "deployment" / "generate_homeassistant_config.sh"
    ).read_text(encoding="utf-8")
    compose_source = (
        REFACTOR_DIR / "deployment" / "generate_compose.sh"
    ).read_text(encoding="utf-8")
    for fragment in (
        'HOST_PYTHON="${LABPULSE_PYTHON:-$PROJECT_DIR/.venv/bin/python}"',
        '"$HOST_PYTHON" -m labpulse.deployment',
        '--config "$CONFIG_PATH"',
        '--output "$OUTPUT_PATH"',
    ):
        if fragment not in compose_source:
            raise AssertionError(f"Compose wrapper contract missing: {fragment}")
    required_generator_fragments = (
        'homeassistant/config/labpulse-dashboard.yaml',
        'Generation is offline',
        'HOST_PYTHON="${LABPULSE_PYTHON:-$PROJECT_DIR/.venv/bin/python}"',
        '"$HOST_PYTHON" -m labpulse.homeassistant',
    )
    for fragment in required_generator_fragments:
        if fragment not in generator_source:
            raise AssertionError(f"Home Assistant wrapper contract missing: {fragment}")
    if "PYTHONPATH=" in generator_source or "labpulse-python" in generator_source:
        raise AssertionError("Home Assistant wrapper still depends on copied source")
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

    editor_source = (REFACTOR_DIR / "deployment" / "edit_config.sh").read_text(
        encoding="utf-8"
    )
    required_editor_fragments = (
        'mktemp "$PROJECT_DIR/.config.yaml.editing.XXXXXX"',
        "labpulse.deployment",
        '--compose-output "$CHECK_DIR/compose.yaml"',
        '--ha-config-dir "$CHECK_DIR/homeassistant/config"',
        'CONFIG_BACKUP="$PROJECT_DIR/config.yaml.edit-backup"',
        '"${DOCKER_PARTS[@]}" compose config --quiet',
        "python -m homeassistant --script check_config --config /config",
        '"${DOCKER_PARTS[@]}" compose up -d --remove-orphans --force-recreate',
        'Check Monitor for "Global Mute Applied"',
        '"Test Mode Applied"',
        'ACTIVE_FAKE_USB=1',
        'from labpulse.common.fake_config import derive_fake_config',
        'RUNTIME_WORK_CONFIG="$WORK_FAKE_CONFIG"',
        'RUNTIME_CONFIG="$FAKE_CONFIG_PATH"',
        '"${COMPOSE_MODE_ARGS[@]}"',
        'DOCKER_COMMAND_TEXT="${LABPULSE_DOCKER_COMMAND:-sudo docker}"',
        'if [ -n "${VISUAL:-}" ]; then',
        'elif [ -n "${EDITOR:-}" ]; then',
        'command -v micro >/dev/null 2>&1',
        'EDITOR_COMMAND="micro"',
        'command -v nano >/dev/null 2>&1',
        'EDITOR_COMMAND="nano"',
    )
    for fragment in required_editor_fragments:
        if fragment not in editor_source:
            raise AssertionError(f"config editor contract missing: {fragment}")
    editor_priority = (
        'if [ -n "${VISUAL:-}" ]; then',
        'elif [ -n "${EDITOR:-}" ]; then',
        'command -v micro >/dev/null 2>&1',
        'command -v nano >/dev/null 2>&1',
    )
    positions = [editor_source.index(fragment) for fragment in editor_priority]
    if positions != sorted(positions):
        raise AssertionError("config editor priority is not VISUAL, EDITOR, micro, nano")


def test_offline_dashboard_generation_is_deterministic() -> None:
    """Regenerate only owned files offline while preserving UI and helper state."""

    TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
    with temporary_test_directory("ha-offline") as root:
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
            [str(config_path), str(ha_dir)]
        )
        if result != 0:
            raise AssertionError("clean offline generation failed")

        generated_names = (
            "configuration.yaml",
            "labpulse-dashboard.yaml",
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
            [str(config_path), str(ha_dir)]
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
    with temporary_test_directory("ha-test-pi") as root:
        config_path = root / "config.yaml"
        config_path.write_text(
            (REFACTOR_DIR / "testing" / "ups_test_pi_config.yaml").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )
        ha_dir = root / "homeassistant" / "config"
        result = generate_homeassistant(
            [str(config_path), str(ha_dir)]
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
        config_path.write_text(
            """mqtt: {broker: mosquitto}
sms: {dry_run: true}
setups: {}
services:
  ups_monitor:
    label: UPS Monitor
    driver:
      type: labpulse.x1200
      options:
        bus: 1
        address: 0x36
        gpio_chip: /dev/gpiochip0
        gpio_line: 6
    measurements:
      voltage: {}
      battery_level: {}
      mains_present: {}
    power_detection:
      outage_confirm_seconds: 3
      restore_confirm_seconds: 5
""",
            encoding="utf-8",
        )
        compose = compose_document(config_path, project_dir, force_simulated=False)
        service = compose["services"]["labpulse-ups-monitor"]
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
        config_path.write_text(
            """mqtt:
  broker: mosquitto
sms:
  dry_run: false
  recipients:
    - "+447700900000"
setups:
  monitor: {}
services:
  pressure_monitor:
    label: Pressure Monitor
    driver:
      type: labpulse.serial_pipe
      options:
        port: /tmp/labpulse-fake-serial/pressure
    measurements:
      pressure:
        setups: [monitor]
""",
            encoding="utf-8",
        )

        compose = compose_document(
            config_path,
            project_dir,
            force_simulated=True,
            runtime_image="local/labpulse:test",
        )
        sms = compose["services"]["labpulse-sms"]
        if sms.get("image") != "local/labpulse:test":
            raise AssertionError("LABPULSE_IMAGE override was not applied")
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
