"""Contracts for external physical-measurement configuration files."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from labpulse.common.config import (
    ConfigError,
    format_config_error,
    load_config,
    render_resolved_config,
    validate_resolved_config,
)
from labpulse.deployment.generate import generate_deployment
from labpulse.common.identity import stable_id


def write_master(root: Path, service: dict[str, object]) -> Path:
    """Write one compact source configuration around a supplied service."""

    root.mkdir(parents=True, exist_ok=True)
    path = root / "config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "mqtt": {"broker": "mosquitto"},
                "setups": {"fridge": {"label": "Fridge"}},
                "services": {"triton_01": service},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def fridge_service(**overrides: object) -> dict[str, object]:
    """Return a valid MQTT fridge service using external measurements."""

    service: dict[str, object] = {
        "label": "Triton 1",
        "driver": {
            "type": "labpulse.mqtt_json",
            "options": {"topic": "labpulse/triton/triton-01/measurements"},
        },
        "measurement_defaults": {"setups": ["fridge"], "precision": 1},
        "measurements_file": "config.d/triton-01-measurements.yaml",
    }
    service.update(overrides)
    return service


def write_measurements(root: Path, text: str | None = None) -> Path:
    """Create the standard fragment and return its path."""

    path = root / "config.d" / "triton-01-measurements.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        (
            "cold_plate_temperature:\n"
            "  source: Cold Plate T(K)\n"
            "  unit: K\n"
            "condense_pressure:\n"
            "  source: P2 Condense (Bar)\n"
            "  unit: bar\n"
        )
        if text is None
        else text,
        encoding="utf-8",
    )
    return path


def error_text(path: Path) -> str:
    """Load an invalid source and return its formatted failure."""

    with pytest.raises(ConfigError) as captured:
        load_config(path)
    return format_config_error(captured.value)


def test_external_measurements_resolve_in_order_and_inherit_defaults(
    workspace_tmp_path: Path,
) -> None:
    """Resolve one fragment into the same typed model used by inline readings."""

    root = workspace_tmp_path / "external-measurements"
    master = write_master(root, fridge_service())
    fragment = write_measurements(root)

    document = load_config(master)
    measurements = document.config.services["triton_01"].measurements
    assert list(measurements) == ["cold_plate_temperature", "condense_pressure"]
    assert measurements["cold_plate_temperature"].setups == ("fridge",)
    assert measurements["cold_plate_temperature"].precision == 1
    assert document.source_paths == (master.resolve(), fragment.resolve())
    assert document.measurement_sources == (("triton_01", fragment.resolve()),)

    rendered = render_resolved_config(document)
    assert "measurements_file" not in rendered
    assert "measurements:" in rendered
    resolved = validate_resolved_config(rendered, root / "config.resolved.yaml")
    assert list(resolved.config.services["triton_01"].measurements) == list(measurements)
    assert resolved.measurement_sources == ()


def test_inline_measurements_remain_supported(workspace_tmp_path: Path) -> None:
    """Keep existing single-file configurations valid without migration."""

    service = fridge_service()
    service.pop("measurements_file")
    service["measurements"] = {
        "cold_plate_temperature": {"source": "Cold Plate T(K)", "unit": "K"}
    }
    document = load_config(write_master(workspace_tmp_path / "inline", service))
    assert list(document.config.services["triton_01"].measurements) == [
        "cold_plate_temperature"
    ]
    assert document.measurement_sources == ()


def test_measurement_source_is_exclusive_and_required(workspace_tmp_path: Path) -> None:
    """Require exactly one inline or external measurement mapping per service."""

    both_root = workspace_tmp_path / "both"
    both = fridge_service(
        measurements={
            "cold_plate_temperature": {"source": "Cold Plate T(K)"}
        }
    )
    write_measurements(both_root)
    assert "exactly one" in error_text(write_master(both_root, both))

    neither = fridge_service()
    neither.pop("measurements_file")
    assert "measurements" in error_text(
        write_master(workspace_tmp_path / "neither", neither)
    )


@pytest.mark.parametrize(
    ("fragment_text", "expected"),
    [
        ("", "non-empty mapping"),
        ("- one\n- two\n", "non-empty mapping"),
        ("measurements: [\n", "while parsing"),
        (
            "cold_plate_temperature:\n  source: one\n"
            "cold_plate_temperature:\n  source: two\n",
            "duplicate key",
        ),
    ],
)
def test_fragment_shape_and_yaml_failures(
    workspace_tmp_path: Path,
    fragment_text: str,
    expected: str,
) -> None:
    """Reject malformed, empty, wrong-root, and duplicate-key fragments."""

    root = workspace_tmp_path / ("fragment-" + str(abs(hash(fragment_text))))
    master = write_master(root, fridge_service())
    fragment = write_measurements(root, fragment_text)
    rendered = error_text(master)
    assert expected in rendered
    assert str(fragment.resolve()) in rendered


def test_fragment_schema_errors_name_the_fragment_and_measurement(
    workspace_tmp_path: Path,
) -> None:
    """Attribute a field-validation error to the external source file."""

    root = workspace_tmp_path / "fragment-schema"
    master = write_master(root, fridge_service())
    fragment = write_measurements(
        root,
        "cold_plate_temperature:\n"
        "  source: Cold Plate T(K)\n"
        "  precision: wrong\n",
    )
    rendered = error_text(master)
    assert str(fragment.resolve()) in rendered
    assert "cold_plate_temperature" in rendered
    assert "precision" in rendered


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("/tmp/readings.yaml", "relative"),
        ("../readings.yaml", "beneath config.d"),
        ("other/readings.yaml", "beneath config.d"),
        ("config.d/readings.txt", ".yaml or .yml"),
        ("config.d/missing.yaml", "does not exist"),
    ],
)
def test_fragment_path_boundaries(
    workspace_tmp_path: Path,
    configured: str,
    expected: str,
) -> None:
    """Keep external measurement sources within the dedicated source tree."""

    root = workspace_tmp_path / ("path-" + str(abs(hash(configured))))
    master = write_master(root, fridge_service(measurements_file=configured))
    assert expected in error_text(master)


def test_fragment_rejects_directories_and_symlinks(workspace_tmp_path: Path) -> None:
    """Require a normal source file without following a link out of config.d."""

    directory_root = workspace_tmp_path / "fragment-directory"
    master = write_master(directory_root, fridge_service())
    fragment = directory_root / "config.d" / "triton-01-measurements.yaml"
    fragment.mkdir(parents=True)
    assert "not a regular file" in error_text(master)

    symlink_root = workspace_tmp_path / "fragment-symlink"
    master = write_master(symlink_root, fridge_service())
    outside = symlink_root / "outside.yaml"
    outside.write_text("reading: {}\n", encoding="utf-8")
    link = symlink_root / "config.d" / "triton-01-measurements.yaml"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("test environment does not permit symbolic links")
    assert "must not use symlinks" in error_text(master)


@pytest.mark.parametrize(
    ("fake_usb", "runtime_name"),
    [(False, "config.resolved.yaml"), (True, "config.fake.yaml")],
)
def test_deployment_mounts_a_standalone_generated_runtime(
    workspace_tmp_path: Path,
    fake_usb: bool,
    runtime_name: str,
) -> None:
    """Resolve fragments before writing either real or simulated runtime YAML."""

    root = workspace_tmp_path / ("generated-fake" if fake_usb else "generated-real")
    master = write_master(root, fridge_service())
    write_measurements(root)
    generate_deployment(
        config_path=master,
        compose_output=root / "compose.yaml",
        project_dir=root,
        ha_config_dir=root / "homeassistant" / "config",
        runtime_image="local/labpulse:test",
        force_simulated=fake_usb,
    )

    resolved_text = (root / "config.resolved.yaml").read_text(encoding="utf-8")
    assert "measurements_file" not in resolved_text
    assert "cold_plate_temperature:" in resolved_text
    validate_resolved_config(resolved_text, root / "config.resolved.yaml")
    runtime_text = (root / runtime_name).read_text(encoding="utf-8")
    assert "measurements_file" not in runtime_text
    validate_resolved_config(runtime_text, root / runtime_name)
    compose = yaml.safe_load((root / "compose.yaml").read_text(encoding="utf-8"))
    expected_mount = f"./{runtime_name}:/app/config.yaml:ro"
    assert expected_mount in compose["services"]["labpulse-triton-01"]["volumes"]
    assert expected_mount in compose["services"]["labpulse-sms"]["volumes"]


def test_two_fridge_fragments_keep_independent_existing_identities(
    workspace_tmp_path: Path,
) -> None:
    """Keep service-scoped entity IDs and source mappings separate per fridge."""

    root = workspace_tmp_path / "two-fridges"
    root.mkdir()
    data = {
        "mqtt": {"broker": "mosquitto"},
        "setups": {
            "triton_1": {"label": "Triton 1"},
            "triton_2": {"label": "Triton 2"},
        },
        "services": {
            "triton_01": fridge_service(
                measurement_defaults={"setups": ["triton_1"]},
            ),
            "triton_02": fridge_service(
                label="Triton 2",
                measurement_defaults={"setups": ["triton_2"]},
                measurements_file="config.d/triton-02-measurements.yaml",
                driver={
                    "type": "labpulse.mqtt_json",
                    "options": {
                        "topic": "labpulse/triton/triton-02/measurements",
                    },
                },
            ),
        },
    }
    master = root / "config.yaml"
    master.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    first = write_measurements(root)
    second = root / "config.d" / "triton-02-measurements.yaml"
    second.write_bytes(first.read_bytes())

    document = load_config(master)
    assert tuple(document.config.services) == ("triton_01", "triton_02")
    for service_id in ("triton_01", "triton_02"):
        measurement = document.config.services[service_id].measurements[
            "cold_plate_temperature"
        ]
        assert measurement.source == "Cold Plate T(K)"
        assert stable_id(service_id, "cold_plate_temperature") == (
            f"labpulse_{service_id}_cold_plate_temperature"
        )
    assert dict(document.measurement_sources) == {
        "triton_01": first.resolve(),
        "triton_02": second.resolve(),
    }
