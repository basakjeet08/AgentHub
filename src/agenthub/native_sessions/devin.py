"""Devin native conversation discovery and exact-ID resume."""

import sqlite3
from pathlib import Path

from ._normalize import normalize_session, unique_sessions
from ._sqlite import read_rows
from .adapter import NativeSessionDiscoveryError
from .model import LaunchSpec, NativeSession


class DevinSessionAdapter:
    """Read Devin's local session index and resume sessions by ID."""

    harness_id = "devin"

    def __init__(self, database: Path | None = None) -> None:
        self._database = database or Path.home() / ".local/share/devin/cli/sessions.db"

    async def discover(self) -> tuple[NativeSession, ...]:
        if not self._database.is_file():
            return ()
        try:
            sessions = read_rows(
                self._database,
                """
                SELECT id, COALESCE(NULLIF(TRIM(title), ''), 'Untitled') AS name,
                       NULLIF(working_directory, '') AS cwd
                FROM sessions
                WHERE hidden = 0
                ORDER BY last_activity_at DESC
                """,
                self._convert_row,
            )
            return unique_sessions(sessions)
        except (OSError, sqlite3.Error) as error:
            raise NativeSessionDiscoveryError(f"Devin discovery failed: {error}") from error

    @classmethod
    def _convert_row(cls, row: sqlite3.Row) -> NativeSession | None:
        cwd = Path(row["cwd"]).expanduser() if row["cwd"] else None
        return normalize_session(cls.harness_id, row["id"], row["name"], cwd)

    async def resume(self, session: NativeSession) -> LaunchSpec:
        cwd = session.cwd if session.cwd is not None and session.cwd.is_dir() else Path.home()
        return LaunchSpec(("devin", "--resume", session.native_session_id), cwd)
