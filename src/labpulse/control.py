"""Operator commands for the installed LabPulse Docker deployment."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from typing import Sequence
import webbrowser

from labpulse.installer import find_install_assets, main as installer_main


DEFAULT_LIVE_DIR = Path("~/labpulse-live")
HOME_ASSISTANT_URL = "http://localhost:8123"


def live_directory(override: str | None = None) -> Path:
    """Return the configured live deployment directory."""

    configured = override or os.environ.get("LABPULSE_LIVE_DIR")
    return Path(configured or DEFAULT_LIVE_DIR).expanduser().resolve()


def docker_command() -> list[str]:
    """Return the Docker command prefix used for operator actions.

    ``sudo docker`` matches the Raspberry Pi installation documentation. Root
    users run Docker directly. Advanced installations can set
    ``LABPULSE_DOCKER_COMMAND`` (for example, to ``docker`` when their account
    belongs to the Docker group).
    """

    configured = os.environ.get("LABPULSE_DOCKER_COMMAND")
    if configured:
        command = shlex.split(configured)
        if not command:
            raise ValueError("LABPULSE_DOCKER_COMMAND cannot be empty")
        return command

    get_effective_user = getattr(os, "geteuid", None)
    if get_effective_user is not None and get_effective_user() == 0:
        return ["docker"]
    if shutil.which("sudo"):
        return ["sudo", "docker"]
    return ["docker"]


def run_compose(live_dir: Path, arguments: Sequence[str]) -> int:
    """Run one Docker Compose operation from the live deployment directory."""

    compose_path = live_dir / "compose.yaml"
    if not compose_path.is_file():
        print(
            f"ERROR: LabPulse is not set up at {live_dir} "
            f"(missing {compose_path.name}). Run 'labpulse setup' first.",
            file=sys.stderr,
        )
        return 2

    try:
        command = [*docker_command(), "compose", *arguments]
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    try:
        return subprocess.run(command, cwd=live_dir, check=False).returncode
    except FileNotFoundError as error:
        print(
            f"ERROR: Cannot run {error.filename!r}. "
            "Install Docker or correct LABPULSE_DOCKER_COMMAND.",
            file=sys.stderr,
        )
        return 127


def run_editor(live_dir: Path) -> int:
    """Run the packaged guarded config editor against the live deployment."""

    if not (live_dir / "config.yaml").is_file():
        print(
            f"ERROR: LabPulse is not set up at {live_dir} "
            "(missing config.yaml). Run 'labpulse setup' first.",
            file=sys.stderr,
        )
        return 2

    bash = shutil.which("bash")
    if bash is None:
        print(
            "ERROR: labpulse edit requires Bash and is supported on "
            "Raspberry Pi OS/Linux.",
            file=sys.stderr,
        )
        return 127

    try:
        edit_script = find_install_assets() / "edit_config.sh"
    except FileNotFoundError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment["LABPULSE_LIVE_DIR"] = str(live_dir)
    try:
        return subprocess.run(
            [bash, str(edit_script)],
            cwd=live_dir,
            env=environment,
            check=False,
        ).returncode
    except FileNotFoundError as error:
        print(f"ERROR: Cannot run {error.filename!r}.", file=sys.stderr)
        return 127


def open_homeassistant() -> int:
    """Open the local Home Assistant interface in the default browser."""

    print(f"Opening Home Assistant: {HOME_ASSISTANT_URL}")
    if webbrowser.open(HOME_ASSISTANT_URL, new=2):
        return 0
    print(
        "ERROR: No graphical browser could be opened. "
        f"Open {HOME_ASSISTANT_URL} manually.",
        file=sys.stderr,
    )
    return 1


def run_setup(
    live_dir_override: str | None,
    *,
    fake_usb: bool,
    backup: bool,
) -> int:
    """Run the packaged installer through the unified command interface."""

    installer_arguments: list[str] = []
    if fake_usb:
        installer_arguments.append("--fake-usb")
    if backup:
        installer_arguments.append("--backup")

    previous_setup_command = os.environ.get("LABPULSE_SETUP_COMMAND")
    previous_live_dir = os.environ.get("LABPULSE_LIVE_DIR")
    os.environ["LABPULSE_SETUP_COMMAND"] = "labpulse setup"
    if live_dir_override is not None:
        os.environ["LABPULSE_LIVE_DIR"] = str(live_directory(live_dir_override))
    try:
        return installer_main(installer_arguments)
    finally:
        if previous_setup_command is None:
            os.environ.pop("LABPULSE_SETUP_COMMAND", None)
        else:
            os.environ["LABPULSE_SETUP_COMMAND"] = previous_setup_command
        if live_dir_override is not None:
            if previous_live_dir is None:
                os.environ.pop("LABPULSE_LIVE_DIR", None)
            else:
                os.environ["LABPULSE_LIVE_DIR"] = previous_live_dir


def build_parser() -> argparse.ArgumentParser:
    """Build the operator command-line parser."""

    parser = argparse.ArgumentParser(
        prog="labpulse",
        description="Control the installed LabPulse Docker deployment.",
    )
    parser.add_argument(
        "--live-dir",
        metavar="DIR",
        help="live deployment directory (default: ~/labpulse-live)",
    )
    commands = parser.add_subparsers(dest="action", required=True)

    setup_parser = commands.add_parser(
        "setup", help="create or refresh the live LabPulse installation"
    )
    setup_parser.add_argument(
        "-fake_usb",
        "--fake-usb",
        "--fake_usb",
        dest="fake_usb",
        action="store_true",
        help="configure simulated USB serial hardware",
    )
    setup_parser.add_argument(
        "--backup",
        action="store_true",
        help="back up generated and package-managed files before replacement",
    )

    up_parser = commands.add_parser(
        "up", help="start the stack or selected services in the background"
    )
    up_parser.add_argument(
        "--build",
        action="store_true",
        help="rebuild local LabPulse images before starting",
    )
    up_parser.add_argument("services", nargs="*", help="optional service names")

    commands.add_parser(
        "down", help="stop and remove containers without deleting persistent data"
    )

    restart_parser = commands.add_parser(
        "restart", help="restart the stack or selected services"
    )
    restart_parser.add_argument("services", nargs="*", help="optional service names")

    ps_parser = commands.add_parser("ps", help="show LabPulse container status")
    ps_parser.add_argument(
        "-a", "--all", action="store_true", help="include stopped containers"
    )

    logs_parser = commands.add_parser("logs", help="show container logs")
    logs_parser.add_argument(
        "-f", "--follow", action="store_true", help="continue following new output"
    )
    logs_parser.add_argument(
        "--tail",
        metavar="LINES",
        help="number of lines to show from the end of each log",
    )
    logs_parser.add_argument(
        "-t", "--timestamps", action="store_true", help="show timestamps"
    )
    logs_parser.add_argument("services", nargs="*", help="optional service names")

    commands.add_parser(
        "edit",
        help="edit, validate, regenerate, and safely apply config.yaml",
    )
    commands.add_parser(
        "open",
        help="open Home Assistant at http://localhost:8123",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the LabPulse operator command."""

    arguments = build_parser().parse_args(argv)

    if arguments.action == "setup":
        return run_setup(
            arguments.live_dir,
            fake_usb=arguments.fake_usb,
            backup=arguments.backup,
        )
    if arguments.action == "open":
        return open_homeassistant()

    live_dir = live_directory(arguments.live_dir)
    if arguments.action == "edit":
        return run_editor(live_dir)

    compose_arguments: list[str]
    if arguments.action == "up":
        compose_arguments = ["up", "-d"]
        if arguments.build:
            compose_arguments.append("--build")
        compose_arguments.extend(arguments.services)
    elif arguments.action == "down":
        compose_arguments = ["down"]
    elif arguments.action == "restart":
        compose_arguments = ["restart", *arguments.services]
    elif arguments.action == "ps":
        compose_arguments = ["ps"]
        if arguments.all:
            compose_arguments.append("--all")
    elif arguments.action == "logs":
        compose_arguments = ["logs"]
        if arguments.follow:
            compose_arguments.append("--follow")
        if arguments.tail is not None:
            compose_arguments.extend(["--tail", arguments.tail])
        if arguments.timestamps:
            compose_arguments.append("--timestamps")
        compose_arguments.extend(arguments.services)
    else:  # pragma: no cover - argparse restricts this value.
        raise AssertionError(f"unsupported action: {arguments.action}")

    return run_compose(live_dir, compose_arguments)


def alias_arguments(action: str, arguments: Sequence[str]) -> list[str]:
    """Insert an alias action after the optional global live-directory flag."""

    values = list(arguments)
    if values[:1] == ["--live-dir"] and len(values) >= 2:
        return ["--live-dir", values[1], action, *values[2:]]
    if values[:1] and values[0].startswith("--live-dir="):
        return [values[0], action, *values[1:]]
    return [action, *values]


def up_main() -> int:
    """Run the standalone ``labpulse-up`` alias."""

    return main(alias_arguments("up", sys.argv[1:]))


def down_main() -> int:
    """Run the standalone ``labpulse-down`` alias."""

    return main(alias_arguments("down", sys.argv[1:]))


def restart_main() -> int:
    """Run the standalone ``labpulse-restart`` alias."""

    return main(alias_arguments("restart", sys.argv[1:]))


def ps_main() -> int:
    """Run the standalone ``labpulse-ps`` alias."""

    return main(alias_arguments("ps", sys.argv[1:]))


def logs_main() -> int:
    """Run the standalone ``labpulse-logs`` alias."""

    return main(alias_arguments("logs", sys.argv[1:]))


def edit_main() -> int:
    """Run the standalone ``labpulse-edit`` alias."""

    return main(alias_arguments("edit", sys.argv[1:]))


def open_main() -> int:
    """Run the standalone ``labpulse-open`` alias."""

    return main(alias_arguments("open", sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
