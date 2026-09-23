"""Unit coverage for OpenCode provider session discovery."""

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agenthub_v2.provider.opencode import OpenCodeProvider
from agenthub_v2.provider.protocol import DiscoveredSession

_OPENCODE_SCHEMA = """
CREATE TABLE session (
    id TEXT,
    title TEXT,
    directory TEXT,
    parent_id TEXT,
    time_archived INTEGER,
    time_updated INTEGER
)
"""

_OPENCODE_INSERT = """
INSERT INTO session (id, title, directory, parent_id, time_archived, time_updated)
VALUES (?, ?, ?, ?, ?, ?)
"""


def test_opencode_discovers_only_root_non_archived_sessions(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(_OPENCODE_SCHEMA)
        connection.executemany(
            _OPENCODE_INSERT,
            (
                ("open-1", "Open work", str(tmp_path), None, None, 5),
                ("child-1", "Child", str(tmp_path), "open-1", None, 6),
                ("archived-1", "Archived", str(tmp_path), None, 1, 7),
                ("open-2", "Newest open work", str(tmp_path), None, None, 9),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    assert OpenCodeProvider(database).discover_sessions() == (
        DiscoveredSession("opencode", "open-2", "Newest open work", tmp_path),
        DiscoveredSession("opencode", "open-1", "Open work", tmp_path),
    )


def test_opencode_rejects_unsupported_schemas(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE session (id TEXT)")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RuntimeError, match="unsupported schema"):
        OpenCodeProvider(database).discover_sessions()


def test_opencode_resume_command_matches_launch_contract(tmp_path: Path) -> None:
    provider = OpenCodeProvider(tmp_path / "opencode.db")

    assert provider.resume_command("open-1") == ("opencode", "--session", "open-1")


async def test_opencode_delete_session_runs_exact_command(tmp_path: Path) -> None:
    provider = OpenCodeProvider(tmp_path / "opencode.db")

    with patch(
        "agenthub_v2.provider.opencode.service.run_delete_command", new=AsyncMock()
    ) as delete_command:
        await provider.delete_session("open-1")

    delete_command.assert_awaited_once_with(("opencode", "session", "delete", "open-1"))
