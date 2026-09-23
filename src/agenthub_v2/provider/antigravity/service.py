"""Antigravity provider implementation."""

import json
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse

from agenthub_v2.provider.protocol import DiscoveredSession
from agenthub_v2.provider.utils import normalize_discovered_session, read_rows

from ._config import COMMAND, DISPLAY_NAME, ICON, PROVIDER_ID


class AntigravityProvider:
    """Provider operations for Antigravity."""

    command = COMMAND
    display_name = DISPLAY_NAME
    icon = ICON
    provider_id = PROVIDER_ID

    def __init__(self, database: Path | None = None) -> None:
        """Initialize the local conversation database."""

        self._database = database or self._configured_database()

    @staticmethod
    def _configured_database() -> Path:
        """Resolve Antigravity's SQLite database."""

        return Path.home() / ".gemini/antigravity-cli/conversation_summaries.db"

    @staticmethod
    def _first_workspace(raw_workspaces: str) -> Path | None:
        try:
            workspaces = json.loads(raw_workspaces)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(workspaces, list) or not workspaces:
            return None
        workspace = workspaces[0]
        if not isinstance(workspace, str):
            return None
        parsed = urlparse(workspace)
        if parsed.scheme == "file":
            return Path(unquote(parsed.path))
        if not parsed.scheme:
            return Path(workspace).expanduser()
        return None

    @classmethod
    def _convert_row(cls, row: sqlite3.Row) -> DiscoveredSession | None:
        cwd = cls._first_workspace(row["workspace_uris"])

        return normalize_discovered_session(
            cls.provider_id,
            row["id"],
            row["name"],
            cwd,
        )

    def discover_sessions(self) -> tuple[DiscoveredSession, ...]:
        """Discover locally persisted Antigravity sessions."""

        try:
            if not self._database.is_file():
                return ()

            return read_rows(
                self._database,
                """
                SELECT conversation_id AS id,
                       COALESCE(NULLIF(TRIM(title), ''), 'Untitled') AS name,
                       workspace_uris
                FROM conversation_summaries
                WHERE killed = 0
                  AND (
                      COALESCE(step_count, 0) > 0
                      OR COALESCE(last_user_input_step_index, -1) >= 0
                  )
                ORDER BY last_modified_time DESC
                """,
                self._convert_row,
            )

        except (OSError, sqlite3.Error) as error:
            raise RuntimeError(f"Antigravity discovery failed: {error}") from error

    def resume_command(self, provider_session_id: str) -> tuple[str, ...]:
        """Return the command used to resume an Antigravity session."""

        return (*self.command, "--conversation", provider_session_id)

    async def delete_session(self, provider_session_id: str) -> None:
        """Reject deletion because Antigravity has no supported headless delete API."""

        raise RuntimeError("Antigravity does not support programmatic session deletion.")
