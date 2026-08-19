"""Check the single supported pipe-delimited serial format."""

from typing import Optional

import pytest

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


@pytest.mark.parametrize(
    ("_description", "line", "expected"),
    TEST_CASES,
    ids=[case[0] for case in TEST_CASES],
)
def test_standard_serial_parser_cases(
    _description: str,
    line: str,
    expected: Optional[dict[str, float]],
) -> None:
    """Parse one named standard-protocol example."""

    assert SerialParser().parse(line) == expected
