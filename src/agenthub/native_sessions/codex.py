"""Codex native conversation discovery and exact-ID resume."""

import re
import sqlite3
from pathlib import Path

from ._normalize import normalize_session, unique_sessions
from ._sqlite import read_rows
from .adapter import NativeSessionDiscoveryError
from .model import LaunchSpec, NativeSession

_STATE_DATABASE = re.compile(r"state_(\d+)\.sqlite$")


class CodexSessionAdapter:
    """Read Codex's local thread index and resume threads by UUID."""

    harness_id = "codex"

    def __init__(self, data_directory: Path | None = None) -> None:
        self._data_directory = data_directory or Path.home() / ".codex"

    def _database(self) -> Path | None:
        candidates = (
            (int(match.group(1)), path)
            for path in self._data_directory.glob("state_*.sqlite")
            if (match := _STATE_DATABASE.search(path.name)) is not None
        )
        return max(candidates, default=(0, None), key=lambda candidate: candidate[0])[1]

    async def discover(self) -> tuple[NativeSession, ...]:
        database = self._database()
        if database is None:
            return ()
        try:
            sessions = read_rows(
                database,
                """
                SELECT id,
                       COALESCE(NULLIF(TRIM(name), ''), NULLIF(TRIM(title), ''), 'Untitled')
                           AS name,
                       NULLIF(cwd, '') AS cwd, rollout_path
                FROM threads
                WHERE archived = 0
                ORDER BY recency_at_ms DESC, updated_at DESC
                """,
                self._convert_row,
            )
            return unique_sessions(sessions)
        except (OSError, sqlite3.Error) as error:
            raise NativeSessionDiscoveryError(f"Codex discovery failed: {error}") from error

    @classmethod
    def _convert_row(cls, row: sqlite3.Row) -> NativeSession | None:
        raw_rollout_path = row["rollout_path"]
        if not isinstance(raw_rollout_path, str) or not raw_rollout_path.strip():
            return None
        rollout_path = Path(raw_rollout_path).expanduser()
        if not rollout_path.is_file():
            return None
        cwd = Path(row["cwd"]).expanduser() if row["cwd"] else None
        return normalize_session(cls.harness_id, row["id"], row["name"], cwd)

    async def resume(self, session: NativeSession) -> LaunchSpec:
        cwd = session.cwd if session.cwd is not None and session.cwd.is_dir() else Path.home()
        return LaunchSpec(("codex", "resume", session.native_session_id), cwd)
