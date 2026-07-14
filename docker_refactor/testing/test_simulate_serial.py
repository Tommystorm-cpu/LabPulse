"""Behavior and contract tests for the pseudo-serial simulator service."""

from pathlib import Path
import sys
from typing import Callable


REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.config import load_config
from labpulse_hardware.legacy_parsing.serial_parser import SerialParser
from simulate_serial import ReadingGenerator, SimulatorService, build_parser


def test_generated_payloads_match_parsers() -> None:
    """Check every generated device format remains consumable by LabPulse."""

    payloads = ReadingGenerator(seed=4).payloads()

    pressure = SerialParser("pressure_monitor", "pressure").parse(
        payloads["pressure"].strip()
    )
    pump_lines = payloads["pump_room"].splitlines()
    pump_flow = SerialParser("pump_room", "pump_room").parse(pump_lines[0])
    pump_temperature = SerialParser("pump_room", "pump_room").parse(pump_lines[1])
    pump_environment = SerialParser("pump_room", "pump_room").parse(pump_lines[2])
    turbo = SerialParser("turbo_pump", "water").parse(payloads["turbo_pump"].strip())
    room = SerialParser("room_environment", "pipe").parse(
        payloads["room_environment"].strip()
    )

    if pressure is None or "pressure" not in pressure:
        raise AssertionError(f"invalid pressure payload: {payloads['pressure']!r}")
    if pump_flow is None or set(pump_flow) != {"flow1", "flow2"}:
        raise AssertionError(f"invalid pump flow payload: {pump_lines[0]!r}")
    if pump_temperature is None or set(pump_temperature) != {
        "temp0",
        "temp1",
        "temp2",
        "temp3",
    }:
        raise AssertionError(f"invalid pump temperature payload: {pump_lines[1]!r}")
    if pump_environment is None or set(pump_environment) != {
        "roomtemp",
        "roomhum",
        "press1",
        "press2",
    }:
        raise AssertionError(f"invalid pump environment payload: {pump_lines[2]!r}")
    configured_pump_readings = {
        reading.name
        for reading in load_config(REFACTOR_DIR / "config.yaml").services[
            "pump_room"
        ].readings
    }
    parsed_pump_readings = set(pump_flow) | set(pump_temperature) | set(pump_environment)
    if configured_pump_readings != parsed_pump_readings:
        raise AssertionError(
            "pump-room starter config and simulated Arduino payload differ: "
            f"configured={configured_pump_readings!r}, parsed={parsed_pump_readings!r}"
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


def test_scenarios_change_generated_values() -> None:
    """Check live scenarios produce danger and stable stale values."""

    generator = ReadingGenerator(seed=8)
    generator.set_scenario("room_environment.humidity", "danger-high")
    generator.set_scenario("pressure_monitor.pressure", "danger-low")
    generator.set_scenario("room_environment.temperature", "stale")
    generator.set_scenario("pump_room.press1", "danger-low")
    generator.set_scenario("pump_room.roomhum", "danger-high")

    first = generator.payloads()
    second = generator.payloads()
    room_parser = SerialParser("room_environment", "pipe")
    first_room = room_parser.parse(first["room_environment"].strip())
    second_room = room_parser.parse(second["room_environment"].strip())
    pressure = SerialParser("pressure_monitor", "pressure").parse(
        first["pressure"].strip()
    )
    pump = SerialParser("pump_room", "pump_room").parse(
        first["pump_room"].splitlines()[2]
    )

    if first_room is None or second_room is None or pressure is None or pump is None:
        raise AssertionError("scenario payload failed to parse")
    if first_room["humidity"] < 90:
        raise AssertionError(f"humidity did not enter danger-high: {first_room!r}")
    if first_room["temperature"] != second_room["temperature"]:
        raise AssertionError("stale temperature changed between emissions")
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


def test_cli_and_transport_contract() -> None:
    """Check the intended background-service commands and socket transport."""

    parser = build_parser()
    parsed = parser.parse_args(
        ["set", "pump_room.flow1", "danger-low", "--dir", "/tmp/test-sim"]
    )
    if parsed.command != "set" or parsed.target != "pump_room.flow1":
        raise AssertionError(f"unexpected CLI parse: {parsed!r}")

    source = (REFACTOR_DIR / "simulate_serial.py").read_text(encoding="utf-8")
    for fragment in (
        'CONTROL_SOCKET_NAME = "control.sock"',
        "pty.openpty()",
        '"start"',
        '"serve"',
        '"set"',
        '"clear"',
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
    ("control commands keep state in memory", test_control_commands_keep_state_in_memory),
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
