"""Tests for logical session creation and selection."""

from pathlib import Path

import pytest

from agenthub.harnesses import AgentHarness
from agenthub.sessions import SessionManager


def test_manager_starts_empty() -> None:
    manager = SessionManager()

    assert manager.sessions == ()
    assert manager.active_session is None


def test_create_retains_sessions_in_order_and_selects_the_newest(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    first = manager.create(
        name="First",
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    second = manager.create(
        name="Second",
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    assert manager.sessions == (first, second)
    assert manager.active_session is second
    assert first.id != second.id
    assert first.terminal.harness is sleeping_harness


def test_select_changes_only_logical_selection(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    first = manager.create(
        name="First",
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    second = manager.create(
        name="Second",
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    assert manager.select(first.id) is first
    assert manager.active_session is first
    assert manager.sessions == (first, second)
    assert not first.terminal.is_mounted
    assert not second.terminal.is_mounted


def test_select_rejects_unknown_session_without_changing_selection(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    session = manager.create(
        name="Known",
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    with pytest.raises(KeyError):
        manager.select("missing")

    assert manager.active_session is session
