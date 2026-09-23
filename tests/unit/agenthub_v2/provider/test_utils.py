"""Unit coverage for the shared provider discovery helpers."""

import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from agenthub_v2.provider.protocol import DiscoveredSession
from agenthub_v2.provider.utils import normalize_discovered_session, read_rows, run_delete_command


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


def _process_mock(returncode: int, stdout: bytes, stderr: bytes) -> Mock:
    process = Mock()
    process.communicate = AsyncMock(return_value=(stdout, stderr))
    process.returncode = returncode
    return process


async def test_run_delete_command_returns_on_clean_exit() -> None:
    launcher = AsyncMock(return_value=_process_mock(0, b"", b""))

    with patch("agenthub_v2.provider.utils.asyncio.create_subprocess_exec", new=launcher):
        await run_delete_command(("codex", "delete", "--force", "codex-1"))

    launcher.assert_awaited_once_with(
        "codex",
        "delete",
        "--force",
        "codex-1",
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def test_run_delete_command_raises_with_stderr_detail() -> None:
    launcher = AsyncMock(return_value=_process_mock(1, b"", b"permission denied"))

    with (
        patch("agenthub_v2.provider.utils.asyncio.create_subprocess_exec", new=launcher),
        pytest.raises(RuntimeError, match="permission denied"),
    ):
        await run_delete_command(("devin", "rm", "devin-1"))


async def test_run_delete_command_falls_back_to_stdout_detail() -> None:
    launcher = AsyncMock(return_value=_process_mock(1, b"boom", b""))

    with (
        patch("agenthub_v2.provider.utils.asyncio.create_subprocess_exec", new=launcher),
        pytest.raises(RuntimeError, match="boom"),
    ):
        await run_delete_command(("opencode", "session", "delete", "open-1"))


async def test_run_delete_command_raises_when_launch_fails() -> None:
    launcher = Mock(side_effect=OSError("not found"))

    with (
        patch("agenthub_v2.provider.utils.asyncio.create_subprocess_exec", new=launcher),
        pytest.raises(RuntimeError, match="Could not launch"),
    ):
        await run_delete_command(("codex", "delete", "codex-1"))


async def test_run_delete_command_kills_process_on_timeout() -> None:
    process = Mock()
    process.communicate = AsyncMock(side_effect=TimeoutError)
    process.kill = Mock()
    process.wait = AsyncMock()
    launcher = AsyncMock(return_value=process)

    with (
        patch("agenthub_v2.provider.utils.asyncio.create_subprocess_exec", new=launcher),
        pytest.raises(RuntimeError, match="timed out"),
    ):
        await run_delete_command(("devin", "rm", "devin-1"))

    process.kill.assert_called_once()
    process.wait.assert_awaited_once()
