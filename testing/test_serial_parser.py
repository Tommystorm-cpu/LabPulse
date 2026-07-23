"""Check the single supported pipe-delimited serial format."""

from pathlib import Path
import sys
from typing import Optional


REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR / "src"))

from labpulse.hardware.serial_parser import SerialParser


TEST_CASES: tuple[tuple[str, str, Optional[dict[str, float]]], ...] = (
    (
        "pressure sample",
        "pressure: 1.03",
        {"pressure": 1.03},
    ),
    (
        "complete pump sample skips null",
        "flow1: 0.27 | flow2: 0.00 | temp0: 25.10 | temp1: null | "
        "roomtemp: 21.2 | roomhum: 45.0 | press1: 1.23 | press2: 1.45",
        {
            "flow1": 0.27,
            "flow2": 0.0,
            "temp0": 25.1,
            "roomtemp": 21.2,
            "roomhum": 45.0,
            "press1": 1.23,
            "press2": 1.45,
        },
    ),
    (
        "compact pipe sample",
        "temperature:21.5|humidity:48.0",
        {"temperature": 21.5, "humidity": 48.0},
    ),
    (
        "UPS simulator uses the same format",
        "voltage: 4.130 | battery_level: 94.2 | mains_present: 1",
        {"voltage": 4.13, "battery_level": 94.2, "mains_present": 1.0},
    ),
    (
        "unit-bearing legacy values are rejected",
        "flow1: 2.45 L/min | temp0: 20.11C",
        None,
    ),
    (
        "legacy unlabelled pressure is rejected",
        "0.1034",
        None,
    ),
    (
        "non-finite values are rejected",
        "first: nan | second: inf",
        None,
    ),
)


def main() -> None:
    """Run every standard serial parser case."""

    parser = SerialParser()
    failures = 0
    for name, line, expected in TEST_CASES:
        actual = parser.parse(line)
        if actual != expected:
            failures += 1
            print(f"[FAIL] {name}: expected {expected!r}, got {actual!r}")
        else:
            print(f"[PASS] {name}")

    print(
        f"Summary: {len(TEST_CASES) - failures}/{len(TEST_CASES)} passed, "
        f"{failures} failed"
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
