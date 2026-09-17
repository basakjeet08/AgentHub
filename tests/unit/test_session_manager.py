"""Tests for logical session creation and selection."""

from dataclasses import replace
from pathlib import Path

import pytest

from agenthub.harnesses import AgentHarness
from agenthub.native_sessions import NativeSession
from agenthub.sessions import SessionKind, SessionManager, SessionState
from agenthub.terminal import AgentTerminal


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


def test_reconcile_discovered_updates_metadata_and_removes_only_stale_unloaded(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    manager = SessionManager()
    stale = manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "stale-native",
            "Stale",
            tmp_path,
        ),
        harness=sleeping_harness,
    )
    running = manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "running-native",
            "Running",
            tmp_path,
        ),
        harness=sleeping_harness,
    )
    manager.attach_terminal(
        running.id,
        AgentTerminal(sleeping_harness, working_directory=tmp_path),
    )
    renamed_cwd = tmp_path / "renamed"

    reconciled = manager.reconcile_discovered(
        native_sessions=(
            NativeSession(
                sleeping_harness.id,
                "running-native",
                "Renamed",
                renamed_cwd,
            ),
            NativeSession(
                sleeping_harness.id,
                "new-native",
                "New",
                tmp_path,
            ),
        ),
        harness=sleeping_harness,
    )

    assert stale not in manager.sessions
    assert manager.sessions == (running, reconciled[1])
    assert reconciled[0] is running
    assert running.name == "Renamed"
    assert running.cwd == renamed_cwd
    assert running.terminal is not None
    assert running.state is SessionState.RUNNING


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


def test_native_deletion_transitions_detach_and_preserve_identity_on_failure(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    session = manager.create(
        name="Native",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    session.native_session_id = "native-1"
    terminal = session.terminal

    assert manager.begin_native_deletion(session.id) is terminal
    assert session.terminal is None
    assert session.state is SessionState.DELETING
    assert session.native_session_id == "native-1"
    assert manager.active_session is None

    assert manager.fail_native_deletion(session.id) is session
    assert session.state is SessionState.UNLOADED
    assert session.native_session_id == "native-1"
    assert manager.sessions == (session,)


def test_native_deletion_removes_row_only_from_deleting_state(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    session = manager.create(
        name="Native",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    session.native_session_id = "native-1"

    with pytest.raises(ValueError, match="not being deleted"):
        manager.complete_native_deletion(session.id)

    manager.begin_native_deletion(session.id)
    assert manager.complete_native_deletion(session.id) is session
    assert manager.sessions == ()


def test_native_deletion_rejects_fresh_agents_and_shells(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    fresh = manager.create(
        name="Fresh",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    shell = manager.create(
        name="Shell",
        kind=SessionKind.SHELL,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    shell.native_session_id = "not-eligible"

    with pytest.raises(ValueError, match="not a native-backed Agent"):
        manager.begin_native_deletion(fresh.id)
    with pytest.raises(ValueError, match="not a native-backed Agent"):
        manager.begin_native_deletion(shell.id)


def test_linkable_native_sessions_filters_to_unique_unloaded_same_harness_agents(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    manager = SessionManager()
    pending = manager.create(
        name="New session",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=sleeping_harness,
    )
    eligible = manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "native-eligible",
            "Eligible",
            tmp_path,
        ),
        harness=sleeping_harness,
    )
    other_directory = tmp_path / "other"
    manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "native-other-directory",
            "Other directory",
            other_directory,
        ),
        harness=sleeping_harness,
    )
    running = manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "native-running",
            "Already running",
            tmp_path,
        ),
        harness=sleeping_harness,
    )
    manager.attach_terminal(
        running.id,
        AgentTerminal(sleeping_harness, working_directory=tmp_path),
    )
    other_harness = replace(sleeping_harness, id="other-harness")
    manager.add_discovered(
        native_session=NativeSession(
            other_harness.id,
            "native-other",
            "Other harness",
            tmp_path,
        ),
        harness=other_harness,
    )
    shell = manager.create(
        name="Shell",
        kind=SessionKind.SHELL,
        cwd=tmp_path,
        harness=sleeping_harness,
    )
    shell.native_session_id = "native-shell"
    manager.select(pending.id)

    assert manager.linkable_native_sessions(pending.id) == (eligible,)


def test_link_native_session_preserves_runtime_and_adopts_provider_metadata(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    manager = SessionManager()
    launch_cwd = tmp_path / "launch"
    launch_cwd.mkdir()
    pending = manager.create(
        name="New session",
        kind=SessionKind.AGENT,
        cwd=launch_cwd,
        harness=sleeping_harness,
    )
    terminal = pending.terminal
    pending_id = pending.id
    candidate = manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "native-123456789",
            "Provider title",
            launch_cwd / ".." / "launch",
        ),
        harness=sleeping_harness,
    )

    linked = manager.link_native_session(pending.id, candidate.id)

    assert linked is pending
    assert linked.id == pending_id
    assert linked.native_session_id == "native-123456789"
    assert linked.name == "Provider title"
    assert linked.cwd == launch_cwd
    assert linked.terminal is terminal
    assert terminal is not None
    assert terminal.working_directory == launch_cwd
    assert linked.state is SessionState.RUNNING
    assert manager.sessions == (linked,)
    assert manager.active_session is linked


def test_link_native_session_preserves_a_different_active_session(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    manager = SessionManager()
    pending = manager.create(
        name="New session",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=sleeping_harness,
    )
    candidate = manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "native-1",
            "Provider title",
            tmp_path,
        ),
        harness=sleeping_harness,
    )
    other = manager.create(
        name="Other",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=sleeping_harness,
    )

    terminal = pending.terminal
    linked = manager.link_native_session(pending.id, candidate.id)

    assert linked is pending
    assert manager.sessions == (pending, other)
    assert manager.active_session is other
    assert pending.native_session_id == "native-1"
    assert pending.name == "Provider title"
    assert pending.terminal is terminal


def test_link_native_session_revalidates_without_partial_mutation(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    manager = SessionManager()
    pending = manager.create(
        name="New session",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=sleeping_harness,
    )
    candidate = manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "native-1",
            "Provider title",
            tmp_path,
        ),
        harness=sleeping_harness,
    )

    candidate.state = SessionState.STARTING
    with pytest.raises(ValueError, match="safe link target"):
        manager.link_native_session(pending.id, candidate.id)

    assert manager.sessions == (pending, candidate)
    assert pending.native_session_id is None
