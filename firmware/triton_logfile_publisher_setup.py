"""Small foreground publisher for commissioning a Triton-to-LabPulse link.

This setup version intentionally has few moving parts. Once the logfile path,
MQTT credentials, certificate, topic, and LabPulse mapping have been proven,
replace it with triton_logfile_publisher_production.py for unattended operation.
"""

import argparse
import json
import math
from pathlib import Path
import socket
import struct
import time
from typing import BinaryIO

import paho.mqtt.client as mqtt


def record_to_json(record: dict[str, float]) -> str:
    """Convert every named Triton value to LabPulse's final JSON contract."""

    recorded_at = record["Time(secs)"]
    if not math.isfinite(recorded_at) or recorded_at < 0:
        raise ValueError(f"Invalid Triton record time: {recorded_at}")
    measurements = {
        header: value if math.isfinite(value) else None
        for header, value in record.items()
    }
    return json.dumps(
        {
            "protocol": "labpulse.measurements",
            "version": 1,
            "recorded_at": recorded_at,
            "measurements": measurements,
        },
        allow_nan=False,
    )


def get_recent_logfile(directory: Path) -> Path:
    """Return the most recently modified Triton logfile."""

    logfiles = list(directory.glob("*.vcl"))
    if not logfiles:
        raise FileNotFoundError(f"No .vcl files found in directory {directory}")
    return max(logfiles, key=lambda path: path.stat().st_mtime)


def read_exact(logfile: BinaryIO, number_of_bytes: int, description: str) -> bytes:
    """Read an exact byte count or identify an incomplete logfile section."""

    data = logfile.read(number_of_bytes)
    if len(data) != number_of_bytes:
        raise ValueError(
            f"Incomplete {description}: expected {number_of_bytes} bytes, got {len(data)}"
        )
    return data


def decode_last_record(logfile_path: Path) -> tuple[int, dict[str, float]]:
    """Decode the newest complete record and its column headings."""

    values_offset = 0x3000
    headers_offset = 0x1800
    header_length = 32
    header_capacity = 184
    bytes_per_value = 8

    with logfile_path.open("rb") as logfile:
        logfile.seek(0, 2)
        value_section_size = logfile.tell() - values_offset

        logfile.seek(values_offset)
        raw_record_size = read_exact(
            logfile, bytes_per_value, "first record size"
        )
        record_size_value = struct.unpack("<d", raw_record_size)[0]
        if not math.isfinite(record_size_value):
            raise ValueError("Record size is not finite")
        if not record_size_value.is_integer():
            raise ValueError(f"Record size is not an integer: {record_size_value}")
        record_size = int(record_size_value)
        if record_size < bytes_per_value * 3:
            raise ValueError(f"Record size is too small: {record_size}")
        if record_size % bytes_per_value:
            raise ValueError(f"Record size is not divisible by 8: {record_size}")

        number_of_values = record_size // bytes_per_value
        if number_of_values > header_capacity:
            raise ValueError(f"Record contains too many values: {number_of_values}")
        number_of_records = value_section_size // record_size
        if number_of_records == 0:
            raise ValueError("No complete records are available yet")

        logfile.seek(values_offset + ((number_of_records - 1) * record_size))
        raw_record = read_exact(logfile, record_size, "last record")
        values = struct.unpack(f"<{number_of_values}d", raw_record)
        if values[0] != record_size:
            raise ValueError("The last record has an unexpected size field")

        logfile.seek(headers_offset)
        raw_headers = read_exact(
            logfile, header_length * number_of_values, "headers"
        )
        headers = [
            raw_headers[index:index + header_length].rstrip(b"\x00").decode("ascii")
            for index in range(0, len(raw_headers), header_length)
        ]

    if any(not header for header in headers):
        raise ValueError("An active header is empty")
    if "Time(secs)" not in headers:
        raise ValueError("Required header 'Time(secs)' is missing")
    if len(headers) != len(set(headers)):
        raise ValueError("The logfile contains duplicate headers")
    return number_of_records, dict(zip(headers, values, strict=True))


def parse_args(arguments: list[str] | None = None) -> argparse.Namespace:
    """Read the small set of settings needed for a commissioning run."""

    parser = argparse.ArgumentParser(
        description="Publish Triton logfile records to LabPulse in the foreground."
    )
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--broker", required=True)
    parser.add_argument("--port", type=int, default=8883)
    parser.add_argument("--topic", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password-file", required=True, type=Path)
    parser.add_argument("--ca-certificate", required=True, type=Path)
    return parser.parse_args(arguments)


def main() -> None:
    """Connect once and visibly publish each new complete Triton record."""

    args = parse_args()
    password = args.password_file.read_text(encoding="utf-8").splitlines()[0]

    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"Triton-setup-{socket.gethostname()}",
    )
    client.username_pw_set(args.username, password)
    client.tls_set(ca_certs=str(args.ca_certificate))
    client.connect(args.broker, args.port, keepalive=60)
    client.loop_start()

    print(f"Connected to {args.broker}:{args.port}; press Ctrl+C to stop.")
    last_record = None
    try:
        while True:
            logfile = get_recent_logfile(args.directory)
            record_number, record = decode_last_record(logfile)
            record_marker = (logfile, record_number, record["Time(secs)"])
            if record_marker != last_record:
                publication = client.publish(
                    args.topic,
                    record_to_json(record),
                    qos=1,
                    retain=False,
                )
                publication.wait_for_publish(timeout=5)
                if not publication.is_published():
                    raise ConnectionError("MQTT publication was not acknowledged")
                print(
                    f"Published record {record_number} from {logfile.name} "
                    f"with {len(record)} fields."
                )
                last_record = record_marker
            time.sleep(5)
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
