"""Focused tests for setup-aware, non-duplicated alarm notifications."""

from collections.abc import Callable, Iterable
from pathlib import Path
import sys

import yaml


REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.config import LabPulseConfig
from labpulse_homeassistant.alarm_package import (
    automations,
    input_booleans,
    load_alarm_seed,
    load_power_seed,
)
from labpulse_homeassistant.render_model import RenderModel
from labpulse_homeassistant.measurement_catalog import build_measurement_catalog


def config_data() -> dict[str, object]:
    """Return one service with single and shared setup memberships."""

    return {
        "mqtt": {"broker": "mosquitto"},
        "setups": {
            "alpha": {"label": "Alpha Experiment", "order": 10},
            "beta": {"label": "Beta Experiment", "order": 20},
        },
        "services": {
            "shared_hub": {
                "driver": "serial",
                "parser": "pump_room",
                "serial_port": "/tmp/shared-hub",
                "device_name": "Shared Sensor Hub",
                "measurements": [
                    {"name": "alpha", "label": "Alpha Measurement", "setups": ["alpha"]},
                    {"name": "beta", "label": "Beta Measurement", "setups": ["beta"]},
                    {
                        "name": "shared",
                        "label": "Shared Measurement",
                        "setups": ["beta", "alpha"],
                    },
                ],
            }
        },
    }


def walk(value: object) -> Iterable[object]:
    """Yield every nested YAML value."""

    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def service_call_count(automation: dict[str, object], service: str) -> int:
    """Count exact Home Assistant service actions in one automation."""

    return sum(
        1
        for item in walk(automation)
        if isinstance(item, dict) and item.get("service") == service
    )


def service_actions(
    automation: dict[str, object], service: str
) -> list[dict[str, object]]:
    """Return exact Home Assistant service actions from one automation."""

    return [
        item
        for item in walk(automation)
        if isinstance(item, dict) and item.get("service") == service
    ]


def rendered_automations(config: LabPulseConfig) -> list[dict[str, object]]:
    """Render alarm automations from the canonical catalog."""

    catalog = build_measurement_catalog(config)
    model = RenderModel.from_config(config, catalog=catalog)
    return automations(load_alarm_seed(), load_power_seed(), model)


def test_context_for_every_scope_without_duplicate_events() -> None:
    """Put setup context in each existing notification without multiplying it."""

    config = LabPulseConfig.model_validate(config_data())
    generated = rendered_automations(config)
    expected = {
        "Alpha Measurement": "Affected setup: Alpha Experiment.",
        "Beta Measurement": "Affected setup: Beta Experiment.",
        "Shared Measurement": "Affected setups: Alpha Experiment, Beta Experiment.",
    }
    transition_suffixes = (
        " Danger",
        " Recovery",
        " Sensor Fault",
        " Sensor Recovery",
    )
    for label, context in expected.items():
        measurement_automations = [
            item
            for item in generated
            if str(item.get("alias", "")).startswith(f"LabPulse {label} ")
            and str(item.get("alias", "")).endswith(transition_suffixes)
        ]
        if len(measurement_automations) != 4:
            raise AssertionError(
                f"{label} should retain four physical transition automations"
            )
        for automation in measurement_automations:
            if service_call_count(automation, "persistent_notification.create") != 1:
                raise AssertionError(f"{automation['alias']} duplicates HA notifications")
            if service_call_count(automation, "mqtt.publish") != 1:
                raise AssertionError(f"{automation['alias']} duplicates SMS requests")
            persistent = service_actions(
                automation, "persistent_notification.create"
            )[0]
            sms = service_actions(automation, "mqtt.publish")[0]
            if context not in str(persistent["data"]["message"]):
                raise AssertionError(
                    f"{automation['alias']} lacks Home Assistant setup context"
                )
            if context not in str(sms["data"]["payload"]):
                raise AssertionError(f"{automation['alias']} lacks SMS setup context")


def test_membership_does_not_change_alarm_identity() -> None:
    """Changing logical membership changes wording but not physical identity."""

    first_data = config_data()
    second_data = config_data()
    second_data["services"]["shared_hub"]["measurements"][1]["setups"] = [
        "alpha",
        "beta",
    ]
    first = RenderModel.from_config(LabPulseConfig.model_validate(first_data)).services[0]
    second = RenderModel.from_config(LabPulseConfig.model_validate(second_data)).services[0]
    first_measurement = first.measurements[1]
    second_measurement = second.measurements[1]
    first_identity = (
        first_measurement.measurement_id,
        first_measurement.mqtt_entity,
        first_measurement.entities["alarm_state"],
        first_measurement.entities["alarm_mode"],
        first_measurement.entities["alarm_muted"],
    )
    second_identity = (
        second_measurement.measurement_id,
        second_measurement.mqtt_entity,
        second_measurement.entities["alarm_state"],
        second_measurement.entities["alarm_mode"],
        second_measurement.entities["alarm_muted"],
    )
    if first_identity != second_identity:
        raise AssertionError("setup membership changed physical alarm identity")
    if first_measurement.notification_context == second_measurement.notification_context:
        raise AssertionError("setup membership did not update notification context")


def test_service_faults_remain_hub_level() -> None:
    """Do not apply measurement/setup context to physical service-health alarms."""

    generated = rendered_automations(LabPulseConfig.model_validate(config_data()))
    service_health = [
        item
        for item in generated
        if "Service Fault" in str(item.get("alias", ""))
        or "Service Restored" in str(item.get("alias", ""))
    ]
    if len(service_health) != 2:
        raise AssertionError("expected one hub fault and one hub recovery automation")
    rendered = yaml.safe_dump(service_health, sort_keys=False)
    for setup_phrase in ("Affected setup", "Affects all setups", "General monitoring"):
        if setup_phrase in rendered:
            raise AssertionError("service health notification gained setup context")


def test_setup_mutes_are_independent_delivery_gates() -> None:
    """Keep shared alerts open while any owning setup remains unmuted."""

    config = LabPulseConfig.model_validate(config_data())
    catalog = build_measurement_catalog(config)
    model = RenderModel.from_config(config, catalog=catalog)
    alpha_mute = "input_boolean.labpulse_setup_alpha_notifications_muted"
    beta_mute = "input_boolean.labpulse_setup_beta_notifications_muted"
    helpers = input_booleans(load_alarm_seed(), load_power_seed(), model)
    for helper in (alpha_mute, beta_mute):
        helper_id = helper.split(".", 1)[1]
        if helper_id not in helpers:
            raise AssertionError(f"setup mute helper is missing: {helper}")
        if "initial" in helpers[helper_id]:
            raise AssertionError(f"setup mute does not restore state: {helper}")

    measurements = {
        measurement.label: measurement
        for service in model.services
        for measurement in service.measurements
    }
    shared_gate = measurements["Shared Measurement"].setup_notifications_unmuted_template
    if shared_gate != (
        "{{ is_state('" + alpha_mute + "', 'off') or "
        "is_state('" + beta_mute + "', 'off') }}"
    ):
        raise AssertionError("shared measurement does not allow either open setup")

    generated = rendered_automations(config)
    expected_gates = {
        "Alpha Measurement": (alpha_mute,),
        "Beta Measurement": (beta_mute,),
        "Shared Measurement": (alpha_mute, beta_mute),
    }
    for label, gates in expected_gates.items():
        transitions = [
            automation
            for automation in generated
            if str(automation.get("alias", "")).startswith(f"LabPulse {label} ")
            and str(automation.get("alias", "")).endswith(
                (" Danger", " Recovery", " Sensor Fault", " Sensor Recovery")
            )
        ]
        if len(transitions) != 4:
            raise AssertionError(f"wrong transition count for {label}")
        value_templates = [
            str(item["value_template"])
            for transition in transitions
            for item in walk(transition)
            if isinstance(item, dict) and "value_template" in item
        ]
        for gate in gates:
            if not any(f"is_state('{gate}', 'off')" in item for item in value_templates):
                raise AssertionError(f"{label} does not require open gate {gate}")
        for unrelated in {alpha_mute, beta_mute}.difference(gates):
            if any(unrelated in item for item in value_templates):
                raise AssertionError(f"{label} gained unrelated setup gate {unrelated}")

    setup_helpers = {alpha_mute, beta_mute}
    for automation in generated:
        for action in walk(automation):
            if not isinstance(action, dict) or action.get("service") not in {
                "input_boolean.turn_on",
                "input_boolean.turn_off",
            }:
                continue
            if any(helper in str(action.get("target", {})) for helper in setup_helpers):
                raise AssertionError("an automation overwrites a setup mute helper")

    service_health = [
        automation
        for automation in generated
        if "Service Fault" in str(automation.get("alias", ""))
        or "Service Restored" in str(automation.get("alias", ""))
    ]
    if any(helper in yaml.safe_dump(service_health) for helper in setup_helpers):
        raise AssertionError("setup mute leaked into physical service-health alarms")


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("context without duplicate events", test_context_for_every_scope_without_duplicate_events),
    ("membership preserves identity", test_membership_does_not_change_alarm_identity),
    ("service faults stay hub-level", test_service_faults_remain_hub_level),
    ("independent setup mute gates", test_setup_mutes_are_independent_delivery_gates),
]


def main() -> None:
    """Run focused notification-context tests."""

    print("Running setup notification-context tests")
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
