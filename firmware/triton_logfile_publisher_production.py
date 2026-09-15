"""Production Triton logfile publisher for unattended Windows operation."""

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import math
from pathlib import Path
import re
import socket
import struct
import time
from typing import BinaryIO

import paho.mqtt.client as mqtt
from paho.mqtt import MQTTException


DEFAULT_MQTT_PORT = 8883
DEFAULT_MQTT_TOPIC = "labpulse/triton/measurements"
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 15.0


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


def default_client_id() -> str:
    """Return a stable MQTT identity unique to the Windows computer."""

    computer_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", socket.gethostname()).strip("-")
    return f"Triton-logfile-publisher-{computer_name or 'unknown'}"


def parse_args(arguments: list[str] | None = None) -> argparse.Namespace:
    """Parse and validate publisher settings supplied by the operator."""

    parser = argparse.ArgumentParser(
        description="Publish the latest complete Triton logfile record to LabPulse."
    )
    parser.add_argument(
        "--directory", type=Path, required=True,
        help="Directory containing the control PC's .vcl files",
    )
    parser.add_argument(
        "--broker", required=True,
        help="Hostname or IP address of the LabPulse MQTT broker",
    )
    parser.add_argument(
        "--port", type=int, default=DEFAULT_MQTT_PORT,
        help="MQTT broker port (default: %(default)s)",
    )
    parser.add_argument(
        "--topic", default=DEFAULT_MQTT_TOPIC,
        help="MQTT topic for Triton snapshots (default: %(default)s)",
    )
    parser.add_argument(
        "--heartbeat-topic", required=True,
        help="per-fridge MQTT topic ending in /heartbeat",
    )
    parser.add_argument(
        "--heartbeat-interval", type=float, default=DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        help="seconds between script heartbeats (default: %(default)s)",
    )
    parser.add_argument(
        "--client-id", default=default_client_id(),
        help="stable unique MQTT client ID (default includes this computer name)",
    )
    parser.add_argument("--username", help="MQTT username; required for secure operation")
    parser.add_argument(
        "--password-file", type=Path,
        help="file containing the MQTT password on its first line",
    )
    parser.add_argument(
        "--ca-certificate", type=Path,
        help="CA certificate used to verify the MQTT broker",
    )
    parser.add_argument(
        "--insecure", action="store_true",
        help="explicitly allow unencrypted MQTT for isolated testing only",
    )
    parser.add_argument(
        "--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS,
        help="seconds between logfile checks (default: %(default)s)",
    )
    parser.add_argument(
        "--log-file", type=Path,
        help="also append operational logs to this file",
    )

    args = parser.parse_args(arguments)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if not math.isfinite(args.poll_interval) or args.poll_interval <= 0:
        parser.error("--poll-interval must be greater than zero")
    if not math.isfinite(args.heartbeat_interval) or args.heartbeat_interval <= 0:
        parser.error("--heartbeat-interval must be greater than zero")
    if "+" in args.topic or "#" in args.topic or not args.topic.strip():
        parser.error("--topic must be one exact non-empty MQTT topic")
    if (
        "+" in args.heartbeat_topic or "#" in args.heartbeat_topic
        or not args.heartbeat_topic.endswith("/heartbeat")
        or args.topic in {args.heartbeat_topic, availability_topic(args.heartbeat_topic)}
    ):
        parser.error("--heartbeat-topic must be an exact /heartbeat topic distinct from measurements")
    if not args.client_id.strip():
        parser.error("--client-id must not be blank")
    if args.insecure:
        if args.ca_certificate is not None:
            parser.error("--ca-certificate cannot be combined with --insecure")
    elif args.ca_certificate is None:
        parser.error(
            "secure operation requires --ca-certificate "
            "(or explicitly use --insecure for testing)"
        )
    if (args.username is None) != (args.password_file is None):
        parser.error("--username and --password-file must be supplied together")
    if not args.insecure and args.username is None:
        parser.error("secure operation requires --username and --password-file")
    return args


def availability_topic(heartbeat_topic: str) -> str:
    """Return the retained availability topic beside one fridge heartbeat."""

    return heartbeat_topic.removesuffix("heartbeat") + "availability"


def create_mqtt_client(args: argparse.Namespace) -> mqtt.Client:
    """Connect a reconnecting MQTT client using validated security settings."""

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=args.client_id)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.will_set(availability_topic(args.heartbeat_topic), "offline", qos=1, retain=True)

    def on_connect(
        connected_client: mqtt.Client,
        _userdata: object,
        _flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        if reason_code == 0:
            logging.info("Connected to LabPulse MQTT broker %s:%s", args.broker, args.port)
            availability = connected_client.publish(
                availability_topic(args.heartbeat_topic), "online", qos=1, retain=True
            )
            if availability.rc != mqtt.MQTT_ERR_SUCCESS:
                logging.error("Could not publish online availability: MQTT result %s", availability.rc)
        else:
            logging.error("MQTT connection rejected: %s", reason_code)

    def on_disconnect(
        _client: mqtt.Client,
        _userdata: object,
        _disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        _properties: mqtt.Properties | None,
    ) -> None:
        if reason_code != 0:
            logging.warning(
                "MQTT connection lost (%s); reconnecting in the background", reason_code
            )

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect

    if args.username is not None:
        password_lines = args.password_file.read_text(encoding="utf-8").splitlines()
        if not password_lines or not password_lines[0]:
            raise ValueError(f"MQTT password file is empty: {args.password_file}")
        client.username_pw_set(args.username, password_lines[0])

    if not args.insecure:
        if not args.ca_certificate.is_file():
            raise FileNotFoundError(
                f"MQTT CA certificate does not exist: {args.ca_certificate}"
            )
        client.tls_set(ca_certs=str(args.ca_certificate))

    client.connect_async(args.broker, args.port, keepalive=60)
    client.loop_start()
    return client


def publish_record(client: mqtt.Client, topic: str, record: dict[str, float]) -> None:
    """Publish one complete record and wait for its MQTT acknowledgement."""

    if not client.is_connected():
        raise ConnectionError("MQTT broker is not connected")
    publication = client.publish(topic, record_to_json(record), qos=1, retain=False)
    publication.wait_for_publish(timeout=5)
    if not publication.is_published():
        raise ConnectionError("MQTT publication was not acknowledged")


def publish_heartbeat(client: mqtt.Client, topic: str) -> None:
    """Report one completed pass through the publisher's main loop."""

    if not client.is_connected():
        raise ConnectionError("MQTT broker is not connected")
    publication = client.publish(topic, "alive", qos=1, retain=False)
    publication.wait_for_publish(timeout=5)
    if not publication.is_published():
        raise ConnectionError("MQTT heartbeat was not acknowledged")


def main() -> None:
    """Publish each newest complete Triton record once until interrupted."""

    args = parse_args()
    logging_handlers: list[logging.Handler] = [logging.StreamHandler()]
    if args.log_file is not None:
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        logging_handlers.append(
            RotatingFileHandler(
                args.log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
        )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=logging_handlers,
    )

    if not args.directory.is_dir():
        raise SystemExit(f"ERROR: Triton logfile directory does not exist: {args.directory}")
    try:
        client = create_mqtt_client(args)
    except (OSError, ValueError) as error:
        raise SystemExit(f"ERROR: Could not configure MQTT: {error}") from error
    last_seen = None
    next_logfile_check_at = time.monotonic()
    next_heartbeat_at = time.monotonic()

    try:
        while True:
            current_time = time.monotonic()
            # Logfile checks and heartbeats have separate clocks, so either
            # interval can run without waiting for the other one.
            if current_time >= next_logfile_check_at:
                try:
                    latest_file = get_recent_logfile(args.directory)
                    record_count, record = decode_last_record(latest_file)
                    marker = (latest_file, record_count, record["Time(secs)"])
                    if marker != last_seen:
                        publish_record(client, args.topic, record)
                        logging.info(
                            "Published record %s from %s (%s measurements)",
                            record_count, latest_file.name, len(record),
                        )
                        last_seen = marker
                except (
                    OSError, ValueError, ConnectionError, RuntimeError, MQTTException
                ) as error:
                    logging.warning("Logfile or MQTT temporarily unavailable: %s", error)
                next_logfile_check_at = time.monotonic() + args.poll_interval

            if time.monotonic() >= next_heartbeat_at:
                try:
                    publish_heartbeat(client, args.heartbeat_topic)
                except (OSError, ConnectionError, RuntimeError, MQTTException) as error:
                    logging.warning("MQTT heartbeat temporarily unavailable: %s", error)
                next_heartbeat_at = time.monotonic() + args.heartbeat_interval

            time.sleep(max(0.0, min(next_logfile_check_at, next_heartbeat_at) - time.monotonic()))
    except KeyboardInterrupt:
        logging.info("Triton logfile publisher stopped")
    finally:
        try:
            if client.is_connected():
                offline = client.publish(
                    availability_topic(args.heartbeat_topic), "offline", qos=1, retain=True
                )
                offline.wait_for_publish(timeout=2)
        except (OSError, RuntimeError, MQTTException) as error:
            logging.warning("Could not publish clean offline availability: %s", error)
        finally:
            client.disconnect()
            client.loop_stop()


if __name__ == "__main__":
    main()
