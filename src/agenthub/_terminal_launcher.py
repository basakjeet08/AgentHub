"""Child-side working-directory setup for terminal-hosted commands."""

import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn


def build_launch_command(
    working_directory: Path,
    command: Sequence[str],
) -> tuple[str, ...]:
    """Build the shell-free helper command passed to textual-tty."""

    if not command:
        raise ValueError("a terminal launch command may not be empty")

    return (
        sys.executable,
        "-m",
        "agenthub._terminal_launcher",
        str(working_directory),
        *command,
    )


def launch(argv: Sequence[str] | None = None) -> NoReturn:
    """Change this child process's directory, then replace it with the harness."""

    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) < 2:
        raise SystemExit("usage: launcher WORKING_DIRECTORY COMMAND [ARG ...]")

    working_directory, *command = arguments
    try:
        os.chdir(working_directory)
        os.execvp(command[0], command)
    except OSError as error:
        print(
            f"agenthub: unable to launch {command[0]!r} in {working_directory!r}: {error}",
            file=sys.stderr,
        )
        raise SystemExit(127) from error


if __name__ == "__main__":
    launch()
