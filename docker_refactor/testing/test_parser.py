from pathlib import Path
import sys


REFACTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REFACTOR_DIR))

from labpulse_common.parser import SerialParser


TEST_CASES = [
    {
        "name": "pressure raw MPa converts to bar",
        "service_name": "pressure_monitor",
        "parser_type": "pressure",
        "line": "0.1034",
        "expected": {"pressure_monitor_pressure": 1.03},
    },
    {
        "name": "pump room flow line",
        "service_name": "pump_room",
        "parser_type": "pump_room",
        "line": "Flow1: 2.45 L/min | Flow2: 3.10 L/min",
        "expected": {"pump_room_flow1": 2.45, "pump_room_flow2": 3.1},
    },
    {
        "name": "pump room temperature line",
        "service_name": "pump_room",
        "parser_type": "pump_room",
        "line": "Temp0: 20.11C  Temp1: 20.22C  Temp2: 20.33C  Temp3: 20.44C  ",
        "expected": {
            "pump_room_temp0": 20.11,
            "pump_room_temp1": 20.22,
            "pump_room_temp2": 20.33,
            "pump_room_temp3": 20.44,
        },
    },
    {
        "name": "pump room room and pressure line",
        "service_name": "pump_room",
        "parser_type": "pump_room",
        "line": "RoomTemp: 21.2C | RoomHum: 45.0% | Press1: 1.23 bar | Press2: 1.45 bar",
        "expected": {
            "pump_room_roomtemp": 21.2,
            "pump_room_roomhum": 45.0,
            "pump_room_press1": 1.23,
            "pump_room_press2": 1.45,
        },
    },
    {
        "name": "full water combined flow and temperature line",
        "service_name": "turbo_pump",
        "parser_type": "water",
        "line": "Flow1: 2.45 L/min | Flow2: 3.10 L/minTemp0: 20.11C  Temp1: 20.22C  Temp2: 20.33C  Temp3: 20.44C  ",
        "expected": {
            "turbo_pump_flow1": 2.45,
            "turbo_pump_flow2": 3.1,
            "turbo_pump_temp0": 20.11,
            "turbo_pump_temp1": 20.22,
            "turbo_pump_temp2": 20.33,
            "turbo_pump_temp3": 20.44,
        },
    },
    {
        "name": "temporary flow reader line",
        "service_name": "flow_test",
        "parser_type": "water",
        "line": "FlowRate:1.234,TotalLitres:0.567",
        "expected": {
            "flow_test_flowrate": 1.234,
            "flow_test_totallitres": 0.567,
        },
    },
]


def run_test(test_case):
    parser = SerialParser(test_case["service_name"], test_case["parser_type"])
    actual = parser.parse(test_case["line"])
    expected = test_case["expected"]
    passed = actual == expected

    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {test_case['name']}")
    print(f"  parser:   {test_case['parser_type']}")
    print(f"  service:  {test_case['service_name']}")
    print(f"  input:    {test_case['line']}")
    print(f"  expected: {expected}")
    print(f"  actual:   {actual}")
    print()

    return passed


def main():
    print("Running SerialParser tests")
    print(f"Refactor dir: {REFACTOR_DIR}")
    print()

    passed_count = 0

    for test_case in TEST_CASES:
        if run_test(test_case):
            passed_count += 1

    total = len(TEST_CASES)
    failed_count = total - passed_count

    print(f"Summary: {passed_count}/{total} passed, {failed_count} failed")

    if failed_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
