"""OpenCode native conversation discovery and exact-ID resume."""

import os
import sqlite3
from pathlib import Path

from agenthub.native_sessions import NativeSessionAdapter
from agenthub.native_sessions._utils import (
    normalize_session,
    read_rows,
    run_delete_command,
    unique_sessions,
)
from agenthub.native_sessions.adapter import NativeSessionDiscoveryError
from agenthub.native_sessions.model import LaunchSpec, NativeSession

_REQUIRED_SESSION_COLUMNS = frozenset(
    {"id", "title", "directory", "parent_id", "time_archived", "time_updated"}
)


class OpenCodeSessionAdapter:
    """Read OpenCode's global session index and resume root sessions by ID."""

    harness_id = "opencode"
    supports_delete = True

    def __init__(self, database: Path | None = None) -> None:
        configured_data_home = os.environ.get("XDG_DATA_HOME")
        data_home = (
            Path(configured_data_home).expanduser()
            if configured_data_home
            else Path.home() / ".local/share"
        )
        self._database = database or data_home / "opencode/opencode.db"

    def discover(self) -> tuple[NativeSession, ...]:
        if not self._database.is_file():
            return ()
        try:
            columns = frozenset(
                read_rows(
                    self._database,
                    "PRAGMA table_info(session)",
                    lambda row: str(row["name"]),
                )
            )
        except (OSError, sqlite3.Error) as error:
            raise NativeSessionDiscoveryError(
                f"OpenCode discovery failed: {error}"
            ) from error

        missing_columns = _REQUIRED_SESSION_COLUMNS - columns
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise NativeSessionDiscoveryError(
                f"OpenCode session database has an unsupported schema; missing: {missing}"
            )

        try:
            sessions = read_rows(
                self._database,
                """
                SELECT id, title, directory
                FROM session
                WHERE parent_id IS NULL AND time_archived IS NULL
                ORDER BY time_updated DESC
                """,
                self._convert_row,
            )
            return unique_sessions(sessions)
        except (OSError, sqlite3.Error) as error:
            raise NativeSessionDiscoveryError(
                f"OpenCode discovery failed: {error}"
            ) from error

    @classmethod
    def _convert_row(cls, row: sqlite3.Row) -> NativeSession | None:
        raw_directory = row["directory"]
        cwd = (
            Path(raw_directory).expanduser()
            if isinstance(raw_directory, str) and raw_directory.strip()
            else None
        )
        return normalize_session(cls.harness_id, row["id"], row["title"], cwd)

    async def resume(self, session: NativeSession) -> LaunchSpec:
        cwd = session.cwd if session.cwd is not None and session.cwd.is_dir() else Path.home()
        return LaunchSpec(("opencode", "--session", session.native_session_id), cwd)

    async def delete(self, session: NativeSession) -> None:
        """Permanently delete an OpenCode session by its exact native ID."""

        await run_delete_command(("opencode", "session", "delete", session.native_session_id))


_OPENCODE_SESSION_ADAPTER_TYPE_CHECK: NativeSessionAdapter = OpenCodeSessionAdapter()
