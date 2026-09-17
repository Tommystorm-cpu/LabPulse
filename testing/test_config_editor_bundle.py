"""Linux integration contracts for the guarded source-bundle editor."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest
import yaml

from labpulse.deployment.generate import generate_deployment


pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None,
    reason="the guarded configuration editor is a Linux shell workflow",
)


def _master(*, external: bool) -> dict[str, object]:
    service: dict[str, object] = {
        "label": "Triton 1",
        "driver": {
            "type": "labpulse.mqtt_json",
            "options": {"topic": "labpulse/triton/triton-01/measurements"},
        },
        "measurement_defaults": {"setups": ["triton_1"]},
    }
    if external:
        service["measurements_file"] = "config.d/triton-01-measurements.yaml"
    else:
        service["measurements"] = {
            "cold_plate_temperature": {
                "source": "Cold Plate T(K)",
                "unit": "K",
            }
        }
    return {
        "mqtt": {"broker": "mosquitto"},
        "setups": {"triton_1": {"label": "Triton 1"}},
        "services": {"triton_01": service},
    }


def _write_editor(path: Path) -> None:
    path.write_text(
        """from pathlib import Path
import os
import sys
import yaml

mode = os.environ.get("EDIT_MODE", "none")
paths = [Path(value) for value in sys.argv[1:]]
master = next((path for path in paths if path.name == "config.yaml"), None)
fragment = next((path for path in paths if path.name != "config.yaml"), None)
if mode == "fragment":
    text = fragment.read_text(encoding="utf-8")
    fragment.write_text(text.replace("unit: K", "unit: mK"), encoding="utf-8")
elif mode == "invalid":
    fragment.write_text("- invalid\\n", encoding="utf-8")
elif mode == "create":
    data = yaml.safe_load(master.read_text(encoding="utf-8"))
    service = data["services"]["triton_01"]
    measurements = service.pop("measurements")
    service["measurements_file"] = "config.d/triton-01-measurements.yaml"
    master.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    fragment.write_text(yaml.safe_dump(measurements, sort_keys=False), encoding="utf-8")
""",
        encoding="utf-8",
    )


def _write_docker(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '%s\\n' "$*" >> "$FAKE_DOCKER_LOG"
if [ "${FAKE_DOCKER_FAIL_CONFIG:-0}" = "1" ] && [ "$*" = "compose config --quiet" ]; then
  exit 1
fi
if [ "$*" = "compose ps --status running --services" ]; then
  exit 0
fi
exit 0
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


@pytest.fixture
def editor_live(
    workspace_tmp_path: Path,
    repository_root: Path,
) -> tuple[Path, dict[str, str]]:
    """Create a generated live tree with fake editor and Docker commands."""

    live = workspace_tmp_path / "live"
    live.mkdir()
    config = live / "config.yaml"
    config.write_text(yaml.safe_dump(_master(external=True), sort_keys=False), encoding="utf-8")
    fragment = live / "config.d" / "triton-01-measurements.yaml"
    fragment.parent.mkdir()
    fragment.write_text(
        "cold_plate_temperature:\n  source: Cold Plate T(K)\n  unit: K\n",
        encoding="utf-8",
    )
    python_link = live / ".venv" / "bin" / "python"
    python_link.parent.mkdir(parents=True)
    python_link.symlink_to(Path(sys.executable))
    generate_deployment(
        config,
        live / "compose.yaml",
        live,
        live / "homeassistant" / "config",
        "local/labpulse:test",
    )
    editor = workspace_tmp_path / "editor.py"
    docker = workspace_tmp_path / "docker"
    _write_editor(editor)
    _write_docker(docker)
    environment = os.environ.copy()
    environment.update(
        {
            "EDITOR": f"{sys.executable} {editor}",
            "FAKE_DOCKER_LOG": str(workspace_tmp_path / "docker.log"),
            "LABPULSE_DOCKER_COMMAND": str(docker),
            "LABPULSE_LIVE_DIR": str(live),
            "PYTHONPATH": str(repository_root / "src"),
        }
    )
    return live, environment


def _run(
    repository_root: Path,
    environment: dict[str, str],
    *files: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(repository_root / "deployment" / "edit_config.sh"), *files],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_fragment_only_change_is_applied(
    editor_live: tuple[Path, dict[str, str]], repository_root: Path
) -> None:
    live, environment = editor_live
    environment["EDIT_MODE"] = "fragment"
    result = _run(repository_root, environment, "config.d/triton-01-measurements.yaml")

    assert result.returncode == 0, result.stderr
    assert "unit: mK" in (live / "config.d/triton-01-measurements.yaml").read_text()
    assert "unit: mK" in (live / "config.resolved.yaml").read_text()
    assert "compose up -d --remove-orphans --force-recreate" in Path(
        environment["FAKE_DOCKER_LOG"]
    ).read_text()


def test_master_and_new_fragment_can_be_created_together(
    editor_live: tuple[Path, dict[str, str]], repository_root: Path
) -> None:
    live, environment = editor_live
    shutil.rmtree(live / "config.d")
    (live / "config.yaml").write_text(
        yaml.safe_dump(_master(external=False), sort_keys=False), encoding="utf-8"
    )
    generate_deployment(
        live / "config.yaml",
        live / "compose.yaml",
        live,
        live / "homeassistant" / "config",
        "local/labpulse:test",
    )
    environment["EDIT_MODE"] = "create"
    result = _run(
        repository_root,
        environment,
        "config.yaml",
        "config.d/triton-01-measurements.yaml",
    )

    assert result.returncode == 0, result.stderr
    assert (live / "config.d" / "triton-01-measurements.yaml").is_file()
    assert "measurements_file:" in (live / "config.yaml").read_text()
    assert "measurements_file" not in (live / "config.resolved.yaml").read_text()


def test_no_change_does_not_restart_when_resolved_is_current(
    editor_live: tuple[Path, dict[str, str]], repository_root: Path
) -> None:
    _live, environment = editor_live
    result = _run(repository_root, environment)

    assert result.returncode == 0, result.stderr
    assert "Nothing was restarted" in result.stdout
    assert not Path(environment["FAKE_DOCKER_LOG"]).exists()


def test_stale_resolved_is_regenerated_without_source_edit(
    editor_live: tuple[Path, dict[str, str]], repository_root: Path
) -> None:
    live, environment = editor_live
    fragment = live / "config.d" / "triton-01-measurements.yaml"
    fragment.write_text(fragment.read_text().replace("unit: K", "unit: mK"))
    result = _run(repository_root, environment)

    assert result.returncode == 0, result.stderr
    assert "unit: mK" in (live / "config.resolved.yaml").read_text()


def test_failed_candidate_validation_leaves_live_bundle_untouched(
    editor_live: tuple[Path, dict[str, str]], repository_root: Path
) -> None:
    live, environment = editor_live
    before_master = (live / "config.yaml").read_bytes()
    before_fragment = (live / "config.d" / "triton-01-measurements.yaml").read_bytes()
    before_resolved = (live / "config.resolved.yaml").read_bytes()
    environment["EDIT_MODE"] = "invalid"
    result = _run(repository_root, environment, "config.d/triton-01-measurements.yaml")

    assert result.returncode != 0
    assert (live / "config.yaml").read_bytes() == before_master
    assert (live / "config.d" / "triton-01-measurements.yaml").read_bytes() == before_fragment
    assert (live / "config.resolved.yaml").read_bytes() == before_resolved


def test_downstream_failure_restores_complete_source_bundle(
    editor_live: tuple[Path, dict[str, str]], repository_root: Path
) -> None:
    live, environment = editor_live
    before_master = (live / "config.yaml").read_bytes()
    before_fragment = (live / "config.d" / "triton-01-measurements.yaml").read_bytes()
    before_resolved = (live / "config.resolved.yaml").read_bytes()
    environment.update({"EDIT_MODE": "fragment", "FAKE_DOCKER_FAIL_CONFIG": "1"})
    result = _run(repository_root, environment, "config.d/triton-01-measurements.yaml")

    assert result.returncode != 0
    assert (live / "config.yaml").read_bytes() == before_master
    assert (live / "config.d" / "triton-01-measurements.yaml").read_bytes() == before_fragment
    assert (live / "config.resolved.yaml").read_bytes() == before_resolved
    assert (live / "backups" / "config-source.edit-backup" / "config.yaml").is_file()
