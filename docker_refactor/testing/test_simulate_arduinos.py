"""Static contract checks for the fake Arduino simulator script."""

from pathlib import Path
import sys
from typing import Callable


REFACTOR_DIR = Path(__file__).resolve().parents[1]
SIMULATOR = REFACTOR_DIR / "simulate_arduinos.sh"


def script_source() -> str:
    """Return the simulator shell source."""

    return SIMULATOR.read_text(encoding="utf-8")


def test_scenario_cli_contract() -> None:
    """Verify the simulator exposes documented alarm test scenarios."""

    source = script_source()
    required_fragments = (
        "[--scenario SERVICE.READING=STATE] [--scenario-file PATH]",
        "--scenario pressure_monitor.pressure=danger-low",
        "--scenario pump_room.flow1=danger-low",
        "--scenario pump_room.temp0=danger-high",
        "--scenario pump_room.flow1=stale",
        "LABPULSE_FAKE_SERIAL_SCENARIO_FILE",
        "normal|recover|danger-low|danger-high|stale",
        "validate_scenarios",
        "Initial alarm test scenarios:",
        "Live scenario control file:",
    )
    for fragment in required_fragments:
        if fragment not in source:
            raise AssertionError(f"missing scenario CLI fragment: {fragment}")


def test_scenario_value_contract() -> None:
    """Check that scenarios emit changing alarm values and fixed stale values."""

    source = script_source()
    required_fragments = (
        'random_hundredths "$normal" "$((normal + 25))"',
        'random_hundredths 5 "$low"',
        'random_hundredths "$high" "$((high + 1000))"',
        'random_tenths "$((normal - 5))" "$((normal + 5))"',
        'random_tenths "$high" "$((high + 10))"',
        "printf '0.1200\\n'",
        "value=$((500 + RANDOM % 91))",
        "printf '%d.%04d\\n'",
        '$(flow_value "pump_room" "flow1")',
        '$(temperature_value "pump_room" "temp0")',
        '$(turbo_flow_value "flow2")',
        '$(turbo_temperature_value "temp3")',
        'while IFS= read -r scenario || [ -n "$scenario" ]; do',
        'prepare_scenario_file',
        'printf \'%s\\n\' "${SCENARIOS[@]}" > "$SCENARIO_FILE"',
    )
    for fragment in required_fragments:
        if fragment not in source:
            raise AssertionError(f"missing scenario value fragment: {fragment}")


TESTS: list[tuple[str, Callable[[], None]]] = [
    ("scenario CLI contract", test_scenario_cli_contract),
    ("scenario value contract", test_scenario_value_contract),
]


def main() -> None:
    """Run simulator contract tests."""

    print("Running fake Arduino simulator tests")
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
