import struct
from pathlib import Path
import math
import time
from typing import BinaryIO
import argparse
import json

import paho.mqtt.client as mqtt

DEFAULT_LOGFILE_DIRECTORY = Path(r"D:\LabPulse Tommy\Triton logfiles\logfiles")
DEFAULT_MQTT_PORT = 8883
DEFAULT_MQTT_TOPIC = "labpulse/triton/measurements"

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor the latest Triton logfile record."
    )

    parser.add_argument(
        "--directory",
        type=Path,
        default=DEFAULT_LOGFILE_DIRECTORY,
        help="Directory containing .vcl files (default: %(default)s)",
    )

    parser.add_argument("--broker", required=True, help="Hostname or IP address of the LabPulse MQTT broker")
    parser.add_argument("--port", type=int, default=DEFAULT_MQTT_PORT, help="MQTT broker port (default: %(default)s)")
    parser.add_argument("--topic", default=DEFAULT_MQTT_TOPIC, help="MQTT topic for Triton snapshots (default: %(default)s)")
    parser.add_argument("--username", help="MQTT username")
    parser.add_argument("--password-file", type=Path, help="File containing the MQTT password on its first line")
    parser.add_argument("--ca-certificate", type=Path, help="CA certificate used to verify the MQTT broker")

    return parser.parse_args()


def create_mqtt_client(args: argparse.Namespace) -> mqtt.Client:
    """Connect a background MQTT client using the requested security settings"""

    if args.password_file is not None and args.username is None:
        raise ValueError("--password-file requires --username")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="Triton-logfile-publisher")

    if args.username is not None:
        password = None
        if args.password_file is not None:
            password_lines = args.password_file.read_text(encoding="utf-8").splitlines()
            if not password_lines or not password_lines[0]:
                raise ValueError(f"MQTT password file is empty: {args.password_file}")
            password = password_lines[0]

        client.username_pw_set(args.username, password)

    if args.ca_certificate is not None:
        client.tls_set(ca_certs=str(args.ca_certificate))

    client.connect_async(args.broker, args.port, keepalive=60)
    client.loop_start()

    return client


def record_to_json(record: dict[str, float]) -> str:
    """Put every Triton value in one named JSON measurement message"""

    recorded_at = record["Time(secs)"]

    if not math.isfinite(recorded_at) or recorded_at < 0:
        raise ValueError(f"Invalid Triton record time: {recorded_at}")

    # JSON has no standard representation for NaN or infinity, so retain the
    # header with a null value when Triton reports a non-finite number.
    measurements = {
        header: value if math.isfinite(value) else None
        for header, value in record.items()
    }

    message = {
        "protocol": "labpulse.measurements",
        "version": 1,
        "recorded_at": recorded_at,
        "measurements": measurements,
    }

    return json.dumps(message, allow_nan=False)


def publish_record(client: mqtt.Client, topic: str, record: dict[str, float]) -> None:
    """Publish one complete record and wait for its MQTT acknowledgement"""

    if not client.is_connected():
        raise ConnectionError("MQTT broker is not connected")

    publication = client.publish(topic, record_to_json(record), qos=1, retain=False)
    publication.wait_for_publish(timeout=5)

    if not publication.is_published():
        raise ConnectionError("MQTT publication was not acknowledged")


def main() -> None:
    """Publish the latest complete Triton record every 5 seconds if it is new"""

    args = parse_args()
    client = create_mqtt_client(args)
    last_seen = None

    try:
        while True:
            try: # So the ValueErrors don't crash the program and it can try again on next poll
                latest_file = get_recent_logfile(args.directory)
                record_count, record = decode_last_record(latest_file)
                marker = (latest_file, record_count, record["Time(secs)"])

                if marker != last_seen:
                    publish_record(client, args.topic, record)
                    print(record)
                    last_seen = marker

            except (OSError, ValueError, ConnectionError, RuntimeError, mqtt.MQTTException) as error:
                print(f"Logfile or MQTT temporarily unavailable: {error}")

            time.sleep(5)

    finally:
        client.disconnect()
        client.loop_stop()


def get_recent_logfile(directory: Path) -> Path:
    """
    Gets the most recently modified logfile from the supplied directory
    """
    logfiles = list(directory.glob("*.vcl"))

    if not logfiles:
        raise FileNotFoundError(f"No .vcl files found in directory {directory}")

    most_recent = max(
        logfiles,
        key = lambda path: path.stat().st_mtime
    )

    return most_recent


def read_exact(logfile: BinaryIO, number_of_bytes: int, description: str) -> bytes:
    """
    .read() but with validation that the expected number of bytes were actually returned
    """

    data = logfile.read(number_of_bytes)

    if len(data) != number_of_bytes:
        raise ValueError(
            f"Incomplete {description}: expected {number_of_bytes} bytes, got {len(data)}"
        )

    return data


def decode_last_record(logfile_path: Path) -> tuple[int, dict[str, float]]:
    """
    Obtain and decode the last complete record of the file
    """

    # These constants are the same for every logfile
    VALUES_OFFSET = 0x3000 # Address the values start at
    HEADERS_OFFSET = 0x1800 # Address the headers start at
    HEADER_LENGTH = 32 # Length of one individual header in bytes
    HEADER_CAPACITY = 184 # Number of header slots reserved in the file (5888 / 32)
    BYTES_PER_VALUE = 8

    with logfile_path.open("rb") as logfile:
        # Get size of file
        logfile.seek(0, 2) # move cursor to end of file
        file_size = logfile.tell() # report cursor position
        value_section_size = file_size - VALUES_OFFSET # Size of the values section of the file

        # Read the first record to find linesize
        logfile.seek(VALUES_OFFSET)
        linesize_raw = read_exact(logfile, BYTES_PER_VALUE, "first record linesize") # Read the linesize (length of record)
        linesize_bytes = struct.unpack("<d", linesize_raw)[0]

        # Validate linesize before converting or dividing by it.
        if not math.isfinite(linesize_bytes):
            raise ValueError("Record size is not finite")

        if not linesize_bytes.is_integer():
            raise ValueError(f"Record size is not an integer: {linesize_bytes}")

        linesize_bytes = int(linesize_bytes)

        if linesize_bytes < BYTES_PER_VALUE*3: # < 3 values
            raise ValueError(f"Record size is too small: {linesize_bytes}")

        if linesize_bytes % BYTES_PER_VALUE != 0:
            raise ValueError(f"Record size is not divisible by 8: {linesize_bytes}")

        if linesize_bytes // BYTES_PER_VALUE > HEADER_CAPACITY:
            raise ValueError(f"Record contains too many values: {linesize_bytes // BYTES_PER_VALUE}")

        # Find the last record
        number_of_values = int(linesize_bytes // BYTES_PER_VALUE) # How many values in a record (equal to number of headers)
        number_of_records = value_section_size // linesize_bytes # discards remainder for last *complete* record

        if number_of_records == 0:
            raise ValueError("No complete records are available yet")

        last_record_address = VALUES_OFFSET + ((number_of_records - 1) * linesize_bytes)

        # Read the last record
        logfile.seek(last_record_address)
        last_record_raw = read_exact(logfile, linesize_bytes, "last record")

        values = struct.unpack(f"<{number_of_values}d", last_record_raw) # Decode values

        if values[0] != linesize_bytes:
            raise ValueError("The last record has an unexpected size field")

        # Get the headers
        logfile.seek(HEADERS_OFFSET)
        headers_raw = read_exact(logfile, HEADER_LENGTH*number_of_values, "headers") # Whole raw bytestring for all the headers
        headers_raw_split = [headers_raw[i:i+HEADER_LENGTH] for i in range(0, len(headers_raw), HEADER_LENGTH)] # Split headers into a list
        headers = [i.rstrip(b"\x00").decode("ascii") for i in headers_raw_split] # Decode headers

    if any(not header for header in headers):
        raise ValueError("An active header is empty")

    if "Time(secs)" not in headers:
        raise ValueError("Required header 'Time(secs)' is missing")

    if len(headers) != len(set(headers)):
        raise ValueError("The logfile contains duplicate headers")
    
    output = dict(zip(headers, values, strict=True))

    return number_of_records, output


if __name__ == "__main__":
    main()
