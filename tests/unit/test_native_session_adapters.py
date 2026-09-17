"""Unit coverage for provider-native session normalization."""

import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agenthub.native_sessions import (
    NativeSessionDeletionError,
    NativeSessionDiscoveryError,
)
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


def test_codex_resolves_configured_state_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / "codex-home"
    sqlite_home = tmp_path / "sqlite-home"
    explicit_home = tmp_path / "explicit-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CODEX_SQLITE_HOME", str(sqlite_home))

    assert CodexSessionAdapter()._data_directory == sqlite_home
    assert CodexSessionAdapter(explicit_home)._data_directory == explicit_home

    monkeypatch.delenv("CODEX_SQLITE_HOME")
    assert CodexSessionAdapter()._data_directory == codex_home


def test_codex_ignores_empty_state_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("CODEX_HOME", "  ")
    monkeypatch.setenv("CODEX_SQLITE_HOME", "")

    assert CodexSessionAdapter()._data_directory == tmp_path / ".codex"


def test_devin_prefers_xdg_database_and_retains_legacy_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    xdg_home = tmp_path / "xdg"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_home))

    adapter = DevinSessionAdapter()

    assert adapter._database_candidates == (
        xdg_home / "devin/cli/sessions.db",
        tmp_path / ".local/share/devin/cli/sessions.db",
    )

    legacy_database = adapter._database_candidates[1]
    legacy_database.parent.mkdir(parents=True)
    legacy_database.touch()
    assert adapter._database() == legacy_database

    xdg_database = adapter._database_candidates[0]
    xdg_database.parent.mkdir(parents=True)
    xdg_database.touch()
    assert adapter._database() == xdg_database


def test_devin_explicit_database_overrides_xdg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    explicit_database = tmp_path / "sessions.db"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))

    assert DevinSessionAdapter(explicit_database)._database_candidates == (
        explicit_database,
    )


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

    sessions = adapter.discover()
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

    assert CodexSessionAdapter(tmp_path).discover() == ()


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

    sessions = adapter.discover()
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

    sessions = adapter.discover()
    launch = await adapter.resume(sessions[0])

    assert sessions[0].cwd == tmp_path
    assert launch.command == ("agy", "--conversation", "agy-id")


async def test_antigravity_skips_zero_step_shells_with_summary_metadata(
    tmp_path: Path,
) -> None:
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
            "empty-id",
            "T48914",
            "[]",
            0,
            1,
            0,
            -1,
            "T48914",
            b"\x0a\x06T48914\x22$placeholder-metadata",
        ),
        "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
    )

    assert AntigravitySessionAdapter(database).discover() == ()


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
    sessions = adapter.discover()
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
        OpenCodeSessionAdapter(database).discover()


@pytest.mark.parametrize(
    ("adapter", "module", "expected_command"),
    (
        (
            CodexSessionAdapter(),
            "agenthub.native_sessions.codex.run_delete_command",
            ("codex", "delete", "--force", "native-id"),
        ),
        (
            DevinSessionAdapter(),
            "agenthub.native_sessions.devin.run_delete_command",
            ("devin", "rm", "--force", "native-id"),
        ),
        (
            OpenCodeSessionAdapter(),
            "agenthub.native_sessions.opencode.run_delete_command",
            ("opencode", "session", "delete", "native-id"),
        ),
    ),
)
async def test_native_adapters_delete_by_exact_provider_id(
    adapter,
    module: str,
    expected_command: tuple[str, ...],
) -> None:
    native_session = NativeSession(adapter.harness_id, "native-id", "Title")

    with patch(module, AsyncMock()) as delete_command:
        await adapter.delete(native_session)

    delete_command.assert_awaited_once_with(expected_command)


async def test_antigravity_delete_fails_safely_without_a_headless_native_api() -> None:
    adapter = AntigravitySessionAdapter()
    native_session = NativeSession("antigravity", "native-id", "Title")

    with pytest.raises(
        NativeSessionDeletionError,
        match="does not currently expose programmatic conversation deletion",
    ):
        await adapter.delete(native_session)
