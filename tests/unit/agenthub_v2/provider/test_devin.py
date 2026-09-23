"""Unit coverage for Devin provider session discovery."""

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agenthub_v2.provider.devin import DevinProvider
from agenthub_v2.provider.protocol import DiscoveredSession

_DEVIN_SCHEMA = """
CREATE TABLE sessions (
    id TEXT,
    title TEXT,
    working_directory TEXT,
    hidden INTEGER,
    last_activity_at INTEGER
)
"""

_DEVIN_INSERT = """
INSERT INTO sessions (id, title, working_directory, hidden, last_activity_at)
VALUES (?, ?, ?, ?, ?)
"""


def test_devin_prefers_xdg_database_and_retains_legacy_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    xdg_home = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_home))

    provider = DevinProvider()

    assert provider._database_candidates == (
        xdg_home / "devin/cli/sessions.db",
        tmp_path / ".local/share/devin/cli/sessions.db",
    )

    legacy_database = provider._database_candidates[1]
    legacy_database.parent.mkdir(parents=True)
    legacy_database.touch()
    assert provider._database() == legacy_database

    xdg_database = provider._database_candidates[0]
    xdg_database.parent.mkdir(parents=True)
    xdg_database.touch()
    assert provider._database() == xdg_database


def test_devin_discovers_visible_sessions(tmp_path: Path) -> None:
    database = tmp_path / "sessions.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(_DEVIN_SCHEMA)
        connection.executemany(
            _DEVIN_INSERT,
            (
                ("devin-1", "Devin work", str(tmp_path), 0, 5),
                ("devin-2", "Recent work", str(tmp_path), 0, 9),
                ("devin-3", "Hidden work", str(tmp_path), 1, 8),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    assert DevinProvider(database).discover_sessions() == (
        DiscoveredSession("devin", "devin-2", "Recent work", tmp_path),
        DiscoveredSession("devin", "devin-1", "Devin work", tmp_path),
    )


def test_devin_resume_command_matches_launch_contract(tmp_path: Path) -> None:
    provider = DevinProvider(tmp_path / "sessions.db")

    assert provider.resume_command("devin-1") == ("devin", "--resume", "devin-1")


async def test_devin_delete_session_runs_exact_command(tmp_path: Path) -> None:
    provider = DevinProvider(tmp_path / "sessions.db")

    with patch(
        "agenthub_v2.provider.devin.service.run_delete_command", new=AsyncMock()
    ) as delete_command:
        await provider.delete_session("devin-1")

    delete_command.assert_awaited_once_with(("devin", "rm", "--force", "devin-1"))
