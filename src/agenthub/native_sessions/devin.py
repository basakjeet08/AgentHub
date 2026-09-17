"""Devin native conversation discovery and exact-ID resume."""

import os
import sqlite3
from pathlib import Path

from ._command import run_delete_command
from ._normalize import normalize_session, unique_sessions
from ._sqlite import read_rows
from .adapter import NativeSessionDiscoveryError
from .model import LaunchSpec, NativeSession


class DevinSessionAdapter:
    """Read Devin's local session index and resume sessions by ID."""

    harness_id = "devin"

    def __init__(self, database: Path | None = None) -> None:
        self._database_candidates = (
            (database,) if database is not None else self._configured_database_candidates()
        )

    @staticmethod
    def _configured_database_candidates() -> tuple[Path, ...]:
        """Return Devin database locations in preferred discovery order."""

        fallback = Path.home() / ".local/share/devin/cli/sessions.db"
        configured_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
        if not configured_data_home:
            return (fallback,)
        configured = Path(configured_data_home).expanduser() / "devin/cli/sessions.db"
        return (configured,) if configured == fallback else (configured, fallback)

    def _database(self) -> Path | None:
        """Return the first provider database that currently exists."""

        return next((path for path in self._database_candidates if path.is_file()), None)

    def discover(self) -> tuple[NativeSession, ...]:
        database = self._database()
        if database is None:
            return ()
        try:
            sessions = read_rows(
                database,
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

    async def delete(self, session: NativeSession) -> None:
        """Permanently delete a Devin session by its exact native ID."""

        await run_delete_command(("devin", "rm", "--force", session.native_session_id))
