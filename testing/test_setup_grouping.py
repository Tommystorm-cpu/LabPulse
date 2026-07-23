"""Configuration and projection tests for logical experimental setups."""

from collections.abc import Callable
from pathlib import Path
import sys

from pydantic import ValidationError


REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR / "src"))

from labpulse.common.config import LabPulseConfig, SetupConfig
from labpulse.homeassistant.measurement_catalog import MeasurementKey, build_measurement_catalog
from labpulse.homeassistant.render_model import RenderModel


def config_data() -> dict[str, object]:
    """Return a config covering single and shared explicit membership."""

    return {
        "mqtt": {"broker": "mosquitto"},
        "setups": {
            "turbo_pump": {
                "label": "Turbo Pump Experiment",
                "icon": "mdi:vacuum-outline",
                "order": 20,
            },
            "cryostat": {
                "label": "Cryostat Experiment",
                "icon": "mdi:snowflake",
                "order": 10,
            },
        },
        "services": {
            "pump_room": {
                "driver": {
                    "type": "labpulse.serial_pipe",
                    "options": {"port": "/tmp/pump-room"},
                },
                "device_name": "Pump Room Hub",
                "measurements": [
                    {
                        "name": "cryostat_only",
                        "setups": ["cryostat"],
                        "unit": "°C",
                        "device_class": "temperature",
                    },
                    {"name": "turbo", "setups": ["turbo_pump"]},
                    {
                        "name": "shared",
                        "setups": ["turbo_pump", "cryostat"],
                        "unit": "°C",
                        "device_class": "temperature",
                    },
                ],
            },
            "room_environment": {
                "driver": {
                    "type": "labpulse.dht11",
                    "options": {"pin": "D4"},
                },
                "device_name": "Room Hub",
                "measurements": [
                    {
                        "name": "temperature",
                        "setups": ["cryostat"],
                        "unit": "°F",
                        "device_class": "temperature",
                    }
                ],
            },
            "disabled": {
                "enabled": False,
                "driver": {
                    "type": "labpulse.serial_pipe",
                    "options": {"port": "/tmp/disabled"},
                },
                "device_name": "Disabled Hub",
                "measurements": [{"name": "ignored", "setups": ["cryostat"]}],
            },
        },
    }


def assert_rejected(data: dict[str, object], expected: str) -> None:
    """Require configuration rejection containing readable context."""

    try:
        LabPulseConfig.model_validate(data)
    except ValidationError as error:
        if expected not in str(error):
            raise AssertionError(f"expected {expected!r} in {error}") from error
    else:
        raise AssertionError(f"invalid configuration was accepted: {expected}")


def test_scope_normalization_and_validation() -> None:
    """Normalize explicit lists and reject missing or removed membership forms."""

    config = LabPulseConfig.model_validate(config_data())
    measurements = config.services["pump_room"].measurements
    if [item.setups.setup_ids for item in measurements if item.setups is not None] != [
        ("cryostat",),
        ("turbo_pump",),
        ("turbo_pump", "cryostat"),
    ]:
        raise AssertionError("measurement setup scopes were not normalized")

    missing_membership = config_data()
    missing_membership["services"]["pump_room"]["measurements"][0].pop("setups")
    assert_rejected(missing_membership, "setups")

    duplicate = config_data()
    duplicate["services"]["pump_room"]["measurements"][1]["setups"] = [
        "turbo_pump",
        "turbo_pump",
    ]
    assert_rejected(duplicate, "must be unique")

    unknown = config_data()
    unknown["services"]["pump_room"]["measurements"][1]["setups"] = ["missing"]
    assert_rejected(unknown, "unknown setups: missing")

    empty = config_data()
    empty["services"]["pump_room"]["measurements"][1]["setups"] = []
    assert_rejected(empty, "at least one setup ID")

    removed_none = config_data()
    removed_none["services"]["pump_room"]["measurements"][1]["setups"] = "none"
    assert_rejected(removed_none, "non-empty list")

    removed_all = config_data()
    removed_all["services"]["pump_room"]["measurements"][1]["setups"] = "all"
    assert_rejected(removed_all, "non-empty list")


def test_setup_metadata_validation() -> None:
    """Reject unstable IDs, blank labels, invalid icons, and bounded order errors."""

    if SetupConfig().display_label("unlabelled_setup") != "Unlabelled Setup":
        raise AssertionError("setup label was not inferred from its stable ID")

    invalid_id = config_data()
    invalid_id["setups"]["Turbo Pump"] = invalid_id["setups"].pop("turbo_pump")
    assert_rejected(invalid_id, "lowercase letters, numbers, and underscores")

    blank_label = config_data()
    blank_label["setups"]["turbo_pump"]["label"] = "  "
    assert_rejected(blank_label, "must not be blank")

    invalid_icon = config_data()
    invalid_icon["setups"]["turbo_pump"]["icon"] = "vacuum"
    assert_rejected(invalid_icon, "mdi: icon identifier")

    invalid_measurement_icon = config_data()
    invalid_measurement_icon["services"]["pump_room"]["measurements"][0][
        "icon"
    ] = "thermometer"
    assert_rejected(invalid_measurement_icon, "measurement icon")

    invalid_order = config_data()
    invalid_order["setups"]["turbo_pump"]["order"] = -1
    assert_rejected(invalid_order, "greater than or equal to 0")

    obsolete_display = config_data()
    obsolete_display["services"]["pump_room"]["display"] = {"order": 20}
    assert_rejected(obsolete_display, "display")

    obsolete_group = config_data()
    obsolete_group["services"]["pump_room"]["measurements"][0]["group"] = "General"
    assert_rejected(obsolete_group, "group")

    no_setups = config_data()
    no_setups["setups"] = {}
    assert_rejected(no_setups, "references unknown setups")


def test_dedicated_power_omits_setup_membership() -> None:
    """Keep dedicated power outside the experimental setup hierarchy."""

    power = {
        "mqtt": {"broker": "mosquitto"},
        "setups": {},
        "services": {
            "ups": {
                "driver": {
                    "type": "labpulse.serial_pipe",
                    "options": {"port": "/tmp/ups"},
                },
                "device_name": "UPS",
                "measurements": [
                    {"name": "voltage"},
                    {"name": "battery_level"},
                    {"name": "mains_present", "state_class": None},
                ],
                "power_detection": {},
            }
        },
    }
    config = LabPulseConfig.model_validate(power)
    if any(measurement.setups is not None for measurement in config.services["ups"].measurements):
        raise AssertionError("power measurement unexpectedly gained setup membership")

    power["services"]["ups"]["measurements"][0]["setups"] = ["power"]
    assert_rejected(power, "dedicated power measurements must omit setups")


def test_canonical_catalog_and_projections() -> None:
    """Project the same canonical measurement objects by setup and physical service."""

    catalog = build_measurement_catalog(LabPulseConfig.model_validate(config_data()))
    if [item.key.service_name for item in catalog.measurements] != [
        "pump_room",
        "pump_room",
        "pump_room",
        "room_environment",
    ]:
        raise AssertionError("catalog did not follow YAML service order")
    if "disabled" in catalog.by_service:
        raise AssertionError("disabled service entered the measurement catalog")

    cryostat_only = catalog.by_key[MeasurementKey("pump_room", "cryostat_only")]
    turbo = catalog.by_key[MeasurementKey("pump_room", "turbo")]
    shared = catalog.by_key[MeasurementKey("pump_room", "shared")]
    global_measurement = catalog.by_key[MeasurementKey("room_environment", "temperature")]

    if catalog.selected_shared_measurements != (shared,):
        raise AssertionError("selected shared projection is incorrect")
    if shared.effective_setup_ids != ("cryostat", "turbo_pump"):
        raise AssertionError("selected setups did not follow configured setup order")
    if global_measurement.effective_setup_ids != ("cryostat",):
        raise AssertionError("single setup membership is incorrect")
    if catalog.by_setup["cryostat"] != (cryostat_only, shared, global_measurement):
        raise AssertionError("cryostat projection is incorrect")
    if catalog.by_setup["turbo_pump"] != (turbo, shared):
        raise AssertionError("turbo projection is incorrect")
    if catalog.by_service["pump_room"] != (cryostat_only, turbo, shared):
        raise AssertionError("physical service projection is incorrect")
    if catalog.by_setup["turbo_pump"][0] is not turbo:
        raise AssertionError("setup projection copied a canonical measurement")
    if turbo.key.stable_id != "labpulse_pump_room_turbo":
        raise AssertionError("setup membership changed physical stable identity")


def test_bulk_deadband_compatibility_groups() -> None:
    """Group exact device-class/unit pairs and isolate missing device classes."""

    config = LabPulseConfig.model_validate(config_data())
    catalog = build_measurement_catalog(config)
    model = RenderModel.from_config(config, catalog)
    all_target = model.bulk_alarm_targets[0]
    groups = {
        (group.key.device_class, group.key.unit): group
        for group in all_target.deadband_groups
    }
    celsius = groups[("temperature", "°C")]
    if celsius.measurement_keys != (
        MeasurementKey("pump_room", "cryostat_only"),
        MeasurementKey("pump_room", "shared"),
    ):
        raise AssertionError("same-class Celsius measurements were not grouped")
    fahrenheit = groups[("temperature", "°F")]
    if fahrenheit.measurement_keys != (
        MeasurementKey("room_environment", "temperature"),
    ):
        raise AssertionError("different temperature units were combined")
    fallback_groups = [
        group for group in all_target.deadband_groups
        if group.key.device_class.startswith("measurement:")
    ]
    if len(fallback_groups) != 1 or fallback_groups[0].measurement_keys != (
        MeasurementKey("pump_room", "turbo"),
    ):
        raise AssertionError("missing device class was not isolated")
    if len(all_target.measurement_keys) != len(set(all_target.measurement_keys)):
        raise AssertionError("all-measurements target duplicated a shared measurement")


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("scope normalization and validation", test_scope_normalization_and_validation),
    ("setup metadata validation", test_setup_metadata_validation),
    ("dedicated power membership", test_dedicated_power_omits_setup_membership),
    ("canonical catalog and projections", test_canonical_catalog_and_projections),
    ("bulk deadband compatibility", test_bulk_deadband_compatibility_groups),
]


def main() -> None:
    """Run all setup grouping tests."""

    print("Running setup grouping tests")
    passed = 0
    for name, test in TESTS:
        try:
            test()
        except Exception as error:
            print(f"[FAIL] {name}: {type(error).__name__}: {error}")
        else:
            print(f"[PASS] {name}")
            passed += 1
    print(f"Summary: {passed}/{len(TESTS)} passed")
    if passed != len(TESTS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
