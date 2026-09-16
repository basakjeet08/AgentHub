"""Unit coverage for provider-native session normalization."""

import sqlite3
from pathlib import Path

import pytest

from agenthub.native_sessions import NativeSessionDiscoveryError
from agenthub.native_sessions.antigravity import AntigravitySessionAdapter
from agenthub.native_sessions.codex import CodexSessionAdapter
from agenthub.native_sessions.devin import DevinSessionAdapter
from agenthub.native_sessions.model import NativeSession
from agenthub.native_sessions.opencode import OpenCodeSessionAdapter


def _database(path: Path, schema: str, values: tuple[object, ...], insert: str) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(schema)
        connection.execute(insert, values)
        connection.commit()
    finally:
        connection.close()


async def test_codex_discovers_and_resumes_exact_thread(tmp_path: Path) -> None:
    database = tmp_path / "state_5.sqlite"
    rollout = tmp_path / "rollout.jsonl"
    rollout.write_text("{}\n")
    _database(
        database,
        """
        CREATE TABLE threads (
            id TEXT, name TEXT, title TEXT, cwd TEXT, archived INTEGER,
            recency_at_ms INTEGER, updated_at INTEGER, rollout_path TEXT
        )
        """,
        (
            "codex-id",
            "Named thread",
            "Generated title",
            str(tmp_path),
            0,
            2,
            1,
            str(rollout),
        ),
        "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    )
    adapter = CodexSessionAdapter(tmp_path)

    sessions = await adapter.discover()
    launch = await adapter.resume(sessions[0])

    assert sessions == (NativeSession("codex", "codex-id", "Named thread", tmp_path),)
    assert launch.command == ("codex", "resume", "codex-id")
    assert launch.working_directory == tmp_path


async def test_codex_skips_stale_threads_without_rollout_files(tmp_path: Path) -> None:
    database = tmp_path / "state_5.sqlite"
    _database(
        database,
        """
        CREATE TABLE threads (
            id TEXT, name TEXT, title TEXT, cwd TEXT, archived INTEGER,
            recency_at_ms INTEGER, updated_at INTEGER, rollout_path TEXT
        )
        """,
        (
            "stale-id",
            "Stale",
            "Stale",
            str(tmp_path),
            0,
            2,
            1,
            str(tmp_path / "missing.jsonl"),
        ),
        "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
    )

    assert await CodexSessionAdapter(tmp_path).discover() == ()


async def test_devin_discovers_all_visible_sessions(tmp_path: Path) -> None:
    database = tmp_path / "sessions.db"
    _database(
        database,
        """
        CREATE TABLE sessions (
            id TEXT, title TEXT, working_directory TEXT, hidden INTEGER,
            last_activity_at INTEGER
        )
        """,
        ("devin-id", "Devin work", str(tmp_path), 0, 1),
        "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
    )
    adapter = DevinSessionAdapter(database)

    sessions = await adapter.discover()
    launch = await adapter.resume(sessions[0])

    assert sessions[0].native_session_id == "devin-id"
    assert launch.command == ("devin", "--resume", "devin-id")


async def test_antigravity_parses_file_workspace_uri(tmp_path: Path) -> None:
    database = tmp_path / "conversation_summaries.db"
    _database(
        database,
        """
        CREATE TABLE conversation_summaries (
            conversation_id TEXT, title TEXT, workspace_uris TEXT,
            killed INTEGER, last_modified_time INTEGER, step_count INTEGER,
            last_user_input_step_index INTEGER, preview TEXT, raw_summary TEXT
        )
        """,
        (
            "agy-id",
            "Gravity work",
            f'["{tmp_path.as_uri()}"]',
            0,
            1,
            1,
            0,
            "User conversation",
            "{}",
        ),
        "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
    )
    adapter = AntigravitySessionAdapter(database)

    sessions = await adapter.discover()
    launch = await adapter.resume(sessions[0])

    assert sessions[0].cwd == tmp_path
    assert launch.command == ("agy", "--conversation", "agy-id")


async def test_antigravity_skips_zero_content_conversation_shells(tmp_path: Path) -> None:
    database = tmp_path / "conversation_summaries.db"
    _database(
        database,
        """
        CREATE TABLE conversation_summaries (
            conversation_id TEXT, title TEXT, workspace_uris TEXT,
            killed INTEGER, last_modified_time INTEGER, step_count INTEGER,
            last_user_input_step_index INTEGER, preview TEXT, raw_summary TEXT
        )
        """,
        ("empty-id", "Untitled", "[]", 0, 1, 0, -1, "", None),
        "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
    )

    assert await AntigravitySessionAdapter(database).discover() == ()


async def test_opencode_discovers_global_root_sessions_and_resumes_exact_id(
    tmp_path: Path,
) -> None:
    database = tmp_path / "opencode.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            """
            CREATE TABLE session (
                id TEXT, title TEXT, directory TEXT, parent_id TEXT,
                time_archived INTEGER, time_updated INTEGER
            )
            """
        )
        connection.executemany(
            "INSERT INTO session VALUES (?, ?, ?, ?, ?, ?)",
            (
                ("open-id", "Open work", str(tmp_path), None, None, 5),
                ("open-id", "Duplicate", str(tmp_path), None, None, 4),
                ("child-id", "Child", str(tmp_path), "open-id", None, 6),
                ("archived-id", "Archived", str(tmp_path), None, 1, 7),
                ("   ", "Invalid", str(tmp_path), None, None, 3),
                ("untitled-id", "   ", str(tmp_path), None, None, 2),
            ),
        )
        connection.commit()
    finally:
        connection.close()

    adapter = OpenCodeSessionAdapter(database)
    sessions = await adapter.discover()
    launch = await adapter.resume(sessions[0])

    assert sessions == (
        NativeSession("opencode", "open-id", "Open work", tmp_path),
        NativeSession("opencode", "untitled-id", "Untitled", tmp_path),
    )
    assert launch.command == ("opencode", "--session", "open-id")
    assert launch.working_directory == tmp_path


async def test_opencode_rejects_an_unsupported_database_schema(tmp_path: Path) -> None:
    database = tmp_path / "opencode.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE session (id TEXT)")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(NativeSessionDiscoveryError, match="unsupported schema"):
        await OpenCodeSessionAdapter(database).discover()
