"""Focused tests for the authoritative source-aware configuration pipeline."""

from collections.abc import Callable
from pathlib import Path
import shutil
import sys
from uuid import uuid4

import yaml


REPOSITORY = Path(__file__).resolve().parents[1]

from labpulse.common.config import (
    ConfigError,
    format_config_error,
    load_config,
)
from labpulse.hardware.drivers.serial_pipe import SerialPipeOptions
from labpulse.hardware.drivers.sht40 import Sht40Options
from labpulse.hardware.drivers.x1200 import X1200Options


def repository_data() -> dict[str, object]:
    """Return a fresh decoded copy of the maintained starter configuration."""

    payload = yaml.safe_load((REPOSITORY / "config.yaml").read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError("starter config did not decode to a mapping")
    return payload


def expect_error(data: object, message: str) -> ConfigError:
    """Parse invalid data and require one structured error containing text."""

    try:
        load_config(REPOSITORY / "invalid.yaml", text=yaml.safe_dump(data))
    except ConfigError as error:
        if message not in format_config_error(error):
            raise AssertionError(f"missing {message!r} in {error}") from error
        return error
    raise AssertionError("invalid configuration was accepted")


def test_valid_document_and_typed_driver_options() -> None:
    """Retain source identity and every concrete options model after one load."""

    document = load_config(REPOSITORY / "config.yaml")
    if document.path != (REPOSITORY / "config.yaml").resolve():
        raise AssertionError(f"unexpected source path: {document.path}")
    expected_types = {
        "pressure_monitor": SerialPipeOptions,
        "room_environment": Sht40Options,
        "ups_monitor": X1200Options,
    }
    for service_name, expected_type in expected_types.items():
        options = document.config.services[service_name].driver.options
        if not isinstance(options, expected_type):
            raise AssertionError(
                f"{service_name} options are {type(options).__name__}, "
                f"not {expected_type.__name__}"
            )
    dumped = document.config.model_dump()
    if dumped["services"]["pressure_monitor"]["driver"]["options"]["baud_rate"] != 9600:
        raise AssertionError("concrete driver defaults were lost during serialization")
    pressure = document.config.services["pressure_monitor"].measurements["pressure"]
    if pressure.alarmed is not True:
        raise AssertionError("measurements are not alarmed by default")
    if document.config.setups["compressed_air"].dashboard != "main":
        raise AssertionError("setups do not default to the main dashboard")


def test_root_and_schema_errors_are_structured() -> None:
    """Reject empty, scalar, unknown-field, driver, and option failures uniformly."""

    expect_error(None, "configuration is empty")
    expect_error([], "configuration root must be a mapping")
    unknown = repository_data()
    unknown["unexpected"] = True
    expect_error(unknown, "Extra inputs are not permitted")
    unknown_driver = repository_data()
    unknown_driver["services"]["pressure_monitor"]["driver"]["type"] = "unknown.driver"  # type: ignore[index]
    expect_error(unknown_driver, "Unknown driver type")
    invalid_option = repository_data()
    invalid_option["services"]["pressure_monitor"]["driver"]["options"]["baud_rate"] = 0  # type: ignore[index]
    expect_error(invalid_option, "greater than or equal to 1")
    invalid_option_shape = repository_data()
    invalid_option_shape["services"]["pressure_monitor"]["driver"]["options"] = 3  # type: ignore[index]
    expect_error(invalid_option_shape, "driver options must be a mapping")

    unsupported_dashboard_label = repository_data()
    measurement = unsupported_dashboard_label["services"]["pressure_monitor"]["measurements"]["pressure"]  # type: ignore[index]
    measurement["dashboard_label"] = "Pressure"
    expect_error(unsupported_dashboard_label, "Extra inputs are not permitted")


def test_alarm_and_dashboard_configuration_contracts() -> None:
    """Validate custom dashboard references and strict measurement alarm flags."""

    configured = repository_data()
    configured["dashboards"] = {
        "cryogenics": {
            "label": "Cryogenics",
            "icon": "mdi:snowflake",
            "order": 10,
        }
    }
    configured["setups"]["cryogenics_room"]["dashboard"] = "cryogenics"  # type: ignore[index]
    configured["services"]["room_environment"]["measurements"]["temperature"]["alarmed"] = False  # type: ignore[index]
    document = load_config(
        REPOSITORY / "configured.yaml",
        text=yaml.safe_dump(configured, sort_keys=False),
    )
    if document.config.setups["cryogenics_room"].dashboard != "cryogenics":
        raise AssertionError("custom dashboard assignment was not retained")
    if document.config.services["room_environment"].measurements["temperature"].alarmed:
        raise AssertionError("explicit alarm disablement was not retained")

    unknown_dashboard = repository_data()
    unknown_dashboard["setups"]["compressed_air"]["dashboard"] = "missing"  # type: ignore[index]
    expect_error(unknown_dashboard, "references unknown dashboard: missing")

    reserved_dashboard = repository_data()
    reserved_dashboard["dashboards"] = {"main": {}}
    expect_error(reserved_dashboard, "reserved for the built-in Monitor tab")

    non_boolean_alarm = repository_data()
    non_boolean_alarm["services"]["pressure_monitor"]["measurements"]["pressure"]["alarmed"] = "false"  # type: ignore[index]
    expect_error(non_boolean_alarm, "valid boolean")

    mixed_power_alarm = repository_data()
    mixed_power_alarm["services"]["ups_monitor"]["measurements"]["voltage"]["alarmed"] = False  # type: ignore[index]
    expect_error(mixed_power_alarm, "must all use the same alarmed value")


def test_file_failures_use_the_same_error_model() -> None:
    """Classify missing and malformed files without exiting the caller."""

    temporary_root = REPOSITORY / "testing" / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    root = temporary_root / f"config-pipeline-{uuid4().hex}"
    root.mkdir()
    try:
        missing = root / "missing.yaml"
        try:
            load_config(missing)
        except ConfigError as error:
            if error.path != missing.resolve() or error.problems[0].kind != "read_error":
                raise AssertionError(f"unexpected missing-file error: {error}") from error
        else:
            raise AssertionError("missing configuration was accepted")

        malformed = root / "malformed.yaml"
        malformed.write_text("services: [\n", encoding="utf-8")
        try:
            load_config(malformed)
        except ConfigError as error:
            if error.problems[0].kind != "yaml_error":
                raise AssertionError(f"unexpected YAML error: {error}") from error
        else:
            raise AssertionError("malformed YAML was accepted")
    finally:
        shutil.rmtree(root)
