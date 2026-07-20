#!/usr/bin/env python3
"""Run and control LabPulse pseudo-serial devices without physical hardware."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import random
import signal
import socket
import subprocess
import sys
import time
from typing import Any, Sequence


DEFAULT_SIM_DIR = Path(
    os.environ.get("LABPULSE_FAKE_SERIAL_DIR", "/tmp/labpulse-fake-serial")
)
DEFAULT_INTERVAL = float(os.environ.get("LABPULSE_FAKE_SERIAL_INTERVAL", "1"))
CONTROL_SOCKET_NAME = "control.sock"
DEVICE_NAMES = (
    "pressure",
    "pump_room",
    "turbo_pump",
    "room_environment",
    "ups_monitor",
)
DEVICE_ALIASES = {
    "pressure_monitor": "pressure",
    "pressure": "pressure",
    "pump_room": "pump_room",
    "turbo_pump": "turbo_pump",
    "room_environment": "room_environment",
    "ups_monitor": "ups_monitor",
}
SCENARIO_STATES = ("normal", "recover", "danger-low", "danger-high", "stale")
UPS_SCENARIO_STATES = ("mains", "battery", "stale")
SCENARIO_TARGETS = (
    "pressure_monitor.pressure",
    "pump_room.flow1",
    "pump_room.flow2",
    "pump_room.temp0",
    "pump_room.temp1",
    "pump_room.temp2",
    "pump_room.temp3",
    "pump_room.roomtemp",
    "pump_room.roomhum",
    "pump_room.press1",
    "pump_room.press2",
    "turbo_pump.flow1",
    "turbo_pump.flow2",
    "turbo_pump.temp0",
    "turbo_pump.temp1",
    "turbo_pump.temp2",
    "turbo_pump.temp3",
    "room_environment.temperature",
    "room_environment.humidity",
    "ups_monitor.power",
)


def validate_scenario(target: str, state: str) -> None:
    """Raise a useful error for an unsupported scenario target or state."""

    if target not in SCENARIO_TARGETS:
        raise ValueError(f"Unsupported scenario target: {target}")
    allowed_states = (
        UPS_SCENARIO_STATES if target == "ups_monitor.power" else SCENARIO_STATES
    )
    if state not in allowed_states:
        raise ValueError(f"Unsupported scenario state: {state}")


def normalize_device_name(name: str) -> str:
    """Return the simulator endpoint name for a service/device alias."""

    try:
        return DEVICE_ALIASES[name]
    except KeyError as error:
        raise ValueError(f"Unsupported simulator device: {name}") from error


def parse_scenario_assignment(assignment: str) -> tuple[str, str]:
    """Parse a TARGET=STATE command-line assignment."""

    if "=" not in assignment:
        raise ValueError("Scenario must use TARGET=STATE")
    target, state = assignment.split("=", 1)
    validate_scenario(target, state)
    return target, state


def receive_message(connection: socket.socket) -> dict[str, Any]:
    """Receive one newline-delimited JSON message from a Unix socket."""

    chunks = bytearray()
    while b"\n" not in chunks:
        chunk = connection.recv(4096)
        if not chunk:
            break
        chunks.extend(chunk)
        if len(chunks) > 65536:
            raise ValueError("Simulator control message is too large")
    if not chunks:
        raise ValueError("Simulator control message is empty")
    return json.loads(bytes(chunks).split(b"\n", 1)[0].decode("utf-8"))


class MeasurementGenerator:
    """Generate the serial payloads emitted by the simulated devices."""

    def __init__(
        self,
        scenarios: dict[str, str] | None = None,
        seed: int | None = None,
    ) -> None:
        """Create a generator with optional initial scenarios and random seed."""

        self.scenarios = dict(scenarios or {})
        self.random = random.Random(seed)
        for target, state in self.scenarios.items():
            validate_scenario(target, state)

    def set_scenario(self, target: str, state: str) -> None:
        """Set one measurement's simulated behavior."""

        validate_scenario(target, state)
        self.scenarios[target] = state

    def clear_scenario(self, target: str) -> None:
        """Return one measurement to its default random behavior."""

        if target not in SCENARIO_TARGETS:
            raise ValueError(f"Unsupported scenario target: {target}")
        self.scenarios.pop(target, None)

    def reset(self) -> None:
        """Return every measurement to its default random behavior."""

        self.scenarios.clear()

    def _integer_value(
        self,
        target: str,
        random_range: tuple[int, int],
        normal_range: tuple[int, int],
        low_range: tuple[int, int],
        high_range: tuple[int, int],
        stale_value: int,
    ) -> int:
        """Select an integer-scaled value for one measurement and scenario."""

        state = self.scenarios.get(target)
        if state is None:
            bounds = random_range
        elif state in {"normal", "recover"}:
            bounds = normal_range
        elif state == "danger-low":
            bounds = low_range
        elif state == "danger-high":
            bounds = high_range
        else:
            return stale_value
        return self.random.randint(*bounds)

    def _hundredths(self, target: str, turbo: bool = False) -> str:
        """Return one flow measurement with two decimal places."""

        random_range = (150, 420) if turbo else (150, 550)
        value = self._integer_value(
            target,
            random_range=random_range,
            normal_range=(250, 275),
            low_range=(5, 20),
            high_range=(120000, 121000),
            stale_value=250,
        )
        return f"{value / 100:.2f}"

    def _temperature(self, target: str, turbo: bool = False) -> str:
        """Return one temperature measurement with one decimal place."""

        random_range = (205, 260) if turbo else (185, 235)
        value = self._integer_value(
            target,
            random_range=random_range,
            normal_range=(215, 225),
            low_range=(0, 5),
            high_range=(600, 610),
            stale_value=220,
        )
        return f"{value / 10:.1f}"

    def _humidity(self, target: str) -> str:
        """Return room humidity with one decimal place."""

        value = self._integer_value(
            target,
            random_range=(350, 650),
            normal_range=(495, 505),
            low_range=(50, 55),
            high_range=(900, 910),
            stale_value=500,
        )
        return f"{value / 10:.1f}"

    def _pump_pressure(self, target: str) -> str:
        """Return one pump-room pressure measurement in bar."""

        value = self._integer_value(
            target,
            random_range=(80, 160),
            normal_range=(120, 140),
            low_range=(5, 20),
            high_range=(120000, 121000),
            stale_value=125,
        )
        return f"{value / 100:.2f}"

    def _pressure_mpa(self) -> str:
        """Return simulated compressed-air pressure in MPa."""

        state = self.scenarios.get("pressure_monitor.pressure")
        if state is None:
            return f"0.{self.random.randint(1200, 1300):04d}"
        if state in {"normal", "recover"}:
            return f"0.{self.random.randint(1200, 1250):04d}"
        if state == "danger-low":
            return f"0.{self.random.randint(500, 590):04d}"
        if state == "danger-high":
            return f"{self.random.randint(120, 121)}.{self.random.randint(0, 9999):04d}"
        return "0.1200"

    def _ups_payload(self) -> str | None:
        """Return normalized UPS telemetry, or no line for a stale scenario."""

        state = self.scenarios.get("ups_monitor.power", "mains")
        if state == "stale":
            return None
        if state == "battery":
            voltage, battery_level, mains_present = 3.95, 79.2, 0
        else:
            voltage, battery_level, mains_present = 4.13, 94.2, 1
        return (
            f"Voltage: {voltage:.3f} V | BatteryLevel: {battery_level:.1f} % "
            f"| mains_present: {mains_present}\n"
        )

    def _is_stale(self, target: str) -> bool:
        """Return whether a simulated measurement should stop being emitted."""

        return self.scenarios.get(target) == "stale"

    @staticmethod
    def _firmware_payload(device: str, measurements: dict[str, float]) -> str:
        """Return one compact schema-1 firmware JSON line."""

        return json.dumps(
            {
                "device": device,
                "schema": 1,
                "firmware": "simulator",
                "type": "sample",
                "measurements": measurements,
            },
            separators=(",", ":"),
        ) + "\n"

    def payloads(self) -> dict[str, str]:
        """Build one complete emission for every simulated serial device."""

        pump_measurements: dict[str, float] = {}
        for index in (1, 2):
            target = f"pump_room.flow{index}"
            if not self._is_stale(target):
                pump_measurements[f"flow{index}"] = float(self._hundredths(target))

        for index in range(4):
            target = f"pump_room.temp{index}"
            if not self._is_stale(target):
                pump_measurements[f"temp{index}"] = float(self._temperature(target))

        if not self._is_stale("pump_room.roomtemp"):
            pump_measurements["roomtemp"] = float(
                self._temperature("pump_room.roomtemp")
            )
        if not self._is_stale("pump_room.roomhum"):
            pump_measurements["roomhum"] = float(self._humidity("pump_room.roomhum"))
        for index in (1, 2):
            target = f"pump_room.press{index}"
            if not self._is_stale(target):
                pump_measurements[f"press{index}"] = float(
                    self._pump_pressure(target)
                )

        turbo_measurements: dict[str, float] = {}
        for index in (1, 2):
            target = f"turbo_pump.flow{index}"
            if not self._is_stale(target):
                turbo_measurements[f"flow{index}"] = float(
                    self._hundredths(target, turbo=True)
                )
        for index in range(4):
            target = f"turbo_pump.temp{index}"
            if not self._is_stale(target):
                turbo_measurements[f"temp{index}"] = float(
                    self._temperature(target, turbo=True)
                )

        room_parts = []
        if not self._is_stale("room_environment.temperature"):
            room_parts.append(
                "temperature:"
                f"{self._temperature('room_environment.temperature')}"
            )
        if not self._is_stale("room_environment.humidity"):
            room_parts.append(
                f"humidity:{self._humidity('room_environment.humidity')}"
            )

        payloads: dict[str, str] = {}
        if not self._is_stale("pressure_monitor.pressure"):
            payloads["pressure"] = self._firmware_payload(
                "pressure_monitor",
                {"pressure": round(float(self._pressure_mpa()) * 10.0, 4)},
            )
        if pump_measurements:
            payloads["pump_room"] = self._firmware_payload(
                "pump_room", pump_measurements
            )
        if turbo_measurements:
            payloads["turbo_pump"] = self._firmware_payload(
                "turbo_pump", turbo_measurements
            )
        if room_parts:
            payloads["room_environment"] = "|".join(room_parts) + "\n"
        ups_payload = self._ups_payload()
        if ups_payload is not None:
            payloads["ups_monitor"] = ups_payload
        return payloads


@dataclass
class SerialEndpoint:
    """One pseudo-terminal pair and its stable public link."""

    master_fd: int
    slave_fd: int
    link_path: Path

    @classmethod
    def create(cls, sim_dir: Path, name: str) -> SerialEndpoint:
        """Create a raw pseudo-terminal and stable link for one device."""

        try:
            import pty
            import tty
        except ImportError as error:
            raise RuntimeError("Pseudo-serial simulation requires Linux") from error

        master_fd, slave_fd = pty.openpty()
        try:
            tty.setraw(slave_fd)
            os.set_blocking(master_fd, False)
            link_path = sim_dir / name
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
            link_path.symlink_to(os.ttyname(slave_fd))
        except Exception:
            os.close(master_fd)
            os.close(slave_fd)
            raise
        return cls(master_fd=master_fd, slave_fd=slave_fd, link_path=link_path)

    def write(self, payload: str) -> None:
        """Write a payload without blocking when no reader is keeping up."""

        try:
            os.write(self.master_fd, payload.encode("utf-8"))
        except BlockingIOError:
            pass

    def close(self) -> None:
        """Close the pseudo-terminal and remove its stable link."""

        try:
            os.close(self.master_fd)
        finally:
            try:
                os.close(self.slave_fd)
            finally:
                if self.link_path.is_symlink():
                    self.link_path.unlink()


class SimulatorService:
    """Own pseudo-serial endpoints and accept live control commands."""

    def __init__(
        self,
        sim_dir: Path,
        interval: float,
        scenarios: dict[str, str] | None = None,
    ) -> None:
        """Configure the foreground simulator service."""

        if interval <= 0:
            raise ValueError("Interval must be greater than zero")
        self.sim_dir = sim_dir
        self.interval = interval
        self.socket_path = sim_dir / CONTROL_SOCKET_NAME
        self.generator = MeasurementGenerator(scenarios)
        self.endpoints: dict[str, SerialEndpoint] = {}
        self.server: socket.socket | None = None
        self.running = True

    def _dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        """Apply one control request and return a JSON-compatible response."""

        command = request.get("command")
        if command == "set":
            target = str(request.get("target", ""))
            state = str(request.get("state", ""))
            self.generator.set_scenario(target, state)
            return {"ok": True, "message": f"Set {target} to {state}"}
        if command == "clear":
            target = str(request.get("target", ""))
            self.generator.clear_scenario(target)
            return {"ok": True, "message": f"Cleared {target}"}
        if command == "disconnect":
            name = normalize_device_name(str(request.get("device", "")))
            endpoint = self.endpoints.pop(name, None)
            if endpoint is None:
                raise ValueError(f"Simulator device is already disconnected: {name}")
            endpoint.close()
            return {"ok": True, "message": f"Disconnected simulator device {name}"}
        if command == "connect":
            name = normalize_device_name(str(request.get("device", "")))
            if name in self.endpoints:
                raise ValueError(f"Simulator device is already connected: {name}")
            self.endpoints[name] = SerialEndpoint.create(self.sim_dir, name)
            return {"ok": True, "message": f"Connected simulator device {name}"}
        if command == "reset":
            self.generator.reset()
            return {"ok": True, "message": "Cleared all scenarios"}
        if command == "status":
            return {
                "ok": True,
                "scenarios": dict(sorted(self.generator.scenarios.items())),
                "devices": {
                    name: str(endpoint.link_path)
                    for name, endpoint in self.endpoints.items()
                },
                "disconnected_devices": sorted(set(DEVICE_NAMES) - set(self.endpoints)),
            }
        if command == "stop":
            self.running = False
            return {"ok": True, "message": "Simulator stopping"}
        raise ValueError(f"Unsupported control command: {command}")

    def _handle_connection(self, connection: socket.socket) -> None:
        """Read, dispatch, and answer one socket request."""

        with connection:
            try:
                request = receive_message(connection)
                response = self._dispatch(request)
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                response = {"ok": False, "error": str(error)}
            connection.sendall(json.dumps(response).encode("utf-8") + b"\n")

    def _emit(self) -> None:
        """Write one payload to each pseudo-serial endpoint."""

        for name, payload in self.generator.payloads().items():
            endpoint = self.endpoints.get(name)
            if endpoint is not None:
                endpoint.write(payload)

    def serve(self) -> None:
        """Run until a stop command or termination signal is received."""

        if not hasattr(socket, "AF_UNIX"):
            raise RuntimeError("The pseudo-serial service requires Linux Unix sockets")

        self.sim_dir.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists() or self.socket_path.is_symlink():
            try:
                send_request(self.sim_dir, {"command": "status"})
            except OSError:
                self.socket_path.unlink()
            else:
                raise RuntimeError("The simulator is already running")

        try:
            for name in DEVICE_NAMES:
                self.endpoints[name] = SerialEndpoint.create(self.sim_dir, name)
            self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server.bind(str(self.socket_path))
            self.socket_path.chmod(0o600)
            self.server.listen()
            self.server.settimeout(0.1)

            signal.signal(signal.SIGTERM, lambda *_: setattr(self, "running", False))
            signal.signal(signal.SIGINT, lambda *_: setattr(self, "running", False))

            next_emission = time.monotonic()
            while self.running:
                now = time.monotonic()
                if now >= next_emission:
                    self._emit()
                    next_emission = now + self.interval
                try:
                    connection, _ = self.server.accept()
                except TimeoutError:
                    continue
                self._handle_connection(connection)
        finally:
            if self.server is not None:
                self.server.close()
            if self.socket_path.exists() or self.socket_path.is_symlink():
                self.socket_path.unlink()
            for endpoint in self.endpoints.values():
                endpoint.close()


def send_request(sim_dir: Path, request: dict[str, Any]) -> dict[str, Any]:
    """Send one command to the running simulator service."""

    socket_path = sim_dir / CONTROL_SOCKET_NAME
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(2)
    try:
        client.connect(str(socket_path))
        client.sendall(json.dumps(request).encode("utf-8") + b"\n")
        response = receive_message(client)
    finally:
        client.close()
    if not response.get("ok"):
        raise RuntimeError(str(response.get("error", "Simulator command failed")))
    return response


def start_service(sim_dir: Path, interval: float, assignments: list[str]) -> None:
    """Launch the simulator in a detached background process."""

    if os.name != "posix":
        raise RuntimeError("The pseudo-serial simulator can only run on Linux")
    try:
        send_request(sim_dir, {"command": "status"})
    except OSError:
        pass
    else:
        raise RuntimeError("The simulator is already running")

    sim_dir.mkdir(parents=True, exist_ok=True)
    socket_path = sim_dir / CONTROL_SOCKET_NAME
    if socket_path.exists() or socket_path.is_symlink():
        socket_path.unlink()

    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "serve",
        "--dir",
        str(sim_dir),
        "--interval",
        str(interval),
    ]
    for assignment in assignments:
        parse_scenario_assignment(assignment)
        command.extend(("--scenario", assignment))

    log_path = sim_dir / "simulator.log"
    with log_path.open("ab") as log_file:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Simulator failed to start; see {log_path}")
        try:
            send_request(sim_dir, {"command": "status"})
        except OSError:
            time.sleep(0.05)
            continue
        print(f"Simulator started in the background. Control socket: {socket_path}")
        return
    process.terminate()
    raise RuntimeError(f"Timed out starting simulator; see {log_path}")


def print_status(response: dict[str, Any]) -> None:
    """Print service status in a concise operator-friendly form."""

    print("Simulator is running.")
    print("Devices:")
    for name, path in response["devices"].items():
        print(f"  {name}: {path}")
    disconnected = response.get("disconnected_devices", [])
    if disconnected:
        print("Disconnected devices:")
        for name in disconnected:
            print(f"  {name}")
    print("Scenarios:")
    scenarios = response["scenarios"]
    if not scenarios:
        print("  all measurements: random healthy values")
    else:
        for target, state in scenarios.items():
            print(f"  {target}: {state}")


def add_directory_argument(parser: argparse.ArgumentParser) -> None:
    """Add the shared simulator-directory option to a subcommand."""

    parser.add_argument("--dir", type=Path, default=DEFAULT_SIM_DIR)


def build_parser() -> argparse.ArgumentParser:
    """Build the simulator command-line parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="start the background service")
    add_directory_argument(start)
    start.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    start.add_argument("--scenario", action="append", default=[])

    serve = subparsers.add_parser("serve", help="run in the foreground")
    add_directory_argument(serve)
    serve.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    serve.add_argument("--scenario", action="append", default=[])

    set_command = subparsers.add_parser("set", help="change one measurement scenario")
    add_directory_argument(set_command)
    set_command.add_argument("target")
    set_command.add_argument("state")

    clear = subparsers.add_parser("clear", help="clear one measurement scenario")
    add_directory_argument(clear)
    clear.add_argument("target")

    for command, help_text in (
        ("disconnect", "simulate unplugging one device"),
        ("connect", "simulate replugging one device"),
    ):
        command_parser = subparsers.add_parser(command, help=help_text)
        add_directory_argument(command_parser)
        command_parser.add_argument("device", choices=tuple(DEVICE_ALIASES))

    for command, help_text in (
        ("reset", "clear every scenario"),
        ("status", "show devices and active scenarios"),
        ("stop", "stop the background service"),
    ):
        command_parser = subparsers.add_parser(command, help=help_text)
        add_directory_argument(command_parser)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one simulator service or control command."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            start_service(args.dir, args.interval, args.scenario)
            return 0
        if args.command == "serve":
            scenarios = dict(parse_scenario_assignment(item) for item in args.scenario)
            SimulatorService(args.dir, args.interval, scenarios).serve()
            return 0

        request: dict[str, Any] = {"command": args.command}
        if args.command == "set":
            validate_scenario(args.target, args.state)
            request.update(target=args.target, state=args.state)
        elif args.command == "clear":
            if args.target not in SCENARIO_TARGETS:
                raise ValueError(f"Unsupported scenario target: {args.target}")
            request["target"] = args.target
        elif args.command in {"disconnect", "connect"}:
            request["device"] = normalize_device_name(args.device)

        response = send_request(args.dir, request)
        if args.command == "status":
            print_status(response)
        else:
            print(response["message"])
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
