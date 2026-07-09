from pathlib import Path
import json
import sys
import uuid

import yaml


sys.dont_write_bytecode = True

REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_homeassistant.model import GeneratorOptions, GeneratorPaths, build_render_model
from labpulse_homeassistant.render import render_all


def assert_equal(actual: object, expected: object, label: str) -> None:
    """Raise AssertionError when two values differ."""

    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def sample_config() -> dict[str, object]:
    """Return a minimal LabPulse config with one enabled service."""

    return {
        "services": {
            "pressure_monitor": {
                "enabled": True,
                "device_name": "Air Pressure Sensor Hub",
                "display": {"section": "Air Pressure", "icon": "mdi:gauge", "order": 40},
                "readings": [
                    {
                        "name": "pressure",
                        "label": "Pressure",
                        "unit": "bar",
                    }
                ],
            }
        }
    }


def render_into(temp_dir: Path, reset_dashboard: bool) -> GeneratorPaths:
    """Render sample Home Assistant files into a temporary directory."""

    temp_dir.mkdir(parents=True, exist_ok=True)
    config_path = temp_dir / "config.yaml"
    config_path.write_text(yaml.safe_dump(sample_config(), sort_keys=False), encoding="utf-8")
    paths = GeneratorPaths(config_path=config_path, ha_config_dir=temp_dir / "homeassistant" / "config")
    render_all(paths, GeneratorOptions(reset_dashboard=reset_dashboard), build_render_model(sample_config()))
    return paths


def test_generated_package_and_entity_map() -> None:
    """Check generated YAML contains stable entities and binary alarm sensors."""

    temp_root = REFACTOR_DIR / "testing" / "tmp"
    temp_root.mkdir(exist_ok=True)
    paths = render_into(temp_root / f"generator-{uuid.uuid4().hex}", reset_dashboard=True)
    package = yaml.safe_load(paths.package_path.read_text(encoding="utf-8"))
    entity_map = yaml.safe_load(paths.entity_map_path.read_text(encoding="utf-8"))
    configuration = paths.configuration_path.read_text(encoding="utf-8")

    assert "automation: !include automations.yaml" in configuration
    assert "script: !include scripts.yaml" in configuration
    assert "scene: !include scenes.yaml" in configuration
    assert_equal(paths.ui_automations_path.read_text(encoding="utf-8"), "[]\n", "empty UI automations")
    assert_equal(paths.ui_scripts_path.read_text(encoding="utf-8"), "[]\n", "empty UI scripts")
    assert_equal(paths.ui_scenes_path.read_text(encoding="utf-8"), "[]\n", "empty UI scenes")
    assert "labpulse_pressure_monitor_pressure_minimum_threshold" in package["input_number"]
    assert "labpulse_pressure_monitor_pressure_maximum_threshold" in package["input_number"]
    assert "labpulse_pressure_monitor_pressure_alert_active" in package["input_boolean"]
    assert_equal(
        package["input_number"]["labpulse_pressure_monitor_pressure_minimum_threshold"]["initial"],
        1,
        "minimum threshold initial",
    )
    alarm_sensor = package["template"][0]["binary_sensor"][0]
    assert_equal(alarm_sensor["name"], "labpulse_pressure_monitor_pressure_alarm", "alarm name")
    assert_equal(alarm_sensor["unique_id"], "labpulse_pressure_monitor_pressure_alarm", "alarm unique id")
    if "{{ states(" not in alarm_sensor["state"]:
        raise AssertionError("alarm seed should preserve Home Assistant Jinja")
    if "maximum_threshold" not in alarm_sensor["state"]:
        raise AssertionError("alarm state should check maximum threshold")
    assert_equal(
        package["automation"][0]["trigger"][0]["entity_id"],
        "binary_sensor.labpulse_pressure_monitor_pressure_alarm",
        "alert trigger entity",
    )
    if "{{ states(" not in package["automation"][0]["trigger"][0]["for"]["seconds"]:
        raise AssertionError("automation delay should preserve Home Assistant Jinja")
    assert_equal(
        package["automation"][0]["condition"][0]["entity_id"],
        "input_boolean.labpulse_pressure_monitor_pressure_alert_active",
        "alert active condition entity",
    )
    assert_equal(package["automation"][0]["condition"][0]["state"], "off", "alert active condition")
    assert_equal(package["automation"][0]["action"][0]["service"], "input_boolean.turn_on", "alert toggles memory")
    assert_equal(package["automation"][1]["condition"][0]["state"], "on", "recovery active condition")
    assert_equal(package["automation"][1]["action"][0]["service"], "input_boolean.turn_off", "recovery clears memory")
    assert_equal(
        entity_map["pressure_monitor"]["pressure"]["expected_entity_id"],
        "sensor.labpulse_pressure_monitor_pressure",
        "entity map sensor",
    )
    assert_equal(
        entity_map["pressure_monitor"]["pressure"]["active_alert"],
        "input_boolean.labpulse_pressure_monitor_pressure_alert_active",
        "entity map active alert",
    )


def test_dashboard_reset_and_preserve() -> None:
    """Check no-flag rendering preserves dashboard storage exactly."""

    temp_root = REFACTOR_DIR / "testing" / "tmp"
    temp_root.mkdir(exist_ok=True)
    temp_dir = temp_root / f"generator-{uuid.uuid4().hex}"
    paths = render_into(temp_dir, reset_dashboard=True)
    first_dashboard = json.loads(paths.lovelace_path.read_text(encoding="utf-8"))
    assert_equal(first_dashboard["data"]["config"]["views"][0]["title"], "LabPulse", "dashboard title")
    pressure_cards = first_dashboard["data"]["config"]["views"][0]["sections"][1]["cards"]
    assert_equal(pressure_cards[2]["name"], "Pressure", "short reading tile name")
    assert_equal(pressure_cards[2]["grid_options"]["columns"], 6, "reading half width")
    assert_equal(pressure_cards[3]["name"], "Alarm", "short alarm tile name")
    assert_equal(pressure_cards[3]["grid_options"]["columns"], 6, "alarm half width")
    assert_equal(pressure_cards[-1]["title"], "Air Pressure Sensor Hub Alert Memory", "memory card title")

    edited_dashboard = '{"edited": true}'
    paths.lovelace_path.write_text(edited_dashboard, encoding="utf-8")
    paths.ui_automations_path.write_text("- id: user_automation\n", encoding="utf-8")
    render_into(temp_dir, reset_dashboard=False)
    assert_equal(paths.lovelace_path.read_text(encoding="utf-8"), edited_dashboard, "preserved dashboard")
    assert_equal(
        paths.ui_automations_path.read_text(encoding="utf-8"),
        "- id: user_automation\n",
        "preserved UI automations",
    )

    render_into(temp_dir, reset_dashboard=True)
    reset_dashboard = json.loads(paths.lovelace_path.read_text(encoding="utf-8"))
    assert_equal(reset_dashboard["key"], "lovelace", "reset dashboard")


TESTS = [
    ("generated package and entity map", test_generated_package_and_entity_map),
    ("dashboard reset and preserve", test_dashboard_reset_and_preserve),
]


def main() -> None:
    """Run Home Assistant generator tests."""

    print("Running Home Assistant generator tests")
    print(f"Refactor dir: {REFACTOR_DIR}")
    print()

    passed_count = 0

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
        passed_count += 1

    total = len(TESTS)
    failed_count = total - passed_count

    print(f"Summary: {passed_count}/{total} passed, {failed_count} failed")

    if failed_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
