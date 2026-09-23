"""Unit coverage for the shared provider discovery helpers."""

import sqlite3
from pathlib import Path

import pytest

from agenthub_v2.provider.protocol import DiscoveredSession
from agenthub_v2.provider.utils import normalize_discovered_session, read_rows


def test_normalize_keeps_identity_and_strips_values(tmp_path: Path) -> None:
    session = normalize_discovered_session("codex", "  codex-1  ", "  Codex work  ", tmp_path)

    assert session == DiscoveredSession(
        provider_id="codex",
        provider_session_id="codex-1",
        name="Codex work",
        cwd=tmp_path,
    )


def test_normalize_names_empty_values_after_the_default() -> None:
    session = normalize_discovered_session("devin", "devin-1", "   ", None)

    assert session is not None
    assert session.name == "Untitled"


def test_normalize_repairs_invalid_cwd_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    session = normalize_discovered_session("devin", "devin-1", "Devin", tmp_path / "missing")

    assert session is not None
    assert session.cwd == tmp_path


def test_normalize_rejects_records_without_identity() -> None:
    assert normalize_discovered_session("codex", None, "Codex", None) is None
    assert normalize_discovered_session("codex", "", "Codex", None) is None
    assert normalize_discovered_session("codex", "   ", "Codex", None) is None


def test_read_rows_skips_converters_that_reject_rows(tmp_path: Path) -> None:
    database = tmp_path / "sample.db"
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE items (id TEXT)")
        connection.executemany("INSERT INTO items (id) VALUES (?)", [("kept",), (None,)])
        connection.commit()
    finally:
        connection.close()

    rows = read_rows(
        database,
        "SELECT id FROM items",
        lambda row: str(row["id"] or "").strip() or None,
    )

    assert rows == ("kept",)
