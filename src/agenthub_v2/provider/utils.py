"""Shared helpers for coding-agent providers."""

import asyncio
import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path

from .protocol import DiscoveredSession

_DELETE_TIMEOUT_SECONDS = 30


def normalize_discovered_session(
    provider_id: str,
    provider_session_id: object,
    name: object,
    cwd: Path | None,
) -> DiscoveredSession | None:
    """
    Normalize one discovered provider record while rejecting records without
    an identity.
    """

    provider_session_id = str(provider_session_id or "").strip()
    if not provider_session_id:
        return None

    normalized_cwd = cwd if cwd is not None and cwd.is_dir() else Path.home()

    return DiscoveredSession(
        provider_id=provider_id,
        provider_session_id=provider_session_id,
        name=str(name or "").strip() or "Untitled",
        cwd=normalized_cwd,
    )


def read_rows[T](
    database: Path,
    query: str,
    convert: Callable[[sqlite3.Row], T | None],
) -> tuple[T, ...]:
    """Read and convert rows from a provider database."""

    uri = f"{database.resolve().as_uri()}?mode=ro"

    connection = sqlite3.connect(uri, uri=True, timeout=1)
    connection.row_factory = sqlite3.Row

    try:
        rows: Sequence[sqlite3.Row] = connection.execute(query).fetchall()

        converted_rows: list[T] = []
        for row in rows:
            converted = convert(row)
            if converted is not None:
                converted_rows.append(converted)

        return tuple(converted_rows)
    finally:
        connection.close()


async def run_delete_command(command: Sequence[str]) -> None:
    """Run one non-interactive provider deletion command and require success."""

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as error:
        raise RuntimeError(f"Could not launch {command[0]}: {error}") from error

    try:
        async with asyncio.timeout(_DELETE_TIMEOUT_SECONDS):
            stdout, stderr = await process.communicate()
    except TimeoutError as error:
        process.kill()
        await process.wait()
        raise RuntimeError(f"{command[0]} deletion timed out") from error

    if process.returncode == 0:
        return

    detail = stderr.decode(errors="replace").strip()
    if not detail:
        detail = stdout.decode(errors="replace").strip()
    if not detail:
        detail = f"exit status {process.returncode}"

    raise RuntimeError(f"{command[0]} deletion failed: {detail}")
