"""Read-only diagnostics for an installed LabPulse deployment."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any

from pydantic import ValidationError
import yaml

from labpulse.common.config import LabPulseConfig
from labpulse.hardware.registry import get_driver_spec


class CheckStatus(StrEnum):
    """Outcome of one diagnostic check."""

    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass(frozen=True)
class DoctorCheck:
    """One human-readable diagnostic result."""

    name: str
    status: CheckStatus
    detail: str


@dataclass
class DoctorReport:
    """Ordered results and the resulting process exit status."""

    live_dir: Path
    checks: list[DoctorCheck] = field(default_factory=list)

    def add(self, status: CheckStatus, name: str, detail: str) -> None:
        """Append one result to the report."""

        self.checks.append(DoctorCheck(name=name, status=status, detail=detail))

    @property
    def exit_code(self) -> int:
        """Return failure when any required check failed."""

        return 1 if any(check.status is CheckStatus.FAIL for check in self.checks) else 0

    def render(self) -> str:
        """Render a compact terminal report."""

        lines = ["LabPulse doctor", f"Live directory: {self.live_dir}", ""]
        for check in self.checks:
            lines.append(f"[{check.status.value:<4}] {check.name}: {check.detail}")

        counts = {
            status: sum(check.status is status for check in self.checks)
            for status in CheckStatus
        }
        lines.extend(
            [
                "",
                "Summary: "
                f"{counts[CheckStatus.PASS]} passed, "
                f"{counts[CheckStatus.WARN]} warnings, "
                f"{counts[CheckStatus.FAIL]} failed, "
                f"{counts[CheckStatus.SKIP]} skipped",
            ]
        )
        if self.exit_code:
            lines.append("Run 'labpulse logs' for service-level error details.")
        return "\n".join(lines)


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]
Connector = Callable[..., Any]


def _read_yaml(path: Path) -> Any:
    """Read one YAML file without mutating it."""

    with path.open("r", encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def _validation_detail(error: Exception) -> str:
    """Return a concise first error suitable for a one-line report."""

    if isinstance(error, ValidationError):
        first = error.errors()[0]
        location = " -> ".join(str(item) for item in first["loc"]) or "root"
        return f"{location}: {first['msg']}"
    return str(error).replace("\n", " ")


def _runtime_config_path(live_dir: Path, compose_data: Any) -> Path:
    """Find the config mounted into containers, including fake-USB mode."""

    if not isinstance(compose_data, dict):
        return (live_dir / "config.yaml").resolve()
    services = compose_data.get("services")
    if not isinstance(services, dict):
        return (live_dir / "config.yaml").resolve()

    for service in services.values():
        if not isinstance(service, dict):
            continue
        volumes = service.get("volumes", ())
        if not isinstance(volumes, list):
            continue
        for volume in volumes:
            if not isinstance(volume, str):
                continue
            parts = volume.split(":")
            if len(parts) >= 2 and parts[1] == "/app/config.yaml":
                source = Path(parts[0]).expanduser()
                return source if source.is_absolute() else (live_dir / source).resolve()
    return (live_dir / "config.yaml").resolve()


def _validate_config(
    report: DoctorReport,
    path: Path,
    name: str,
) -> LabPulseConfig | None:
    """Validate one LabPulse configuration and record its outcome."""

    if not path.is_file():
        report.add(CheckStatus.FAIL, name, f"missing {path}")
        return None
    try:
        config = LabPulseConfig.model_validate(_read_yaml(path))
    except (OSError, yaml.YAMLError, ValidationError, TypeError, ValueError) as error:
        report.add(CheckStatus.FAIL, name, _validation_detail(error))
        return None

    enabled = sum(service.enabled for service in config.services.values())
    report.add(
        CheckStatus.PASS,
        name,
        f"{path.name} is valid ({enabled} enabled hardware services)",
    )
    return config


def _host_resource_paths(config: LabPulseConfig, *, simulated: bool) -> dict[str, set[Path]]:
    """Resolve host device and mount paths used by enabled driver containers."""

    resources: dict[str, set[Path]] = {}
    for service_name, service in config.services.items():
        if not service.enabled:
            continue
        definition = get_driver_spec(service.driver.type)
        options = definition.validate_options(service.driver.options)
        requirements = definition.resolve_resources(options, simulated)
        paths = {Path(device.split(":", 1)[0]) for device in requirements.devices}
        paths.update(Path(mount.split(":", 1)[0]) for mount in requirements.mounts)

        port = getattr(options, "port", None)
        if isinstance(port, str) and port:
            paths.add(Path(port))
        resources[service_name] = paths
    return resources


def _check_hardware(
    report: DoctorReport,
    config: LabPulseConfig | None,
    *,
    simulated: bool,
) -> None:
    """Check that configured driver resources are visible on the host."""

    if config is None:
        report.add(
            CheckStatus.SKIP,
            "Hardware resources",
            "runtime configuration is not valid",
        )
        return

    try:
        service_paths = _host_resource_paths(config, simulated=simulated)
    except (TypeError, ValueError) as error:
        report.add(CheckStatus.FAIL, "Hardware resources", str(error))
        return

    if not service_paths:
        report.add(CheckStatus.PASS, "Hardware resources", "no hardware services enabled")
        return

    for service_name, paths in service_paths.items():
        missing = sorted(str(path) for path in paths if not path.exists())
        if missing:
            report.add(
                CheckStatus.FAIL,
                f"Hardware {service_name}",
                "missing " + ", ".join(missing),
            )
        else:
            detail = ", ".join(sorted(str(path) for path in paths))
            report.add(
                CheckStatus.PASS,
                f"Hardware {service_name}",
                detail or "driver declares no host paths",
            )


def _run(
    runner: CommandRunner,
    command: Sequence[str],
    live_dir: Path,
) -> subprocess.CompletedProcess[str]:
    """Run one bounded, non-interactive diagnostic command."""

    return runner(
        list(command),
        cwd=live_dir,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


def _process_error(result: subprocess.CompletedProcess[str]) -> str:
    """Extract the most useful one-line process failure."""

    output = (result.stderr or result.stdout or "").strip().splitlines()
    return output[-1] if output else f"command exited {result.returncode}"


def _check_docker(
    report: DoctorReport,
    live_dir: Path,
    compose_services: set[str],
    docker_prefix: Sequence[str] | None,
    runner: CommandRunner,
) -> None:
    """Validate Compose syntax and compare expected with running services."""

    if docker_prefix is None:
        report.add(
            CheckStatus.FAIL,
            "Docker Compose",
            "Docker command is not configured correctly",
        )
        report.add(CheckStatus.SKIP, "Containers", "Docker Compose is unavailable")
        return

    command = [*docker_prefix, "compose"]
    try:
        version = _run(runner, [*command, "version"], live_dir)
    except (FileNotFoundError, PermissionError, subprocess.SubprocessError) as error:
        report.add(CheckStatus.FAIL, "Docker Compose", str(error))
        report.add(CheckStatus.SKIP, "Containers", "Docker Compose is unavailable")
        return
    if version.returncode != 0:
        report.add(CheckStatus.FAIL, "Docker Compose", _process_error(version))
        report.add(CheckStatus.SKIP, "Containers", "Docker Compose is unavailable")
        return
    report.add(CheckStatus.PASS, "Docker Compose", "command is available")

    try:
        validation = _run(runner, [*command, "config", "--quiet"], live_dir)
    except subprocess.SubprocessError as error:
        report.add(CheckStatus.FAIL, "Compose validation", str(error))
        report.add(CheckStatus.SKIP, "Containers", "Compose validation did not complete")
        return
    if validation.returncode != 0:
        report.add(CheckStatus.FAIL, "Compose validation", _process_error(validation))
        report.add(CheckStatus.SKIP, "Containers", "Compose file is invalid")
        return
    report.add(CheckStatus.PASS, "Compose validation", "compose.yaml is valid")

    try:
        running_result = _run(
            runner,
            [*command, "ps", "--status", "running", "--services"],
            live_dir,
        )
    except subprocess.SubprocessError as error:
        report.add(CheckStatus.FAIL, "Containers", str(error))
        return
    if running_result.returncode != 0:
        report.add(CheckStatus.FAIL, "Containers", _process_error(running_result))
        return

    running = {line.strip() for line in running_result.stdout.splitlines() if line.strip()}
    missing = sorted(compose_services - running)
    if missing:
        report.add(
            CheckStatus.FAIL,
            "Containers",
            "not running: " + ", ".join(missing),
        )
    else:
        report.add(
            CheckStatus.PASS,
            "Containers",
            f"all {len(compose_services)} Compose services are running",
        )


def _check_tcp(
    report: DoctorReport,
    name: str,
    host: str,
    port: int,
    timeout: float,
    connector: Connector,
) -> None:
    """Check one local TCP endpoint and always close the probe socket."""

    try:
        connection = connector((host, port), timeout=timeout)
        connection.close()
    except (OSError, TimeoutError) as error:
        report.add(CheckStatus.FAIL, name, f"{host}:{port} is unavailable ({error})")
        return
    report.add(CheckStatus.PASS, name, f"{host}:{port} accepted a connection")


def diagnose(
    live_dir: Path,
    *,
    docker_prefix: Sequence[str] | None,
    timeout: float = 1.0,
    command_runner: CommandRunner = subprocess.run,
    connector: Connector = socket.create_connection,
) -> DoctorReport:
    """Run all read-only LabPulse deployment checks."""

    report = DoctorReport(live_dir=live_dir)
    if not live_dir.is_dir():
        report.add(
            CheckStatus.FAIL,
            "Installation",
            "directory is missing; run 'labpulse setup' first",
        )
        return report
    report.add(CheckStatus.PASS, "Installation", "live directory exists")

    compose_path = live_dir / "compose.yaml"
    compose_data: Any = None
    compose_services: set[str] = set()
    if not compose_path.is_file():
        report.add(CheckStatus.FAIL, "Compose file", f"missing {compose_path}")
    else:
        try:
            compose_data = _read_yaml(compose_path)
            services = compose_data.get("services") if isinstance(compose_data, dict) else None
            if not isinstance(services, dict) or not services:
                raise ValueError("services must be a non-empty mapping")
            compose_services = set(services)
        except (OSError, yaml.YAMLError, TypeError, ValueError) as error:
            report.add(CheckStatus.FAIL, "Compose file", _validation_detail(error))
        else:
            report.add(
                CheckStatus.PASS,
                "Compose file",
                f"{len(compose_services)} services are defined",
            )

    source_config_path = (live_dir / "config.yaml").resolve()
    source_config = _validate_config(report, source_config_path, "Source configuration")
    runtime_config_path = _runtime_config_path(live_dir, compose_data)
    if runtime_config_path == source_config_path.resolve():
        runtime_config = source_config
    else:
        runtime_config = _validate_config(
            report,
            runtime_config_path,
            "Runtime configuration",
        )

    generated_files = (
        live_dir / "homeassistant" / "config" / "configuration.yaml",
        live_dir
        / "homeassistant"
        / "config"
        / "packages"
        / "labpulse_generated.yaml",
        live_dir / "homeassistant" / "config" / "labpulse-dashboard.yaml",
    )
    missing_generated = [str(path.relative_to(live_dir)) for path in generated_files if not path.is_file()]
    if missing_generated:
        report.add(
            CheckStatus.FAIL,
            "Generated Home Assistant files",
            "missing " + ", ".join(missing_generated),
        )
    else:
        report.add(
            CheckStatus.PASS,
            "Generated Home Assistant files",
            "configuration, alarms, and dashboard are present",
        )

    _check_hardware(
        report,
        runtime_config,
        simulated=runtime_config_path.name == "config.fake.yaml",
    )

    if compose_services:
        _check_docker(
            report,
            live_dir,
            compose_services,
            docker_prefix,
            command_runner,
        )
    else:
        report.add(CheckStatus.SKIP, "Docker Compose", "compose.yaml is unavailable")
        report.add(CheckStatus.SKIP, "Containers", "compose.yaml is unavailable")

    # The generated deployment publishes Mosquitto on this host-only endpoint;
    # container config uses the Compose hostname instead.
    _check_tcp(report, "MQTT", "127.0.0.1", 1883, timeout, connector)
    _check_tcp(report, "Home Assistant", "127.0.0.1", 8123, timeout, connector)
    return report


def run_doctor(
    live_dir: Path,
    docker_prefix: Sequence[str] | None,
    *,
    timeout: float = 1.0,
) -> int:
    """Run diagnostics, print the report, and return its shell status."""

    report = diagnose(live_dir, docker_prefix=docker_prefix, timeout=timeout)
    print(report.render())
    return report.exit_code


if __name__ == "__main__":  # pragma: no cover - exposed through labpulse control.
    print("Run diagnostics with 'labpulse doctor'.", file=sys.stderr)
    raise SystemExit(2)
