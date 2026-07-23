"""Contract tests for the read-only LabPulse installation doctor."""

from contextlib import contextmanager
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from typing import Iterator
from uuid import uuid4


REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))

from labpulse.doctor import CheckStatus, diagnose


VALID_CONFIG = """\
mqtt:
  broker: mosquitto
  port: 1883
sms:
  dry_run: true
setups: {}
services: {}
"""

COMPOSE = """\
services:
  homeassistant:
    volumes:
      - ./homeassistant/config:/config
  mosquitto:
    ports:
      - "127.0.0.1:1883:1883"
  labpulse-sms:
    volumes:
      - ./config.fake.yaml:/app/config.yaml:ro
"""


@contextmanager
def live_install() -> Iterator[Path]:
    """Create a disposable, structurally complete live installation."""

    temporary_root = REPOSITORY / "testing" / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    path = temporary_root / f"doctor-{uuid4().hex}"
    generated = path / "homeassistant" / "config"
    (generated / "packages").mkdir(parents=True)
    (path / "config.yaml").write_text(VALID_CONFIG, encoding="utf-8")
    (path / "config.fake.yaml").write_text(VALID_CONFIG, encoding="utf-8")
    (path / "compose.yaml").write_text(COMPOSE, encoding="utf-8")
    (generated / "configuration.yaml").write_text(
        "homeassistant:\n  packages: !include_dir_named packages\n",
        encoding="utf-8",
    )
    (generated / "packages" / "labpulse_generated.yaml").write_text(
        "{}\n",
        encoding="utf-8",
    )
    (generated / "labpulse-dashboard.yaml").write_text(
        "views: []\n",
        encoding="utf-8",
    )
    try:
        yield path.resolve()
    finally:
        shutil.rmtree(path)


def healthy_runner(
    command: list[str],
    **_kwargs: object,
) -> subprocess.CompletedProcess[str]:
    """Emulate successful Docker Compose inspection."""

    stdout = ""
    if command[-4:] == ["ps", "--status", "running", "--services"]:
        stdout = "homeassistant\nmosquitto\nlabpulse-sms\n"
    return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")


class Connection:
    """Minimal closable socket stand-in."""

    def close(self) -> None:
        """Match the socket API used by the doctor."""


def healthy_connector(
    _address: tuple[str, int],
    *,
    timeout: float,
) -> Connection:
    """Emulate a reachable local endpoint."""

    if timeout <= 0:
        raise AssertionError("doctor passed an invalid timeout")
    return Connection()


def main() -> None:
    """Verify success, failure, runtime-config detection, and read-only behavior."""

    with live_install() as live_dir:
        before = {
            path.relative_to(live_dir): path.read_bytes()
            for path in live_dir.rglob("*")
            if path.is_file()
        }
        report = diagnose(
            live_dir,
            docker_prefix=["docker"],
            command_runner=healthy_runner,
            connector=healthy_connector,
        )
        if report.exit_code != 0:
            raise AssertionError(report.render())
        if not any(
            check.name == "Runtime configuration"
            and check.status is CheckStatus.PASS
            and "config.fake.yaml" in check.detail
            for check in report.checks
        ):
            raise AssertionError("doctor did not detect the Compose runtime config")
        after = {
            path.relative_to(live_dir): path.read_bytes()
            for path in live_dir.rglob("*")
            if path.is_file()
        }
        if after != before:
            raise AssertionError("doctor modified the live installation")

        (live_dir / "homeassistant" / "config" / "labpulse-dashboard.yaml").unlink()

        def stopped_runner(
            command: list[str],
            **_kwargs: object,
        ) -> subprocess.CompletedProcess[str]:
            stdout = ""
            if command[-4:] == ["ps", "--status", "running", "--services"]:
                stdout = "mosquitto\n"
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

        def refused_connector(
            address: tuple[str, int],
            *,
            timeout: float,
        ) -> Connection:
            raise ConnectionRefusedError(f"refused {address} after {timeout}s")

        failed = diagnose(
            live_dir,
            docker_prefix=["docker"],
            command_runner=stopped_runner,
            connector=refused_connector,
        )
        failed_names = {
            check.name
            for check in failed.checks
            if check.status is CheckStatus.FAIL
        }
        expected_failures = {
            "Generated Home Assistant files",
            "Containers",
            "MQTT",
            "Home Assistant",
        }
        if failed.exit_code != 1 or not expected_failures.issubset(failed_names):
            raise AssertionError(failed.render())

    missing = REPOSITORY / "testing" / "definitely-not-a-doctor-install"
    missing_report = diagnose(
        missing,
        docker_prefix=["docker"],
        command_runner=healthy_runner,
        connector=healthy_connector,
    )
    if missing_report.exit_code != 1 or len(missing_report.checks) != 1:
        raise AssertionError(missing_report.render())

    print("[PASS] healthy installation diagnostics")
    print("[PASS] fake runtime configuration detection")
    print("[PASS] read-only diagnostic behavior")
    print("[PASS] actionable service and endpoint failures")
    print("[PASS] missing installation handling")


if __name__ == "__main__":
    main()
