"""OpenCode provider implementation."""

import os
import sqlite3
from pathlib import Path

from agenthub_v2.provider.protocol import DiscoveredSession
from agenthub_v2.provider.utils import (
    normalize_discovered_session,
    read_rows,
    run_delete_command,
)

from ._config import COMMAND, DISPLAY_NAME, ICON, PROVIDER_ID

_REQUIRED_SESSION_COLUMNS = frozenset(
    {"id", "title", "directory", "parent_id", "time_archived", "time_updated"}
)


class OpenCodeProvider:
    """Provider operations for OpenCode."""

    command = COMMAND
    display_name = DISPLAY_NAME
    icon = ICON
    provider_id = PROVIDER_ID

    def __init__(self, database: Path | None = None) -> None:
        """Initialize the local conversation database."""

        self._database = database or self._configured_database()

    @staticmethod
    def _configured_database() -> Path:
        """Resolve OpenCode's SQLite database."""

        configured_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
        data_home = (
            Path(configured_data_home).expanduser()
            if configured_data_home
            else Path.home() / ".local/share"
        )

        return data_home / "opencode/opencode.db"

    @classmethod
    def _convert_row(cls, row: sqlite3.Row) -> DiscoveredSession | None:
        raw_directory = row["directory"]
        cwd = (
            Path(raw_directory).expanduser()
            if isinstance(raw_directory, str) and raw_directory.strip()
            else None
        )

        return normalize_discovered_session(
            cls.provider_id,
            row["id"],
            row["title"],
            cwd,
        )

    def discover_sessions(self) -> tuple[DiscoveredSession, ...]:
        """Discover locally persisted OpenCode sessions."""

        try:
            if not self._database.is_file():
                return ()

            columns = frozenset(
                read_rows(
                    self._database,
                    "PRAGMA table_info(session)",
                    lambda row: str(row["name"]),
                )
            )
        except (OSError, sqlite3.Error) as error:
            raise RuntimeError(f"OpenCode discovery failed: {error}") from error

        missing_columns = _REQUIRED_SESSION_COLUMNS - columns
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise RuntimeError(
                f"OpenCode session database has an unsupported schema; missing: {missing}"
            )

        try:
            return read_rows(
                self._database,
                """
                SELECT id,
                       title,
                       directory
                FROM session
                WHERE parent_id IS NULL
                  AND time_archived IS NULL
                ORDER BY time_updated DESC
                """,
                self._convert_row,
            )
        except (OSError, sqlite3.Error) as error:
            raise RuntimeError(f"OpenCode discovery failed: {error}") from error

    def resume_command(self, provider_session_id: str) -> tuple[str, ...]:
        """Return the command used to resume an OpenCode session."""

        return (*self.command, "--session", provider_session_id)

    async def delete_session(self, provider_session_id: str) -> None:
        """Delete an OpenCode session."""

        await run_delete_command((*self.command, "session", "delete", provider_session_id))
