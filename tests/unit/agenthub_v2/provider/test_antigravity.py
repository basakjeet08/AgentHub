"""Unit coverage for Antigravity provider session discovery."""

import json
import sqlite3
from pathlib import Path

import pytest

from agenthub_v2.provider.antigravity import AntigravityProvider
from agenthub_v2.provider.protocol import DiscoveredSession

_ANTIGRAVITY_SCHEMA = """
CREATE TABLE conversation_summaries (
    conversation_id TEXT,
    title TEXT,
    workspace_uris TEXT,
    killed INTEGER,
    step_count INTEGER,
    last_user_input_step_index INTEGER,
    last_modified_time TEXT
)
"""

_ANTIGRAVITY_INSERT = """
INSERT INTO conversation_summaries
    (conversation_id, title, workspace_uris, killed, step_count,
     last_user_input_step_index, last_modified_time)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""


def _create_summaries(path: Path, rows: tuple[tuple[object, ...], ...]) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(_ANTIGRAVITY_SCHEMA)
        connection.executemany(_ANTIGRAVITY_INSERT, rows)
        connection.commit()
    finally:
        connection.close()


def test_antigravity_converts_file_workspace_uris(tmp_path: Path) -> None:
    _create_summaries(
        tmp_path / "conversation_summaries.db",
        (
            (
                "agy-1",
                "Antigravity thread",
                json.dumps([tmp_path.as_uri()]),
                0,
                3,
                1,
                "t1",
            ),
        ),
    )

    assert AntigravityProvider(tmp_path / "conversation_summaries.db").discover_sessions() == (
        DiscoveredSession("antigravity", "agy-1", "Antigravity thread", tmp_path),
    )


def test_antigravity_excludes_zero_step_and_killed_sessions(tmp_path: Path) -> None:
    _create_summaries(
        tmp_path / "conversation_summaries.db",
        (
            ("agy-1", "Active thread", json.dumps([str(tmp_path)]), 0, 2, None, "t1"),
            ("agy-2", "Empty shell", json.dumps([str(tmp_path)]), 0, 0, None, "t2"),
            ("agy-3", "Killed thread", json.dumps([str(tmp_path)]), 1, 4, 1, "t3"),
        ),
    )

    assert AntigravityProvider(tmp_path / "conversation_summaries.db").discover_sessions() == (
        DiscoveredSession("antigravity", "agy-1", "Active thread", tmp_path),
    )


def test_antigravity_resume_command_matches_launch_contract(tmp_path: Path) -> None:
    provider = AntigravityProvider(tmp_path / "conversation_summaries.db")

    assert provider.resume_command("agy-1") == ("agy", "--conversation", "agy-1")


async def test_antigravity_delete_session_rejects_deletion(tmp_path: Path) -> None:
    provider = AntigravityProvider(tmp_path / "conversation_summaries.db")

    with pytest.raises(RuntimeError, match="does not support"):
        await provider.delete_session("agy-1")
