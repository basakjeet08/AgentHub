"""Antigravity native conversation discovery and exact-ID resume."""

import json
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse

from agenthub.native_sessions._utils import normalize_session, read_rows, unique_sessions
from agenthub.native_sessions.adapter import (
    NativeSessionDeletionUnavailableError,
    NativeSessionDiscoveryError,
)
from agenthub.native_sessions.model import LaunchSpec, NativeSession


class AntigravitySessionAdapter:
    """Read Antigravity's local summary index and resume conversations by ID."""

    harness_id = "antigravity"
    supports_delete = False

    def __init__(self, database: Path | None = None) -> None:
        self._database = (
            database
            or Path.home() / ".gemini/antigravity-cli/conversation_summaries.db"
        )

    def discover(self) -> tuple[NativeSession, ...]:
        if not self._database.is_file():
            return ()
        try:
            sessions = read_rows(
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
            return unique_sessions(sessions)
        except (OSError, sqlite3.Error) as error:
            raise NativeSessionDiscoveryError(
                f"Antigravity discovery failed: {error}"
            ) from error

    @classmethod
    def _convert_row(cls, row: sqlite3.Row) -> NativeSession | None:
        cwd = cls._first_workspace(row["workspace_uris"])
        return normalize_session(cls.harness_id, row["id"], row["name"], cwd)

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

    async def resume(self, session: NativeSession) -> LaunchSpec:
        cwd = session.cwd if session.cwd is not None and session.cwd.is_dir() else Path.home()
        return LaunchSpec(("agy", "--conversation", session.native_session_id), cwd)

    async def delete(self, session: NativeSession) -> None:
        """Reject unsafe storage edits when no headless native delete API exists."""

        raise NativeSessionDeletionUnavailableError.for_provider("Antigravity")
