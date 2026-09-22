"""Private helpers shared by provider-native session adapters."""

import asyncio
import sqlite3
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from .adapter import NativeSessionDeletionError
from .model import NativeSession

_DELETE_TIMEOUT_SECONDS = 30


async def run_delete_command(command: Sequence[str]) -> None:
    """Run one non-interactive native deletion command and require success."""

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
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


def normalize_session(
    harness_id: str,
    native_session_id: object,
    name: object,
    cwd: Path | None,
) -> NativeSession | None:
    """Normalize one provider record, rejecting records without an identity."""

    normalized_id = str(native_session_id or "").strip()
    if not normalized_id:
        return None
    normalized_name = str(name or "").strip() or "Untitled"
    return NativeSession(harness_id, normalized_id, normalized_name, cwd)


def unique_sessions(
    sessions: Iterable[NativeSession | None],
) -> tuple[NativeSession, ...]:
    """Discard invalid records and preserve the first occurrence of each native ID."""

    unique: list[NativeSession] = []
    seen_ids: set[str] = set()
    for session in sessions:
        if session is None or session.native_session_id in seen_ids:
            continue
        seen_ids.add(session.native_session_id)
        unique.append(session)
    return tuple(unique)


def read_rows[T](
    database: Path,
    query: str,
    convert: Callable[[sqlite3.Row], T],
) -> tuple[T, ...]:
    """Read and convert rows without creating or modifying a provider database."""

    uri = f"{database.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=1)
    connection.row_factory = sqlite3.Row
    try:
        rows: Sequence[sqlite3.Row] = connection.execute(query).fetchall()
        return tuple(convert(row) for row in rows)
    finally:
        connection.close()
