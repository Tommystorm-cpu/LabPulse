"""Integration checks for generated deployment files after the package move."""

from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
import shutil
import sys
from typing import Callable
from uuid import uuid4

import pytest
import yaml



REFACTOR_DIR = Path(__file__).resolve().parents[1]
TEST_TMP_DIR = REFACTOR_DIR / "testing" / "tmp"

from labpulse import __version__
from labpulse.common.config import load_config
from labpulse.deployment.compose import build_compose
from labpulse.deployment.mosquitto import (
    build_mosquitto_config,
    validate_external_mqtt_files,
)
from labpulse.homeassistant.generator import main as generate_homeassistant


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


def test_external_mqtt_listener_is_secure_and_explicitly_published() -> None:
    """Generate a TLS/authenticated broker endpoint only when configured."""

    TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
    with temporary_test_directory("external-mqtt") as project_dir:
        config_path = project_dir / "config.yaml"
        config_path.write_text(
            """mqtt:
  broker: mosquitto
  external_listener:
    enabled: true
    bind_addresses: [10.50.1.1, 10.50.2.1]
    port: 9443
sms: {dry_run: true}
setups: {monitor: {}}
services:
  hub:
    label: Hub
    driver:
      type: labpulse.serial_pipe
      options: {port: /tmp/hub}
    measurements:
      pressure: {setups: [monitor]}
""",
            encoding="utf-8",
        )
        document = load_config(config_path)
        config_dir = project_dir / "mosquitto" / "config"
        for relative_path in (
            "certs/server.crt",
            "certs/server.key",
            "external-passwords",
            "external-acl",
        ):
            path = config_dir / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture", encoding="utf-8")

        validate_external_mqtt_files(document, project_dir)
        compose = compose_document(config_path, project_dir, force_simulated=False)
        assert compose["services"]["mosquitto"]["ports"] == [
            "127.0.0.1:1883:1883",
            "10.50.1.1:9443:8883",
            "10.50.2.1:9443:8883",
        ]
        broker = build_mosquitto_config(document)
        assert "listener 1883\nallow_anonymous true" in broker
        assert "listener 8883\nallow_anonymous false" in broker
        assert "password_file /mosquitto/config/external-passwords" in broker
        assert "acl_file /mosquitto/config/external-acl" in broker
        assert "certfile /mosquitto/config/certs/server.crt" in broker


def test_external_mqtt_listener_refuses_missing_secrets() -> None:
    """Fail generation before exposing a listener with missing TLS/auth files."""

    TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
    with temporary_test_directory("external-mqtt-missing") as project_dir:
        config_path = project_dir / "config.yaml"
        config_path.write_text(
            """mqtt:
  broker: mosquitto
  external_listener: {enabled: true}
sms: {dry_run: true}
setups: {}
services: {}
""",
            encoding="utf-8",
        )
        document = load_config(config_path)

        with pytest.raises(ValueError, match="required TLS/authentication files are missing"):
            validate_external_mqtt_files(document, project_dir)


def test_default_mqtt_listener_remains_loopback_only() -> None:
    """Existing installations must not gain an external broker endpoint."""

    document = load_config(REFACTOR_DIR / "config.yaml")
    compose = build_compose(
        document,
        config_mount_source="./config.yaml",
        runtime_image="labpulse:test",
        force_simulated=False,
    )
    payload = yaml.safe_load(compose)
    assert payload["services"]["mosquitto"]["ports"] == ["127.0.0.1:1883:1883"]
    assert "listener 8883" not in build_mosquitto_config(document)


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
            "System Status",
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


def test_generic_gpio_compose_is_least_privilege() -> None:
    """Expose only the selected GPIO chip to a generic input service."""

    TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
    project_dir = TEST_TMP_DIR / f"gpio-deployment-{uuid4().hex}"
    project_dir.mkdir()
    try:
        config_path = project_dir / "config.yaml"
        config_path.write_text(
            """mqtt: {broker: mosquitto}
sms: {dry_run: true}
setups:
  equipment: {}
services:
  equipment_running:
    label: Equipment Running
    driver:
      type: labpulse.gpio_input
      options:
        gpio_chip: /dev/gpiochip2
    measurements:
      pin_17:
        setups: [equipment]
        state_class: null
        gpio_line: 17
""",
            encoding="utf-8",
        )
        compose = compose_document(config_path, project_dir, force_simulated=False)
        service = compose["services"]["labpulse-equipment-running"]
        if service.get("devices") != ["/dev/gpiochip2:/dev/gpiochip2"]:
            raise AssertionError(f"unexpected GPIO device mapping: {service.get('devices')!r}")
        if service.get("privileged") is True or "/dev:/dev" in service.get("volumes", []):
            raise AssertionError("generic GPIO service received broad device privileges")
    finally:
        for path in sorted(project_dir.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        project_dir.rmdir()


def test_gpio_output_compose_is_isolated_and_omitted_in_fake_mode() -> None:
    """Run one least-privilege output worker only in real-hardware mode."""

    TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
    project_dir = TEST_TMP_DIR / f"gpio-output-deployment-{uuid4().hex}"
    project_dir.mkdir()
    try:
        config_path = project_dir / "config.yaml"
        config_path.write_text(
            """mqtt: {broker: mosquitto}
sms: {dry_run: true}
setups:
  monitor: {}
services:
  monitor:
    label: Monitor
    driver:
      type: labpulse.serial_pipe
      options: {port: /tmp/monitor}
    measurements:
      value: {setups: [monitor]}
outputs:
  cooling_valve_enable:
    label: Cooling Valve Enable
    driver:
      type: labpulse.gpio_output
      options:
        gpio_chip: /dev/gpiochip2
        gpio_line: 18
        active_high: true
        safe_state: false
    maximum_active_seconds: 300
""",
            encoding="utf-8",
        )
        compose = compose_document(config_path, project_dir, force_simulated=False)
        output = compose["services"]["labpulse-output-cooling-valve-enable"]
        if output["command"] != [
            "python",
            "-m",
            "labpulse.output",
            "--config",
            "/app/config.yaml",
            "--output",
            "cooling_valve_enable",
        ]:
            raise AssertionError(f"unexpected output command: {output['command']!r}")
        if output.get("devices") != ["/dev/gpiochip2:/dev/gpiochip2"]:
            raise AssertionError(f"unexpected output device mapping: {output.get('devices')!r}")
        if output.get("privileged") is True or "/dev:/dev" in output.get("volumes", []):
            raise AssertionError("GPIO output received broad device privileges")

        fake_compose = compose_document(config_path, project_dir, force_simulated=True)
        if "labpulse-output-cooling-valve-enable" in fake_compose["services"]:
            raise AssertionError("fake-USB mode retained a physical actuator worker")
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
