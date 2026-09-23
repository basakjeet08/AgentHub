"""Devin provider implementation."""

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


class DevinProvider:
    """Provider operations for Devin."""

    command = COMMAND
    display_name = DISPLAY_NAME
    icon = ICON
    provider_id = PROVIDER_ID

    def __init__(self, database: Path | None = None) -> None:
        """Initialize the local conversation database candidates."""

        self._database_candidates = (
            (database,) if database is not None else self._configured_candidates()
        )

    @staticmethod
    def _configured_candidates() -> tuple[Path, ...]:
        """Return Devin database locations in preferred discovery order."""

        fallback = Path.home() / ".local/share/devin/cli/sessions.db"
        configured_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
        if not configured_data_home:
            return (fallback,)

        configured = Path(configured_data_home).expanduser() / "devin/cli/sessions.db"
        if configured == fallback:
            return (configured,)

        return (configured, fallback)

    def _database(self) -> Path | None:
        """Return the first Devin database that currently exists."""

        return next((path for path in self._database_candidates if path.is_file()), None)

    @classmethod
    def _convert_row(cls, row: sqlite3.Row) -> DiscoveredSession | None:
        cwd = Path(row["cwd"]).expanduser() if row["cwd"] else None

        return normalize_discovered_session(
            cls.provider_id,
            row["id"],
            row["name"],
            cwd,
        )

    def discover_sessions(self) -> tuple[DiscoveredSession, ...]:
        """Discover locally persisted Devin sessions."""

        try:
            database = self._database()
            if database is None:
                return ()

            return read_rows(
                database,
                """
                SELECT id,
                       COALESCE(NULLIF(TRIM(title), ''), 'Untitled') AS name,
                       NULLIF(working_directory, '') AS cwd
                FROM sessions
                WHERE hidden = 0
                ORDER BY last_activity_at DESC
                """,
                self._convert_row,
            )

        except (OSError, sqlite3.Error) as error:
            raise RuntimeError(f"Devin discovery failed: {error}") from error

    def resume_command(self, provider_session_id: str) -> tuple[str, ...]:
        """Return the command used to resume a Devin session."""

        return (*self.command, "--resume", provider_session_id)

    async def delete_session(self, provider_session_id: str) -> None:
        """Delete a Devin session."""

        await run_delete_command((*self.command, "rm", "--force", provider_session_id))
