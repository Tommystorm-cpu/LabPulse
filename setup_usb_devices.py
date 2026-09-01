#!/usr/bin/env python3
"""Interactively assign stable USB serial paths to LabPulse services."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Sequence


def _use_managed_python_when_deployed() -> None:
    """Re-execute deployed commands with LabPulse's managed interpreter."""

    project_dir = Path(__file__).resolve().parent
    default_python = project_dir / ".venv/bin/python"
    if not default_python.is_file() and "LABPULSE_PYTHON" not in os.environ:
        return
    configured = os.environ.get("LABPULSE_PYTHON")
    python_path = Path(configured) if configured else default_python
    if not python_path.is_file():
        raise SystemExit(
            f"ERROR: LabPulse's managed Python environment is missing: {python_path}\n"
            "Run 'labpulse setup' to restore the managed environment."
        )
    if Path(sys.executable).resolve() != python_path.resolve():
        # Replace this process rather than starting a child, so signals and the
        # final exit code still belong to the command the operator launched.
        os.execv(str(python_path), [str(python_path), *sys.argv])


if __name__ == "__main__":
    _use_managed_python_when_deployed()

from labpulse.common.config import (
    ConfigError,
    format_config_error,
    load_config,
)
REAL_DEVICE_DIR = Path("/dev/serial/by-id")
FAKE_DEVICE_DIR = Path("/tmp/labpulse-fake-serial")


@dataclass(frozen=True)
class SerialService:
    """One enabled serial service requiring a physical endpoint assignment."""

    name: str
    label: str


def load_serial_services(config_path: Path) -> list[SerialService]:
    """Load enabled serial services in config order without changing the file."""

    document = load_config(config_path)
    services: list[SerialService] = []
    for name, config in document.config.services.items():
        if config.enabled and config.driver.type == "labpulse.serial_pipe":
            services.append(SerialService(name=name, label=config.label or name))
    return services


def snapshot_devices(device_dir: Path) -> dict[str, str]:
    """Return stable public paths for currently connected serial symlinks."""

    if not device_dir.is_dir():
        return {}
    # /dev/serial/by-id contains stable symlinks rather than the changeable
    # /dev/ttyUSB0-style names underneath them.
    return {
        entry.name: str(device_dir / entry.name)
        for entry in sorted(device_dir.iterdir(), key=lambda item: item.name)
        if entry.is_symlink()
    }


def identify_devices(
    services: list[SerialService],
    device_dir: Path,
) -> dict[str, str]:
    """Identify one endpoint per service through guided unplug/replug changes."""

    input(
        "Start with every USB serial device plugged in, then press Enter to scan. "
    )
    baseline = snapshot_devices(device_dir)
    if len(baseline) < len(services):
        raise RuntimeError(
            f"Found {len(baseline)} serial device(s), but {len(services)} enabled "
            "serial service(s) need assignments"
        )

    assignments: dict[str, str] = {}
    used_devices: set[str] = set()
    for service in services:
        input(
            f"Unplug the USB device for {service.label} ({service.name}), "
            "then press Enter. "
        )
        unplugged = snapshot_devices(device_dir)
        # Set subtraction leaves the name that existed before unplugging but is
        # absent now. Exactly one disappearance identifies one physical device.
        missing = set(baseline) - set(unplugged)
        if len(missing) != 1:
            raise RuntimeError(
                f"Expected exactly one device to disappear for {service.name}; "
                f"detected {sorted(missing)!r}. Reconnect everything and rerun."
            )
        device_name = missing.pop()
        if device_name in used_devices:
            raise RuntimeError(f"Device {device_name} was already assigned")

        input(
            f"Detected {baseline[device_name]}. Replug it, then press Enter. "
        )
        replugged = snapshot_devices(device_dir)
        if device_name not in replugged:
            raise RuntimeError(
                f"{baseline[device_name]} did not return. Reconnect it and rerun."
            )

        assignments[service.name] = baseline[device_name]
        used_devices.add(device_name)
        baseline = replugged

    return assignments


def replace_serial_ports(
    config_text: str,
    assignments: dict[str, str],
    *,
    source: Path,
) -> str:
    """Replace only assigned nested driver port lines, preserving other text."""

    lines = config_text.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in config_text else "\n"
    # Work with the original lines rather than dumping parsed YAML, because the
    # explanatory comments and the user's formatting should survive this edit.
    services_index = next(
        (index for index, line in enumerate(lines) if re.match(r"^services:\s*(?:#.*)?$", line.rstrip("\r\n"))),
        None,
    )
    if services_index is None:
        raise ValueError("Config has no top-level services mapping")

    for service_name, port in assignments.items():
        # Locate this service's top-level two-space header, then stop at the next
        # service or top-level config section.
        header_pattern = re.compile(rf"^  {re.escape(service_name)}:\s*(?:#.*)?$")
        start = next(
            (
                index
                for index in range(services_index + 1, len(lines))
                if header_pattern.match(lines[index].rstrip("\r\n"))
            ),
            None,
        )
        if start is None:
            raise ValueError(f"Service block not found: {service_name}")

        end = len(lines)
        for index in range(start + 1, len(lines)):
            stripped = lines[index].rstrip("\r\n")
            if re.match(r"^  [A-Za-z0-9_-]+:\s*(?:#.*)?$", stripped):
                end = index
                break
            if stripped and not stripped.startswith(" ") and not stripped.startswith("#"):
                end = index
                break

        # json.dumps supplies valid YAML quoting for unusual path characters.
        replacement = f"        port: {json.dumps(port)}{newline}"
        port_index = next(
            (
                index
                for index in range(start + 1, end)
                if re.match(r"^        port:\s*", lines[index])
            ),
            None,
        )
        if port_index is not None:
            lines[port_index] = replacement
            continue

        # Older configs may omit the optional port line. Insert it directly
        # below driver.options when there is no existing line to replace.
        insert_after = next(
            (
                index
                for index in range(start + 1, end)
                if re.match(r"^      options:\s*", lines[index])
            ),
            None,
        )
        if insert_after is None:
            raise ValueError(
                f"Serial driver options block not found: {service_name}"
            )
        lines.insert(insert_after + 1, replacement)

    # Validate the complete edited document and confirm each typed driver model
    # received the intended path before anything is written to disk.
    updated = "".join(lines)
    document = load_config(source, text=updated)
    for service_name, port in assignments.items():
        options = document.config.services[service_name].driver.options
        actual = getattr(options, "port", None)
        if actual != port:
            raise ValueError(f"Failed to update driver port for {service_name}")
    return updated


def write_config(config_path: Path, updated_text: str) -> Path:
    """Atomically write config after keeping one non-proliferating backup."""

    backup_path = config_path.with_name(config_path.name + ".usb-setup-backup")
    shutil.copy2(config_path, backup_path)
    temporary_name: str | None = None
    try:
        # Write beside config.yaml and replace it only after the complete file is
        # safely closed, so interruption cannot leave a partial configuration.
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=config_path.parent,
            prefix=config_path.name + ".usb-setup-",
            delete=False,
        ) as temporary:
            temporary.write(updated_text)
            temporary_name = temporary.name
        os.chmod(temporary_name, config_path.stat().st_mode)
        os.replace(temporary_name, config_path)
    except Exception:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
        raise
    return backup_path


def build_parser() -> argparse.ArgumentParser:
    """Build the USB assignment helper command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument(
        "--fake-usb",
        action="store_true",
        help="identify simulator endpoints instead of /dev/serial/by-id",
    )
    parser.add_argument("--device-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help="detect and preview without writing config")
    parser.add_argument("--yes", action="store_true", help="apply the detected mapping without a final prompt")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the interactive stable USB assignment workflow."""

    args = build_parser().parse_args(argv)
    config_path = args.config.expanduser().resolve()
    device_dir = args.device_dir or (FAKE_DEVICE_DIR if args.fake_usb else REAL_DEVICE_DIR)
    try:
        services = load_serial_services(config_path)
        if not services:
            print("No enabled serial services were found; nothing to assign.")
            return 0

        print(f"Config: {config_path}")
        print(f"Device directory: {device_dir}")
        print("Serial services to identify:")
        for service in services:
            print(f"  {service.name}: {service.label}")

        assignments = identify_devices(services, device_dir)
        print("\nDetected assignments:")
        for service in services:
            print(f"  {service.name}: {assignments[service.name]}")

        original = config_path.read_text(encoding="utf-8")
        updated = replace_serial_ports(original, assignments, source=config_path)
        if args.dry_run:
            print("\nDry run complete; config was not changed.")
            return 0
        if not args.yes:
            answer = input("\nApply these serial driver port assignments? [y/N] ").strip().lower()
            if answer not in {"y", "yes"}:
                print("Config was not changed.")
                return 0

        backup_path = write_config(config_path, updated)
        print(f"Updated {config_path}")
        print(f"Previous config saved at {backup_path}")
        print("Regenerate Compose before restarting LabPulse services.")
        return 0
    except ConfigError as error:
        print(format_config_error(error), file=sys.stderr)
        return 1
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
