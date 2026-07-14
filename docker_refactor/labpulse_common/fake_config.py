"""Apply narrowly scoped fake-hardware substitutions to live LabPulse YAML."""

from __future__ import annotations

import re
from textwrap import indent

import yaml
from yaml.nodes import MappingNode, ScalarNode


FAKE_UPS_PORT = "/tmp/labpulse-fake-serial/ups_monitor"
POWER_HARDWARE_KEYS = frozenset(
    {
        "driver",
        "parser",
        "serial_port",
        "baud_rate",
        "i2c_sensor",
        "i2c_bus",
        "i2c_address",
        "ina219_calibration",
        "ina219_config_register",
        "ina219_current_lsb_ma",
    }
)
DEFAULT_FAKE_POWER_SERVICE = {
    "enabled": True,
    "driver": "serial",
    "parser": "ups_simulator",
    "serial_port": FAKE_UPS_PORT,
    "baud_rate": 9600,
    "device_name": "UPS Monitor",
    "display": {
        "section": "UPS Power",
        "icon": "mdi:battery-charging",
        "order": 10,
    },
    "readings": [
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
    ],
    "reconnect_interval_seconds": 5,
    "read_interval_seconds": 1,
    "power_detection": {
        "source": "ups_voltage_inference",
        "low_voltage_threshold": 4.0,
        "outage_confirm_seconds": 10,
        "restore_confirm_seconds": 15,
        "maximum_reading_age_seconds": 15,
    },
}


def convert_power_service_to_fake_serial(text: str) -> str:
    """Switch one enabled power service to the UPS pseudo-serial endpoint.

    Only hardware transport keys inside the selected service are replaced.
    Labels, readings, dashboard metadata, battery settings, power timings,
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

    service_name = str(targets[0])
    root = yaml.compose(text)
    service_node = _mapping_value(_mapping_value(root, "services"), service_name)
    if not isinstance(service_node, MappingNode):
        raise ValueError(f"Power service '{service_name}' must be a YAML mapping")

    lines = text.splitlines(keepends=True)
    start = service_node.start_mark.line
    end = service_node.end_mark.line
    indent = service_node.start_mark.column
    key_pattern = re.compile(rf"^\s{{{indent}}}([A-Za-z0-9_]+)\s*:")
    retained: list[str] = []

    for line in lines[start:end]:
        match = key_pattern.match(line)
        if match and match.group(1) in POWER_HARDWARE_KEYS:
            continue
        retained.append(line)

    newline = "\r\n" if "\r\n" in text else "\n"
    prefix = " " * indent
    fake_transport = [
        f"{prefix}driver: serial{newline}",
        f"{prefix}parser: ups_simulator{newline}",
        f'{prefix}serial_port: "{FAKE_UPS_PORT}"{newline}',
        f"{prefix}baud_rate: 9600{newline}",
    ]
    lines[start:end] = fake_transport + retained
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
