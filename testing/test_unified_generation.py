"""Integration tests for one-load staged deployment generation."""

from collections.abc import Callable
from pathlib import Path
import shutil
import sys
from uuid import uuid4


REPOSITORY = Path(__file__).resolve().parents[1]
TEST_TMP = REPOSITORY / "testing" / "tmp"
TEST_TMP.mkdir(parents=True, exist_ok=True)

import labpulse.deployment.generate as generation


def workspace(prefix: str) -> Path:
    """Create one explicit test directory that callers remove in ``finally``."""

    root = TEST_TMP / f"{prefix}-{uuid4().hex}"
    root.mkdir()
    return root


def write_config(root: Path) -> Path:
    """Copy the maintained config into one generation test directory."""

    config_path = root / "config.yaml"
    config_path.write_text(
        (REPOSITORY / "config.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return config_path


def test_generation_loads_once_and_preserves_ui_files() -> None:
    """Build both output families from one document without replacing UI YAML."""

    root = workspace("unified-generation")
    original_loader = generation.load_config
    calls = 0

    def counting_loader(path: Path) -> object:
        """Count authoritative loads while delegating to the real implementation."""

        nonlocal calls
        calls += 1
        return original_loader(path)

    try:
        config_path = write_config(root)
        compose_path = root / "compose.yaml"
        ha_config_dir = root / "homeassistant" / "config"
        ha_config_dir.mkdir(parents=True)
        automations = ha_config_dir / "automations.yaml"
        automations.write_text("# user-owned\n[]\n", encoding="utf-8")
        generation.load_config = counting_loader  # type: ignore[assignment]
        generation.generate_deployment(
            config_path,
            compose_path,
            root,
            ha_config_dir,
            "local/labpulse:test",
        )
        if calls != 1:
            raise AssertionError(f"generation loaded configuration {calls} times")
        if not compose_path.is_file():
            raise AssertionError("Compose output was not installed")
        for path in (
            ha_config_dir / "configuration.yaml",
            ha_config_dir / "packages" / "labpulse_generated.yaml",
            ha_config_dir / "labpulse-dashboard.yaml",
        ):
            if not path.is_file():
                raise AssertionError(f"Home Assistant output is missing: {path}")
        if automations.read_text(encoding="utf-8") != "# user-owned\n[]\n":
            raise AssertionError("UI-managed automations were overwritten")
        for name in ("scripts.yaml", "scenes.yaml"):
            if (ha_config_dir / name).read_text(encoding="utf-8") != "[]\n":
                raise AssertionError(f"missing UI file was not initialized: {name}")
    finally:
        generation.load_config = original_loader
        shutil.rmtree(root)


def test_failed_build_leaves_live_outputs_unchanged() -> None:
    """Do not replace Compose or HA files when staged HA generation fails."""

    root = workspace("failed-generation")
    original_generator = generation.generate_homeassistant

    def fail_generation(*_args: object, **_kwargs: object) -> None:
        """Simulate a renderer failure after Compose has built in memory."""

        raise RuntimeError("simulated Home Assistant build failure")

    try:
        config_path = write_config(root)
        compose_path = root / "compose.yaml"
        ha_config_dir = root / "homeassistant" / "config"
        compose_path.write_text("old compose\n", encoding="utf-8")
        ha_config_dir.mkdir(parents=True)
        dashboard = ha_config_dir / "labpulse-dashboard.yaml"
        dashboard.write_text("old dashboard\n", encoding="utf-8")
        generation.generate_homeassistant = fail_generation
        try:
            generation.generate_deployment(
                config_path,
                compose_path,
                root,
                ha_config_dir,
                "local/labpulse:test",
            )
        except RuntimeError as error:
            if "simulated" not in str(error):
                raise
        else:
            raise AssertionError("simulated build failure was ignored")
        if compose_path.read_text(encoding="utf-8") != "old compose\n":
            raise AssertionError("Compose changed after a staged build failure")
        if dashboard.read_text(encoding="utf-8") != "old dashboard\n":
            raise AssertionError("Home Assistant output changed after build failure")
    finally:
        generation.generate_homeassistant = original_generator
        shutil.rmtree(root)
