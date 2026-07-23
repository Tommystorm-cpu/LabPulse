"""Apply narrowly scoped fake-hardware substitutions to live LabPulse YAML."""

from __future__ import annotations

import json
from textwrap import indent

import yaml
from yaml.nodes import MappingNode, ScalarNode


FAKE_UPS_PORT = "/tmp/labpulse-fake-serial/ups_monitor"
DEFAULT_FAKE_POWER_SERVICE = {
    "enabled": True,
    "driver": {
        "type": "labpulse.serial_pipe",
        "options": {
            "port": FAKE_UPS_PORT,
            "baud_rate": 9600,
        },
    },
    "device_name": "UPS Monitor",
    "measurements": [
        {
            "name": "voltage",
            "label": "UPS Battery Voltage",
            "unit": "V",
            "device_class": "voltage",
        },
        {
            "name": "battery_level",
            "label": "UPS Battery Level",
            "unit": "%",
            "device_class": "battery",
        },
        {
            "name": "mains_present",
            "label": "External Power Present",
            "state_class": None,
        },
    ],
    "reconnect_interval_seconds": 5,
    "read_interval_seconds": 1,
    "maximum_measurement_age_seconds": 15,
    "power_detection": {
        "outage_confirm_seconds": 3,
        "restore_confirm_seconds": 5,
    },
}


def convert_power_service_to_fake_serial(text: str) -> str:
    """Switch one enabled power service to the UPS pseudo-serial endpoint.

    Only hardware transport keys inside the selected service are replaced.
    Labels, measurements, dashboard metadata, battery settings, power timings,
    comments elsewhere in the file, and the service's stable name are retained.
    """

    payload = yaml.safe_load(text) or {}
    services = payload.get("services", {})
    configured_power_services = [
        name
        for name, service in services.items()
        if isinstance(service, dict)
        and service.get("power_detection") is not None
    ]
    targets = [
        name
        for name in configured_power_services
        if services[name].get("enabled", True)
    ]
    if not targets:
        if configured_power_services:
            return text
        return _add_default_fake_power_service(text)
    if len(targets) > 1:
        raise ValueError(
            "-fake_usb supports one enabled power_detection service because "
            "there is one ups_monitor pseudo-serial endpoint"
        )

    return convert_service_to_fake_serial(text, str(targets[0]), FAKE_UPS_PORT)


def convert_service_to_fake_serial(
    text: str,
    service_name: str,
    port: str,
) -> str:
    """Replace one service's driver block while preserving surrounding YAML."""

    root = yaml.compose(text)
    service_node = _mapping_value(_mapping_value(root, "services"), service_name)
    if not isinstance(service_node, MappingNode):
        raise ValueError(f"Service '{service_name}' must be a YAML mapping")

    driver_key, driver_node = _mapping_entry(service_node, "driver")
    lines = text.splitlines(keepends=True)
    newline = "\r\n" if "\r\n" in text else "\n"
    prefix = " " * driver_key.start_mark.column
    replacement = [
        f"{prefix}driver:{newline}",
        f"{prefix}  type: labpulse.serial_pipe{newline}",
        f"{prefix}  options:{newline}",
        f"{prefix}    port: {json.dumps(port)}{newline}",
        f"{prefix}    baud_rate: 9600{newline}",
    ]
    lines[driver_key.start_mark.line : driver_node.end_mark.line] = replacement
    return "".join(lines)


def _add_default_fake_power_service(text: str) -> str:
    """Add an active simulator-safe UPS service beneath the services mapping."""

    root = yaml.compose(text)
    services_node = _mapping_value(root, "services")
    if not isinstance(services_node, MappingNode):
        raise ValueError("services must be a YAML mapping")

    lines = text.splitlines(keepends=True)
    insertion_line = services_node.end_mark.line
    for index, line in enumerate(lines):
        if line.startswith("# Live UPS example"):
            insertion_line = index
            break

    newline = "\r\n" if "\r\n" in text else "\n"
    dumped = yaml.safe_dump(
        {"ups_monitor": DEFAULT_FAKE_POWER_SERVICE},
        sort_keys=False,
        allow_unicode=True,
    )
    block = newline + indent(dumped, "  ").replace("\n", newline) + newline
    lines.insert(insertion_line, block)
    return "".join(lines)


def _mapping_value(node: object, key: str) -> object:
    """Return a named child value from a composed YAML mapping node."""

    if not isinstance(node, MappingNode):
        raise ValueError(f"Expected YAML mapping while locating '{key}'")
    for key_node, value_node in node.value:
        if isinstance(key_node, ScalarNode) and key_node.value == key:
            return value_node
    raise ValueError(f"Missing YAML mapping key: {key}")


def _mapping_entry(
    node: object,
    key: str,
) -> tuple[ScalarNode, object]:
    """Return one key/value node pair from a composed YAML mapping."""

    if not isinstance(node, MappingNode):
        raise ValueError(f"Expected YAML mapping while locating '{key}'")
    for key_node, value_node in node.value:
        if isinstance(key_node, ScalarNode) and key_node.value == key:
            return key_node, value_node
    raise ValueError(f"Missing YAML mapping key: {key}")
