"""Shared shell-free execution for provider-native session commands."""

import asyncio
from collections.abc import Sequence

from .adapter import NativeSessionDeletionError

_DELETE_TIMEOUT_SECONDS = 30


async def run_delete_command(command: Sequence[str]) -> None:
    """Run one non-interactive native deletion command and require success."""

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as error:
        raise NativeSessionDeletionError(
            f"could not launch {command[0]}: {error}"
        ) from error

    try:
        async with asyncio.timeout(_DELETE_TIMEOUT_SECONDS):
            stdout, stderr = await process.communicate()
    except TimeoutError as error:
        process.kill()
        await process.wait()
        raise NativeSessionDeletionError(
            f"{command[0]} deletion timed out"
        ) from error

    if process.returncode == 0:
        return

    detail = stderr.decode(errors="replace").strip()
    if not detail:
        detail = stdout.decode(errors="replace").strip()
    if not detail:
        detail = f"exit status {process.returncode}"
    raise NativeSessionDeletionError(f"{command[0]} deletion failed: {detail}")
