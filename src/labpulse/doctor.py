"""Read-only diagnostics for an installed LabPulse deployment."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any

import yaml

from labpulse import __version__
from labpulse.common.config import ConfigError, LabPulseConfig, format_config_error, load_config
from labpulse.hardware.registry import get_driver_definition


WATCHDOG_PATH = Path("/sys/class/watchdog/watchdog0")


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
        summary = (
            f"{counts[CheckStatus.PASS]} passed, {counts[CheckStatus.WARN]} warnings, "
            f"{counts[CheckStatus.FAIL]} failed, {counts[CheckStatus.SKIP]} skipped"
        )
        lines.extend(("", f"Summary: {summary}"))
        if self.exit_code:
            lines.append("Run 'labpulse logs' for service-level error details.")
        return "\n".join(lines)


def _validation_detail(error: Exception) -> str:
    """Return a concise first error suitable for a one-line report."""

    if isinstance(error, ConfigError):
        return format_config_error(error).replace("\n", "; ")
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


def _check_runtime_image(report: DoctorReport, compose_data: Any) -> None:
    """Report whether LabPulse services use the installed release's image."""

    expected = f"ghcr.io/tommystorm-cpu/labpulse:{__version__}"
    services = compose_data.get("services") if isinstance(compose_data, dict) else None
    if not isinstance(services, dict):
        report.add(CheckStatus.SKIP, "Runtime image", "compose.yaml is unavailable")
        return

    images = {
        service.get("image")
        for name, service in services.items()
        if isinstance(name, str)
        and name.startswith("labpulse-")
        and isinstance(service, dict)
    }
    if images == {expected}:
        report.add(CheckStatus.PASS, "Runtime image", f"{expected} matches the installed package")
        return

    rendered = ", ".join(sorted(str(image) for image in images)) or "none"
    report.add(
        CheckStatus.WARN,
        "Runtime image",
        f"installed package expects {expected}, Compose uses {rendered}; "
        "rerun 'labpulse setup' unless this is an intentional LABPULSE_IMAGE override",
    )


def _validate_config(report: DoctorReport, path: Path, name: str) -> LabPulseConfig | None:
    """Validate one LabPulse configuration and record its outcome."""

    if not path.is_file():
        report.add(CheckStatus.FAIL, name, f"missing {path}; run 'labpulse setup' to restore managed files")
        return None
    try:
        config = load_config(path).config
    except ConfigError as error:
        report.add(CheckStatus.FAIL, name, _validation_detail(error))
        return None

    enabled_services = sum(service.enabled for service in config.services.values())
    enabled_outputs = sum(output.enabled for output in config.outputs.values())
    report.add(
        CheckStatus.PASS,
        name,
        f"{path.name} is valid ({enabled_services} enabled hardware services, "
        f"{enabled_outputs} enabled outputs)",
    )
    return config


def _check_hardware(report: DoctorReport, config: LabPulseConfig | None, *, simulated: bool) -> None:
    """Check that configured driver resources are visible on the host."""

    if config is None:
        report.add(CheckStatus.SKIP, "Hardware resources", "runtime configuration is not valid")
        return

    service_paths: dict[str, set[Path]] = {}
    try:
        for service_name, service in config.services.items():
            if not service.enabled:
                continue
            requirements = get_driver_definition(service.driver.type).container_requirements(
                service.driver.options, simulated
            )
            paths = {Path(device.split(":", 1)[0]) for device in requirements.devices}
            paths.update(Path(mount.split(":", 1)[0]) for mount in requirements.mounts)
            port = getattr(service.driver.options, "port", None)
            if isinstance(port, str) and port:
                paths.add(Path(port))
            service_paths[service_name] = paths
        if not simulated:
            for output_name, output in config.outputs.items():
                if not output.enabled:
                    continue
                requirements = get_driver_definition(
                    output.driver.type
                ).container_requirements(output.driver.options, False)
                paths = {
                    Path(device.split(":", 1)[0])
                    for device in requirements.devices
                }
                paths.update(
                    Path(mount.split(":", 1)[0])
                    for mount in requirements.mounts
                )
                service_paths[f"output {output_name}"] = paths
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
                "missing "
                + ", ".join(missing)
                + "; check the cable, configured device path, and host permissions",
            )
        else:
            detail = ", ".join(sorted(str(path) for path in paths))
            report.add(CheckStatus.PASS, f"Hardware {service_name}", detail or "driver declares no host paths")


def _run(command: Sequence[str], live_dir: Path) -> subprocess.CompletedProcess[str]:
    """Run one bounded, non-interactive diagnostic command."""

    return subprocess.run(
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
) -> None:
    """Validate Compose syntax and compare expected with running services."""

    if docker_prefix is None:
        report.add(CheckStatus.FAIL, "Docker daemon", "Docker command is not configured correctly")
        report.add(CheckStatus.SKIP, "Docker Compose", "Docker daemon is unavailable")
        report.add(CheckStatus.SKIP, "Containers", "Docker Compose is unavailable")
        return

    command = [*docker_prefix, "compose"]
    try:
        engine = _run([*docker_prefix, "version", "--format", "{{.Server.Version}}"], live_dir)
    except (FileNotFoundError, PermissionError, subprocess.SubprocessError) as error:
        report.add(
            CheckStatus.FAIL,
            "Docker daemon",
            f"{error}; install/start Docker or correct LABPULSE_DOCKER_COMMAND",
        )
        report.add(CheckStatus.SKIP, "Docker Compose", "Docker daemon is unavailable")
        report.add(CheckStatus.SKIP, "Containers", "Docker Compose is unavailable")
        return
    if engine.returncode != 0:
        report.add(
            CheckStatus.FAIL,
            "Docker daemon",
            f"{_process_error(engine)}; check Docker service status and user permissions",
        )
        report.add(CheckStatus.SKIP, "Docker Compose", "Docker daemon is unavailable")
        report.add(CheckStatus.SKIP, "Containers", "Docker Compose is unavailable")
        return
    engine_version = engine.stdout.strip() or "version unavailable"
    report.add(CheckStatus.PASS, "Docker daemon", f"server {engine_version} is reachable")

    try:
        version = _run([*command, "version"], live_dir)
    except (FileNotFoundError, PermissionError, subprocess.SubprocessError) as error:
        report.add(CheckStatus.FAIL, "Docker Compose", str(error))
        report.add(CheckStatus.SKIP, "Containers", "Docker Compose is unavailable")
        return
    if version.returncode != 0:
        report.add(CheckStatus.FAIL, "Docker Compose", _process_error(version))
        report.add(CheckStatus.SKIP, "Containers", "Docker Compose is unavailable")
        return
    compose_version = version.stdout.strip().splitlines()
    report.add(CheckStatus.PASS, "Docker Compose", compose_version[-1] if compose_version else "command is available")

    try:
        validation = _run([*command, "config", "--quiet"], live_dir)
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
        running_result = _run([*command, "ps", "--status", "running", "--services"], live_dir)
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
            "not running: "
            + ", ".join(missing)
            + "; run 'labpulse up' and inspect 'labpulse logs SERVICE'",
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
) -> None:
    """Check one local TCP endpoint and always close the probe socket."""

    try:
        connection = socket.create_connection((host, port), timeout=timeout)
        connection.close()
    except (OSError, TimeoutError) as error:
        service = "mosquitto" if name == "MQTT" else "homeassistant"
        report.add(
            CheckStatus.FAIL,
            name,
            f"{host}:{port} is unavailable ({error}); "
            f"run 'labpulse restart {service}' and inspect its logs",
        )
        return
    report.add(CheckStatus.PASS, name, f"{host}:{port} accepted a connection")


def _check_clock(report: DoctorReport, live_dir: Path) -> None:
    """Report host timezone and NTP synchronization without changing either."""

    command = ["timedatectl", "show", "--property=Timezone", "--property=NTPSynchronized"]
    try:
        result = _run(command, live_dir)
    except (FileNotFoundError, PermissionError, subprocess.SubprocessError) as error:
        report.add(
            CheckStatus.WARN,
            "Host clock",
            f"could not query timedatectl ({error}); verify timezone and NTP manually",
        )
        return
    if result.returncode != 0:
        report.add(
            CheckStatus.WARN,
            "Host clock",
            f"{_process_error(result)}; run 'timedatectl status' and restore NTP",
        )
        return

    properties = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            properties[key.strip()] = value.strip()
    timezone = properties.get("Timezone", "unknown timezone")
    synchronized = properties.get("NTPSynchronized", "").lower() == "yes"
    if not synchronized:
        report.add(
            CheckStatus.WARN,
            "Host clock",
            f"{timezone}; NTP is not synchronized. Run 'timedatectl status' "
            "before trusting timestamps or alarm ordering",
        )
        return
    report.add(CheckStatus.PASS, "Host clock", f"{timezone}; NTP synchronized")


def _check_watchdog(
    report: DoctorReport,
    live_dir: Path,
) -> None:
    """Check that a hardware watchdog exists and systemd is servicing it."""

    if not WATCHDOG_PATH.exists():
        report.add(
            CheckStatus.WARN,
            "Hardware watchdog",
            "watchdog0 is unavailable; configure kernel_watchdog_timeout "
            "before relying on automatic recovery",
        )
        return
    try:
        command = ["systemctl", "show", "--property=RuntimeWatchdogUSec", "--value"]
        result = _run(command, live_dir)
    except (FileNotFoundError, PermissionError, subprocess.SubprocessError) as error:
        report.add(
            CheckStatus.WARN,
            "Hardware watchdog",
            f"could not query systemd ({error}); verify RuntimeWatchdogSec manually",
        )
        return
    if result.returncode != 0:
        report.add(
            CheckStatus.WARN,
            "Hardware watchdog",
            f"{_process_error(result)}; verify RuntimeWatchdogSec in system.conf",
        )
        return

    timeout = result.stdout.strip()
    if timeout.lower() in {"", "0", "0s", "0us", "off", "infinity"}:
        report.add(
            CheckStatus.WARN,
            "Hardware watchdog",
            "device exists but RuntimeWatchdogSec is disabled",
        )
        return
    report.add(
        CheckStatus.PASS,
        "Hardware watchdog",
        f"systemd runtime timeout is {timeout}",
    )


def diagnose(
    live_dir: Path,
    *,
    docker_prefix: Sequence[str] | None,
    timeout: float = 1.0,
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

    # Clock and watchdog settings live on the Raspberry Pi host rather than in
    # Docker, so check them before reasoning about generated container state.
    _check_clock(report, live_dir)
    _check_watchdog(report, live_dir)

    # compose.yaml tells diagnostics which services should exist and whether
    # containers mount the real or fake configuration file.
    compose_path = live_dir / "compose.yaml"
    compose_data: Any = None
    compose_services: set[str] = set()
    if not compose_path.is_file():
        report.add(CheckStatus.FAIL, "Compose file", f"missing {compose_path}")
    else:
        try:
            with compose_path.open("r", encoding="utf-8") as stream:
                compose_data = yaml.safe_load(stream)
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
    _check_runtime_image(report, compose_data)

    # config.yaml remains the user's source of truth. In fake USB mode the
    # containers instead read config.fake.yaml, so both files need checking.
    source_config_path = (live_dir / "config.yaml").resolve()
    source_config = _validate_config(report, source_config_path, "Source configuration")
    runtime_config_path = _runtime_config_path(live_dir, compose_data)
    simulated = runtime_config_path.name == "config.fake.yaml"
    if compose_data is None:
        report.add(
            CheckStatus.SKIP,
            "Runtime mode",
            "cannot determine mode until compose.yaml is valid",
        )
    else:
        report.add(
            CheckStatus.PASS,
            "Runtime mode",
            (
                "fake USB via config.fake.yaml"
                if simulated
                else "real hardware via config.yaml"
            ),
        )
    if runtime_config_path == source_config_path.resolve():
        runtime_config = source_config
    else:
        runtime_config = _validate_config(report, runtime_config_path, "Runtime configuration")

    # These are the three LabPulse-owned Home Assistant outputs. User-owned
    # automations.yaml, scripts.yaml, and scenes.yaml are deliberately excluded.
    generated_files = (
        live_dir / "homeassistant" / "config" / "configuration.yaml",
        live_dir / "homeassistant" / "config" / "packages" / "labpulse_generated.yaml",
        live_dir / "homeassistant" / "config" / "labpulse-dashboard.yaml",
    )
    missing_generated = [str(path.relative_to(live_dir)) for path in generated_files if not path.is_file()]
    if missing_generated:
        report.add(
            CheckStatus.FAIL,
            "Generated Home Assistant files",
            "missing "
            + ", ".join(missing_generated)
            + "; run 'labpulse config' to validate and regenerate them",
        )
    else:
        report.add(
            CheckStatus.PASS,
            "Generated Home Assistant files",
            "configuration, alarms, and dashboard are present",
        )

    _check_hardware(report, runtime_config, simulated=simulated)

    if compose_services:
        _check_docker(report, live_dir, compose_services, docker_prefix)
    else:
        report.add(CheckStatus.SKIP, "Docker Compose", "compose.yaml is unavailable")
        report.add(CheckStatus.SKIP, "Containers", "compose.yaml is unavailable")

    # The generated deployment publishes Mosquitto on this host-only endpoint;
    # container config uses the Compose hostname instead.
    _check_tcp(report, "MQTT", "127.0.0.1", 1883, timeout)
    _check_tcp(report, "Home Assistant", "127.0.0.1", 8123, timeout)
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
