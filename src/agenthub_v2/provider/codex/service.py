"""Codex provider implementation."""

import os
import re
import sqlite3
from pathlib import Path

from agenthub_v2.provider.protocol import DiscoveredSession
from agenthub_v2.provider.utils import (
    normalize_discovered_session,
    read_rows,
    run_delete_command,
)

from ._config import COMMAND, DISPLAY_NAME, ICON, PROVIDER_ID

_STATE_DATABASE = re.compile(r"state_(\d+)\.sqlite$")


class CodexProvider:
    """Provider operations for Codex."""

    command = COMMAND
    display_name = DISPLAY_NAME
    icon = ICON
    provider_id = PROVIDER_ID

    def __init__(self, data_directory: Path | None = None) -> None:
        """Initialize the local database directory."""

        self._data_directory = data_directory or self._configured_data_directory()

    @staticmethod
    def _configured_data_directory() -> Path:
        """Resolve Codex's SQLite directory using its environment precedence."""

        for variable in ("CODEX_SQLITE_HOME", "CODEX_HOME"):
            configured = os.environ.get(variable, "").strip()
            if configured:
                return Path(configured).expanduser()

        return Path.home() / ".codex"

    def _database(self) -> Path | None:
        candidates = (
            (int(match.group(1)), path)
            for path in self._data_directory.glob("state_*.sqlite")
            if (match := _STATE_DATABASE.search(path.name)) is not None
        )

        return max(candidates, default=(0, None), key=lambda candidate: candidate[0])[1]

    @classmethod
    def _convert_row(cls, row: sqlite3.Row) -> DiscoveredSession | None:
        raw_rollout_path = row["rollout_path"]
        if not isinstance(raw_rollout_path, str) or not raw_rollout_path.strip():
            return None

        rollout_path = Path(raw_rollout_path).expanduser()
        if not rollout_path.is_file():
            return None

        cwd = Path(row["cwd"]).expanduser() if row["cwd"] else None

        return normalize_discovered_session(
            cls.provider_id,
            row["id"],
            row["name"],
            cwd,
        )

    def discover_sessions(self) -> tuple[DiscoveredSession, ...]:
        """Discover locally persisted Codex sessions."""

        try:
            database = self._database()
            if database is None:
                return ()

            return read_rows(
                database,
                """
                SELECT id,
                    COALESCE(NULLIF(TRIM(name), ''), NULLIF(TRIM(title), ''), 'Untitled')
                        AS name,
                    NULLIF(cwd, '') AS cwd,
                    rollout_path
                FROM threads
                WHERE archived = 0
                ORDER BY recency_at_ms DESC, updated_at DESC
                """,
                self._convert_row,
            )

        except (OSError, sqlite3.Error) as error:
            raise RuntimeError(f"Codex discovery failed: {error}") from error

    def resume_command(self, provider_session_id: str) -> tuple[str, ...]:
        """Return the command used to resume a Codex session."""

        return (*self.command, "resume", provider_session_id)

    async def delete_session(self, provider_session_id: str) -> None:
        """Delete a Codex session."""

        await run_delete_command((*self.command, "delete", "--force", provider_session_id))
