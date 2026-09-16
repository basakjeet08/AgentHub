"""Tests for logical session creation and selection."""

from pathlib import Path

import pytest

from agenthub.harnesses import AgentHarness
from agenthub.native_sessions import NativeSession
from agenthub.sessions import SessionKind, SessionManager, SessionState


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
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    second = manager.create(
        name="Second",
        kind=SessionKind.SHELL,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    assert manager.sessions == (first, second)
    assert manager.active_session is second
    assert first.id != second.id
    assert first.kind is SessionKind.AGENT
    assert second.kind is SessionKind.SHELL
    assert first.terminal.harness is sleeping_harness


def test_select_changes_only_logical_selection(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    first = manager.create(
        name="First",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    second = manager.create(
        name="Second",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    assert manager.select(first.id) is first
    assert manager.active_session is first
    assert manager.sessions == (first, second)
    assert not first.terminal.is_mounted
    assert not second.terminal.is_mounted


def test_add_discovered_session_is_unloaded_and_deduplicated(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    native = NativeSession(
        harness_id=sleeping_harness.id,
        native_session_id="native-1",
        name="Existing work",
        cwd=Path.cwd(),
    )

    session = manager.add_discovered(native_session=native, harness=sleeping_harness)
    duplicate = manager.add_discovered(native_session=native, harness=sleeping_harness)

    assert duplicate is session
    assert manager.sessions == (session,)
    assert manager.active_session is None
    assert session.native_session_id == "native-1"
    assert session.terminal is None
    assert session.state is SessionState.UNLOADED


def test_select_rejects_unknown_session_without_changing_selection(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    session = manager.create(
        name="Known",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    with pytest.raises(KeyError):
        manager.select("missing")

    assert manager.active_session is session


def test_remove_inactive_session_preserves_selection(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    first = manager.create(
        name="First",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    second = manager.create(
        name="Second",
        kind=SessionKind.SHELL,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    assert manager.remove(first.id) is first
    assert manager.sessions == (second,)
    assert manager.active_session is second


def test_remove_active_session_clears_selection(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    first = manager.create(
        name="First",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    second = manager.create(
        name="Second",
        kind=SessionKind.SHELL,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    assert manager.remove(second.id) is second
    assert manager.sessions == (first,)
    assert manager.active_session is None


def test_remove_rejects_unknown_session_without_changing_selection(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    session = manager.create(
        name="Known",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    with pytest.raises(KeyError):
        manager.remove("missing")

    assert manager.sessions == (session,)
    assert manager.active_session is session
