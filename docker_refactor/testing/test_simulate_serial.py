"""Behavior and contract tests for the pseudo-serial simulator service."""

from pathlib import Path
import sys
from typing import Callable
from unittest.mock import patch


REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.config import load_config
from labpulse_hardware.serial_parser import SerialParser
from simulate_serial import MeasurementGenerator, SimulatorService, build_parser


def test_generated_payloads_match_parsers() -> None:
    """Check every generated device format remains consumable by LabPulse."""

    payloads = MeasurementGenerator(seed=4).payloads()

    pressure = SerialParser().parse(
        payloads["pressure"].strip()
    )
    pump = SerialParser().parse(
        payloads["pump_room"].strip()
    )
    turbo = SerialParser().parse(payloads["turbo_pump"].strip())
    room = SerialParser().parse(
        payloads["room_environment"].strip()
    )
    ups = SerialParser().parse(
        payloads["ups_monitor"].strip()
    )

    if pressure is None or "pressure" not in pressure:
        raise AssertionError(f"invalid pressure payload: {payloads['pressure']!r}")
    if pump is None:
        raise AssertionError(f"invalid pump payload: {payloads['pump_room']!r}")
    configured_pump_measurements = {
        measurement.name
        for measurement in load_config(REFACTOR_DIR / "config.yaml").services[
            "pump_room"
        ].measurements
    }
    parsed_pump_measurements = set(pump)
    if configured_pump_measurements != parsed_pump_measurements:
        raise AssertionError(
            "pump-room starter config and simulated Arduino payload differ: "
            f"configured={configured_pump_measurements!r}, parsed={parsed_pump_measurements!r}"
        )
    if turbo is None or set(turbo) != {
        "flow1",
        "flow2",
        "temp0",
        "temp1",
        "temp2",
        "temp3",
    }:
        raise AssertionError(f"invalid turbo payload: {payloads['turbo_pump']!r}")
    if room is None or set(room) != {"temperature", "humidity"}:
        raise AssertionError(f"invalid room payload: {payloads['room_environment']!r}")
    if ups is None or set(ups) != {"voltage", "battery_level", "mains_present"}:
        raise AssertionError(f"invalid UPS payload: {payloads['ups_monitor']!r}")


def test_ups_power_scenarios_and_stale_suppression() -> None:
    """Check UPS scenarios use real gauge fields and stale stops publication."""

    generator = MeasurementGenerator(seed=2)
    parser = SerialParser()
    expected_voltage = {"mains": 4.13, "battery": 3.95}
    for state, voltage in expected_voltage.items():
        generator.set_scenario("ups_monitor.power", state)
        parsed = parser.parse(generator.payloads()["ups_monitor"])
        if parsed is None:
            raise AssertionError(f"UPS {state} payload did not parse")
        expected_mains = 1.0 if state == "mains" else 0.0
        if (
            parsed["voltage"] != voltage
            or parsed["mains_present"] != expected_mains
            or set(parsed) != {"voltage", "battery_level", "mains_present"}
        ):
            raise AssertionError(f"UPS {state} payload is not truthful: {parsed!r}")

    generator.set_scenario("ups_monitor.power", "stale")
    if "ups_monitor" in generator.payloads():
        raise AssertionError("stale UPS simulation emitted fresh telemetry")
    generator.clear_scenario("ups_monitor.power")
    if "ups_monitor" not in generator.payloads():
        raise AssertionError("cleared UPS scenario did not resume telemetry")


def test_scenarios_change_generated_values() -> None:
    """Check danger scenarios emit values while stale stops one measurement."""

    generator = MeasurementGenerator(seed=8)
    generator.set_scenario("room_environment.humidity", "danger-high")
    generator.set_scenario("pressure_monitor.pressure", "danger-low")
    generator.set_scenario("room_environment.temperature", "stale")
    generator.set_scenario("pump_room.press1", "danger-low")
    generator.set_scenario("pump_room.roomhum", "danger-high")

    first = generator.payloads()
    room_parser = SerialParser()
    first_room = room_parser.parse(first["room_environment"].strip())
    pressure = SerialParser().parse(
        first["pressure"].strip()
    )
    pump = SerialParser().parse(first["pump_room"])

    if first_room is None or pressure is None or pump is None:
        raise AssertionError("scenario payload failed to parse")
    if first_room["humidity"] < 90:
        raise AssertionError(f"humidity did not enter danger-high: {first_room!r}")
    if "temperature" in first_room or "humidity" not in first_room:
        raise AssertionError("stale temperature was emitted or suppressed its healthy peer")
    if pressure["pressure"] >= 1:
        raise AssertionError(f"pressure did not enter danger-low: {pressure!r}")
    if pump["press1"] >= 1:
        raise AssertionError(f"pump pressure did not enter danger-low: {pump!r}")
    if pump["roomhum"] < 90:
        raise AssertionError(f"pump humidity did not enter danger-high: {pump!r}")


def test_control_commands_keep_state_in_memory() -> None:
    """Check set, clear, and reset mutate daemon memory without a state file."""

    service = SimulatorService(Path("/tmp/unused-labpulse-test"), interval=1)

    service._dispatch(
        {
            "command": "set",
            "target": "pump_room.flow1",
            "state": "danger-low",
        }
    )
    status = service._dispatch({"command": "status"})
    if status["scenarios"] != {"pump_room.flow1": "danger-low"}:
        raise AssertionError(f"unexpected scenario state: {status!r}")

    service._dispatch({"command": "clear", "target": "pump_room.flow1"})
    if service.generator.scenarios:
        raise AssertionError("clear left scenario state behind")

    service.generator.set_scenario("turbo_pump.temp0", "danger-high")
    service._dispatch({"command": "reset"})
    if service.generator.scenarios:
        raise AssertionError("reset left scenario state behind")


def test_device_disconnect_control() -> None:
    """Check one fake endpoint can disappear without stopping the simulator."""

    class FakeEndpoint:
        """Record endpoint closure without requiring a Linux pseudo-terminal."""

        def __init__(self) -> None:
            self.closed = False
            self.link_path = Path("/tmp/labpulse-fake-serial/pressure")

        def close(self) -> None:
            """Record that simulator disconnect closed the endpoint."""

            self.closed = True

    service = SimulatorService(Path("/tmp/unused-labpulse-test"), interval=1)
    endpoint = FakeEndpoint()
    service.endpoints["pressure"] = endpoint  # type: ignore[assignment]
    response = service._dispatch({"command": "disconnect", "device": "pressure_monitor"})
    if not endpoint.closed or "pressure" in service.endpoints:
        raise AssertionError("disconnect did not close and remove the endpoint")
    if "Disconnected simulator device pressure" not in response["message"]:
        raise AssertionError(f"unclear disconnect response: {response!r}")
    status = service._dispatch({"command": "status"})
    if "pressure" not in status["disconnected_devices"]:
        raise AssertionError(f"status omitted disconnected endpoint: {status!r}")
    replacement = FakeEndpoint()
    with patch("simulate_serial.SerialEndpoint.create", return_value=replacement) as create:
        response = service._dispatch({"command": "connect", "device": "pressure"})
    create.assert_called_once_with(service.sim_dir, "pressure")
    if service.endpoints.get("pressure") is not replacement:
        raise AssertionError("connect did not install the replacement endpoint")
    if "Connected simulator device pressure" not in response["message"]:
        raise AssertionError(f"unclear connect response: {response!r}")


def test_cli_and_transport_contract() -> None:
    """Check the intended background-service commands and socket transport."""

    parser = build_parser()
    parsed = parser.parse_args(
        ["set", "pump_room.flow1", "danger-low", "--dir", "/tmp/test-sim"]
    )
    if parsed.command != "set" or parsed.target != "pump_room.flow1":
        raise AssertionError(f"unexpected CLI parse: {parsed!r}")
    ups = parser.parse_args(["set", "ups_monitor.power", "battery"])
    if ups.state != "battery":
        raise AssertionError(f"unexpected UPS CLI parse: {ups!r}")
    disconnect = parser.parse_args(["disconnect", "pressure_monitor"])
    if disconnect.command != "disconnect" or disconnect.device != "pressure_monitor":
        raise AssertionError(f"unexpected disconnect CLI parse: {disconnect!r}")
    connect = parser.parse_args(["connect", "pump_room"])
    if connect.command != "connect" or connect.device != "pump_room":
        raise AssertionError(f"unexpected connect CLI parse: {connect!r}")

    source = (REFACTOR_DIR / "simulate_serial.py").read_text(encoding="utf-8")
    for fragment in (
        'CONTROL_SOCKET_NAME = "control.sock"',
        "pty.openpty()",
        '"start"',
        '"serve"',
        '"set"',
        '"clear"',
        '"disconnect"',
        '"connect"',
        '"reset"',
        '"status"',
        '"stop"',
    ):
        if fragment not in source:
            raise AssertionError(f"missing simulator contract: {fragment}")
    if "scenarios.txt" in source or "socat" in source or "_writer" in source:
        raise AssertionError("old file/socat control mechanism remains")


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("generated payloads match parsers", test_generated_payloads_match_parsers),
    ("scenarios change generated values", test_scenarios_change_generated_values),
    ("UPS power scenarios and stale suppression", test_ups_power_scenarios_and_stale_suppression),
    ("control commands keep state in memory", test_control_commands_keep_state_in_memory),
    ("device disconnect control", test_device_disconnect_control),
    ("CLI and transport contract", test_cli_and_transport_contract),
]


def main() -> None:
    """Run simulator tests without requiring Linux pseudo-terminals."""

    print("Running pseudo-serial simulator tests")
    print(f"Refactor dir: {REFACTOR_DIR}")
    print()

    passed = 0
    for name, test_func in TESTS:
        try:
            test_func()
        except Exception as error:
            print(f"[FAIL] {name}")
            print(f"  error: {type(error).__name__}: {error}")
            print()
            continue
        print(f"[PASS] {name}")
        print()
        passed += 1

    failed = len(TESTS) - passed
    print(f"Summary: {passed}/{len(TESTS)} passed, {failed} failed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
