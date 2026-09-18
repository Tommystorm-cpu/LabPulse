"""Interactively assign stable USB serial paths to LabPulse services."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
import tempfile

from labpulse.common.config import (
    ConfigError,
    format_config_error,
    load_config,
)


REAL_DEVICE_DIR = Path("/dev/serial/by-id")


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

        # Configs may omit the optional port line. Insert it directly
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

    backup_directory = config_path.parent / "backups"
    backup_directory.mkdir(exist_ok=True)
    backup_path = backup_directory / (config_path.name + ".usb-setup-backup")
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


def run_usb_setup(config_path: Path, *, dry_run: bool = False, assume_yes: bool = False) -> int:
    """Guide USB identification and save confirmed assignments to the live config."""

    config_path = config_path.expanduser().resolve()
    device_dir = REAL_DEVICE_DIR
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

        command = f"labpulse --live-dir {shlex.quote(str(config_path.parent))}"
        print("\nBefore unplugging boards, stop LabPulse workers in another terminal:")
        print(f"  {command} down")
        print("Close any Arduino serial monitors. Then follow the prompts below.")
        assignments = identify_devices(services, device_dir)
        print("\nDetected assignments:")
        for service in services:
            print(f"  {service.name}: {assignments[service.name]}")

        original = config_path.read_text(encoding="utf-8")
        updated = replace_serial_ports(original, assignments, source=config_path)
        if dry_run:
            print("\nDry run complete; config was not changed.")
            return 0
        if not assume_yes:
            answer = input("\nApply these serial driver port assignments? [y/N] ").strip().lower()
            if answer not in {"y", "yes"}:
                print("Config was not changed.")
                return 0

        backup_path = write_config(config_path, updated)
        print(f"Updated {config_path}")
        print(f"Previous config saved at {backup_path}")
        print("\nApply the new mappings with:")
        print(f"  {command} config config.yaml")
        print("Save and close the editor to regenerate and apply the configuration.")
        print("Then ensure the services are running:")
        print(f"  {command} up")
        return 0
    except (EOFError, KeyboardInterrupt):
        print("\nUSB setup cancelled; config was not changed.", file=sys.stderr)
        return 130
    except ConfigError as error:
        print(format_config_error(error), file=sys.stderr)
        return 1
    except (KeyError, OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
