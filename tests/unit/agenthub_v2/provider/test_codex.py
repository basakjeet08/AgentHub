"""Unit coverage for Codex provider session discovery."""

import sqlite3
from pathlib import Path

import pytest

from agenthub_v2.provider.codex import CodexProvider
from agenthub_v2.provider.protocol import DiscoveredSession

_CODEX_SCHEMA = """
CREATE TABLE threads (
    id TEXT,
    name TEXT,
    title TEXT,
    cwd TEXT,
    rollout_path TEXT,
    archived INTEGER,
    recency_at_ms INTEGER,
    updated_at INTEGER
)
"""

_CODEX_INSERT = """
INSERT INTO threads
    (id, name, title, cwd, rollout_path, archived, recency_at_ms, updated_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


def _create_threads(path: Path, rows: tuple[tuple[object, ...], ...]) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(_CODEX_SCHEMA)
        connection.executemany(_CODEX_INSERT, rows)
        connection.commit()
    finally:
        connection.close()


def test_codex_discovers_threads_with_rollout_files(tmp_path: Path) -> None:
    rollout = tmp_path / "rollout-a.jsonl"
    rollout.touch()
    archived_rollout = tmp_path / "archived.jsonl"
    archived_rollout.touch()
    _create_threads(
        tmp_path / "state_5.sqlite",
        (
            ("codex-1", "Alpha thread", "", str(tmp_path), str(rollout), 0, 20, 10),
            (
                "codex-2",
                "Stale thread",
                "Stale title",
                str(tmp_path),
                str(tmp_path / "missing.jsonl"),
                0,
                30,
                5,
            ),
            (
                "codex-3",
                "Archived thread",
                "",
                str(tmp_path),
                str(archived_rollout),
                1,
                40,
                20,
            ),
        ),
    )

    assert CodexProvider(tmp_path).discover_sessions() == (
        DiscoveredSession("codex", "codex-1", "Alpha thread", tmp_path),
    )


def test_codex_discovers_nothing_without_rollout_files(tmp_path: Path) -> None:
    _create_threads(
        tmp_path / "state_5.sqlite",
        (
            (
                "codex-1",
                "Stale thread",
                "",
                str(tmp_path),
                str(tmp_path / "missing.jsonl"),
                0,
                1,
                1,
            ),
        ),
    )

    assert CodexProvider(tmp_path).discover_sessions() == ()


def test_codex_resolves_directory_environment_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / "codex-home"
    sqlite_home = tmp_path / "sqlite-home"
    monkeypatch.setenv("CODEX_SQLITE_HOME", str(sqlite_home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    assert CodexProvider()._configured_data_directory() == sqlite_home

    monkeypatch.delenv("CODEX_SQLITE_HOME")
    assert CodexProvider()._configured_data_directory() == codex_home

    monkeypatch.delenv("CODEX_HOME")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert CodexProvider()._configured_data_directory() == tmp_path / ".codex"
