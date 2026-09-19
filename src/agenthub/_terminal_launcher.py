"""Child-side working-directory and environment setup for hosted commands."""

import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn


def build_launch_command(
    working_directory: Path,
    command: Sequence[str],
    *,
    environment_file: Path | None = None,
) -> tuple[str, ...]:
    """Build the shell-free helper command passed to textual-tty."""

    if not command:
        raise ValueError("a terminal launch command may not be empty")

    environment_arguments: tuple[str, ...] = ()
    if environment_file is not None:
        environment_arguments = ("--environment-file", str(environment_file))
    return (
        sys.executable,
        "-m",
        "agenthub._terminal_launcher",
        *environment_arguments,
        str(working_directory),
        *command,
    )


def _read_environment_file(path: Path) -> dict[str, str]:
    """Consume validated child-only overrides, failing open on any error."""

    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(decoded, dict):
            return {}
        return {
            key: value
            for key, value in decoded.items()
            if isinstance(key, str)
            and isinstance(value, str)
            and key
            and "=" not in key
            and "\x00" not in key
            and "\x00" not in value
        }
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def launch(argv: Sequence[str] | None = None) -> NoReturn:
    """Change this child process's directory, then replace it with the harness."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    environment_file: Path | None = None
    if len(arguments) >= 2 and arguments[0] == "--environment-file":
        environment_file = Path(arguments[1])
        arguments = arguments[2:]
    if len(arguments) < 2:
        raise SystemExit(
            "usage: launcher [--environment-file FILE] WORKING_DIRECTORY COMMAND [ARG ...]"
        )

    working_directory, *command = arguments
    try:
        environment = os.environ.copy()
        if environment_file is not None:
            environment.update(_read_environment_file(environment_file))
        os.chdir(working_directory)
        os.execvpe(command[0], command, environment)
    except OSError as error:
        print(
            f"agenthub: unable to launch {command[0]!r} in {working_directory!r}: {error}",
            file=sys.stderr,
        )
        raise SystemExit(127) from error


if __name__ == "__main__":
    launch()
