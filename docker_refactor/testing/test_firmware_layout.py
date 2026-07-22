"""Check the modular Arduino firmware layout and current serial contracts."""

from pathlib import Path
import re


REFACTOR_DIR = Path(__file__).resolve().parents[1]
FIRMWARE_DIR = REFACTOR_DIR / "firmware"


def assert_contains(path: Path, values: tuple[str, ...]) -> None:
    """Require every text fragment to appear in one firmware source file."""

    text = path.read_text(encoding="utf-8")
    for value in values:
        if value not in text:
            raise AssertionError(f"Missing {value!r} in {path}")


def measurement_names(path: Path) -> list[str]:
    """Return pipe-writer measurement names in source order."""

    text = path.read_text(encoding="utf-8")
    return re.findall(r'sample\.value\(F\("([a-z0-9_]+)"\)', text)


def test_reusable_sensor_modules() -> None:
    """Require one reusable header and implementation per sensor concern."""

    source_dir = FIRMWARE_DIR / "src"
    for stem in (
        "Dht11Sensor",
        "PipeSampleWriter",
        "PulseFlowSensor",
        "ThermistorSensor",
        "LinearPressureSensor",
    ):
        if not (source_dir / f"{stem}.h").is_file():
            raise AssertionError(f"Missing reusable header: {stem}.h")
        if not (source_dir / f"{stem}.cpp").is_file():
            raise AssertionError(f"Missing reusable implementation: {stem}.cpp")


def test_device_composition_files() -> None:
    """Require every device to have a config header, composition source, and wrapper."""

    for target in ("pressure_monitor", "pump_room", "turbo_pump"):
        target_dir = FIRMWARE_DIR / "examples" / target
        for suffix in (".h", ".cpp", ".ino"):
            path = target_dir / f"{target}{suffix}"
            if not path.is_file():
                raise AssertionError(f"Missing device firmware file: {path}")


def test_current_configuration_is_retained() -> None:
    """Pin the deployed LabPulse pins, intervals, and calibration constants."""

    assert_contains(
        FIRMWARE_DIR / "examples" / "pressure_monitor" / "pressure_monitor.h",
        (
            "SAMPLE_INTERVAL_MS = 1000UL",
            "A0,",
            "0.48F",
            "4.5F",
            "1.6F",
            "10000.0F",
            "-0.25F",
            "16.5F",
        ),
    )
    assert_contains(
        FIRMWARE_DIR / "examples" / "pump_room" / "pump_room.h",
        (
            "SAMPLE_INTERVAL_MS = 5000UL",
            "3, 450.0F, INPUT_PULLUP, FALLING",
            "2, 450.0F, INPUT_PULLUP, FALLING",
            "A0, 5.0F, 1023",
            "A3, 5.0F, 1023",
            "DHT11_CONFIG",
            "4, DHT11, -40.0F, 80.0F, 0.0F, 100.0F",
            "A5, 5.0F, 1024",
            "A4, 5.0F, 1024",
        ),
    )
    assert_contains(
        FIRMWARE_DIR / "examples" / "turbo_pump" / "turbo_pump.h",
        (
            "SAMPLE_INTERVAL_MS = 5000UL",
            "2, 450.0F, INPUT_PULLUP, FALLING",
            "3, 450.0F, INPUT_PULLUP, FALLING",
            "A0, 5.0F, 1023",
            "A3, 5.0F, 1023",
        ),
    )


def test_pipe_measurement_order() -> None:
    """Keep emitted measurement names and order aligned with current config."""

    expected = {
        "pressure_monitor": ["pressure"],
        "pump_room": [
            "flow1",
            "flow2",
            "temp0",
            "temp1",
            "temp2",
            "temp3",
            "roomtemp",
            "roomhum",
            "press1",
            "press2",
        ],
        "turbo_pump": [
            "flow1",
            "flow2",
            "temp0",
            "temp1",
            "temp2",
            "temp3",
        ],
    }
    for target, names in expected.items():
        actual = measurement_names(
            FIRMWARE_DIR / "examples" / target / f"{target}.cpp"
        )
        if actual != names:
            raise AssertionError(f"{target} emits {actual}, expected {names}")


def run() -> None:
    """Run all firmware layout checks without external test dependencies."""

    tests = (
        test_reusable_sensor_modules,
        test_device_composition_files,
        test_current_configuration_is_retained,
        test_pipe_measurement_order,
    )
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
    print(f"Summary: {len(tests)}/{len(tests)} passed, 0 failed")


if __name__ == "__main__":
    run()
