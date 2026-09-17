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


def measurement_references(path: Path) -> list[str]:
    """Return header-owned name fields passed to the writer in source order."""

    text = path.read_text(encoding="utf-8")
    return re.findall(
        r"sample\.value\(\s*"
        r"([A-Z][A-Z0-9_]*(?:\[\d+\])?\."
        r"(?:name|temperatureName|humidityName))\s*,",
        text,
    )


def test_reusable_sensor_modules() -> None:
    """Require one reusable header and implementation per sensor concern."""

    source_dir = FIRMWARE_DIR / "src"
    for stem in (
        "Dht11Sensor",
        "PipeSampleWriter",
        "PulseFlowSensor",
        "ThermistorSensor",
        "LinearPressureSensor",
        "Sht40Sensor",
    ):
        if not (source_dir / f"{stem}.h").is_file():
            raise AssertionError(f"Missing reusable header: {stem}.h")
        if not (source_dir / f"{stem}.cpp").is_file():
            raise AssertionError(f"Missing reusable implementation: {stem}.cpp")
    if not (source_dir / "PinMeasurement.h").is_file():
        raise AssertionError("Missing reusable header: PinMeasurement.h")
    assert_contains(
        FIRMWARE_DIR / "README.md",
        (
            "450 pulses per litre",
            "0.0014948",
            "0.00021902",
            "0.0000016239",
            "0.000000034445",
            "0.48 to 4.5 V",
            "0.5 to 4.5 V",
            "Numeric zero and invalid are different",
        ),
    )
    assert_contains(
        source_dir / "Sht40Sensor.cpp",
        (
            "sensor_.begin()",
            "SHT4X_HIGH_PRECISION",
            "SHT4X_NO_HEATER",
            "sensor_.getEvent(&humidityEvent, &temperatureEvent)",
            "initialized_ = false",
        ),
    )


def test_arduino_library_metadata() -> None:
    """Require metadata needed for discovery by Arduino IDE 1.8.19."""

    assert_contains(
        FIRMWARE_DIR / "library.properties",
        (
            "name=LabPulseFirmware",
            "version=0.1.0",
            "url=https://github.com/lairdgrouplancaster/LabPulse",
            "architectures=*",
            "depends=DHT sensor library",
            "Adafruit SHT4x Library",
        ),
    )


def test_device_composition_files() -> None:
    """Require every device to have a config header, composition source, and wrapper."""

    for target in ("pressure_monitor", "pump_room", "turbo_pump"):
        target_dir = FIRMWARE_DIR / "examples" / target
        for suffix in (".h", ".cpp", ".ino"):
            path = target_dir / f"{target}{suffix}"
            if not path.is_file():
                raise AssertionError(f"Missing device firmware file: {path}")


def test_pipe_measurement_order() -> None:
    """Require output names to come from header mappings in the current order."""

    expected = {
        "pressure_monitor": [
            "PRESSURE.name",
            "ENVIRONMENT.temperatureName",
            "ENVIRONMENT.humidityName",
        ],
        "pump_room": [
            "FLOW1.name",
            "FLOW2.name",
            "TEMPERATURES[0].name",
            "TEMPERATURES[1].name",
            "TEMPERATURES[2].name",
            "TEMPERATURES[3].name",
            "ROOM_DHT11.temperatureName",
            "ROOM_DHT11.humidityName",
            "PRESSURES[0].name",
            "PRESSURES[1].name",
        ],
        "turbo_pump": [
            "FLOW1.name",
            "FLOW2.name",
            "TEMPERATURES[0].name",
            "TEMPERATURES[1].name",
            "TEMPERATURES[2].name",
            "TEMPERATURES[3].name",
        ],
    }
    for target, names in expected.items():
        actual = measurement_references(
            FIRMWARE_DIR / "examples" / target / f"{target}.cpp"
        )
        if actual != names:
            raise AssertionError(
                f"{target} uses name fields {actual}, expected {names}"
            )
