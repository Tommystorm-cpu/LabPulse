"""Shared Raspberry Pi GPIO input reading through the libgpiod command line."""

from __future__ import annotations

from pathlib import Path
import subprocess


def read_gpio(chip: str, line: int, active_high: bool) -> float:
    """Read one GPIO line as 0.0 or 1.0 using either libgpiod CLI version."""

    chip_name = Path(chip).name
    result = subprocess.run(
        ["gpioget", "-c", chip_name, str(line)],
        capture_output=True,
        text=True,
        check=False,
        timeout=2,
    )
    if result.returncode != 0:
        result_legacy = subprocess.run(
            ["gpioget", chip_name, str(line)],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
        if result_legacy.returncode != 0:
            modern_detail = result.stderr.strip() or f"gpioget exited {result.returncode}"
            legacy_detail = result_legacy.stderr.strip() or f"gpioget exited {result_legacy.returncode}"
            raise OSError(
                "libgpiod 2.x read failed: "
                f"{modern_detail}; libgpiod 1.x read failed: {legacy_detail}"
            )
        result = result_legacy

    raw = result.stdout.strip()
    value = raw.rsplit("=", 1)[-1].strip().lower()
    if value not in {"0", "1", "active", "inactive"}:
        raise ValueError(f"unexpected gpioget output: {raw!r}")

    asserted = value in {"1", "active"}
    logical_state = asserted if active_high else not asserted
    return 1.0 if logical_state else 0.0
