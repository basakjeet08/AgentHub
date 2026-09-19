"""Tests for provider-neutral Agent activity state and routing."""

from pathlib import Path

import pytest

from agenthub.activity import (
    ActivityReducerState,
    AgentActivity,
    AgentActivityEvent,
    AgentActivityEventKind,
    reduce_activity,
    reduce_activity_state,
)
from agenthub.native_sessions import NativeSession
from agenthub.sessions import SessionKind, SessionManager, SessionState


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (AgentActivityEventKind.SESSION_STARTED, AgentActivity.IDLE),
        (AgentActivityEventKind.PROMPT_SUBMITTED, AgentActivity.WORKING),
        (AgentActivityEventKind.TOOL_STARTED, AgentActivity.WORKING),
        (AgentActivityEventKind.PERMISSION_REQUESTED, AgentActivity.NEEDS_INPUT),
        (AgentActivityEventKind.INPUT_REQUESTED, AgentActivity.NEEDS_INPUT),
        (AgentActivityEventKind.TOOL_FINISHED, AgentActivity.WORKING),
        (AgentActivityEventKind.TURN_STOP_REQUESTED, AgentActivity.DONE),
        (AgentActivityEventKind.TURN_COMPLETED, AgentActivity.DONE),
        (AgentActivityEventKind.INTERRUPTED, AgentActivity.IDLE),
    ],
)
def test_reducer_maps_normalized_events(
    kind: AgentActivityEventKind,
    expected: AgentActivity,
) -> None:
    event = AgentActivityEvent("session-1", kind)

    assert reduce_activity(AgentActivity.UNKNOWN, event) is expected


def test_attention_acknowledgement_clears_only_done() -> None:
    event = AgentActivityEvent(
        "session-1",
        AgentActivityEventKind.ATTENTION_ACKNOWLEDGED,
    )

    assert reduce_activity(AgentActivity.DONE, event) is AgentActivity.IDLE
    assert reduce_activity(AgentActivity.WORKING, event) is AgentActivity.WORKING


def test_unknown_event_leaves_activity_unchanged() -> None:
    event = AgentActivityEvent("session-1", "future_provider_event")

    assert reduce_activity(AgentActivity.WORKING, event) is AgentActivity.WORKING


def test_late_tool_events_do_not_overwrite_attention_states() -> None:
    tool_started = AgentActivityEvent(
        "session-1",
        AgentActivityEventKind.TOOL_STARTED,
    )
    tool_finished = AgentActivityEvent(
        "session-1",
        AgentActivityEventKind.TOOL_FINISHED,
    )
    input_requested = AgentActivityEvent(
        "session-1",
        AgentActivityEventKind.INPUT_REQUESTED,
    )

    assert reduce_activity(AgentActivity.NEEDS_INPUT, tool_started) is AgentActivity.NEEDS_INPUT
    assert reduce_activity(AgentActivity.DONE, tool_started) is AgentActivity.DONE
    assert reduce_activity(AgentActivity.DONE, tool_finished) is AgentActivity.DONE
    assert reduce_activity(AgentActivity.DONE, input_requested) is AgentActivity.DONE


@pytest.mark.parametrize(
    ("terminal_kind", "expected"),
    [
        (AgentActivityEventKind.TURN_COMPLETED, AgentActivity.DONE),
        (AgentActivityEventKind.INTERRUPTED, AgentActivity.IDLE),
    ],
)
@pytest.mark.parametrize(
    "request_kind",
    [
        AgentActivityEventKind.PERMISSION_REQUESTED,
        AgentActivityEventKind.INPUT_REQUESTED,
    ],
)
def test_closed_scope_rejects_late_input_event(
    terminal_kind: AgentActivityEventKind,
    expected: AgentActivity,
    request_kind: AgentActivityEventKind,
) -> None:
    state = ActivityReducerState()
    state = reduce_activity_state(
        state,
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.PROMPT_SUBMITTED,
            scope_id="turn-a",
        ),
    )
    state = reduce_activity_state(
        state,
        AgentActivityEvent(
            "session-1",
            terminal_kind,
            scope_id="turn-a",
        ),
    )

    state = reduce_activity_state(
        state,
        AgentActivityEvent(
            "session-1",
            request_kind,
            scope_id="turn-a",
        ),
    )

    assert state.activity is expected


def test_new_scope_rejects_late_completion_from_previous_scope() -> None:
    state = reduce_activity_state(
        ActivityReducerState(),
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.PROMPT_SUBMITTED,
            scope_id="turn-a",
        ),
    )
    state = reduce_activity_state(
        state,
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.PROMPT_SUBMITTED,
            scope_id="turn-b",
        ),
    )

    state = reduce_activity_state(
        state,
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.TURN_COMPLETED,
            scope_id="turn-a",
        ),
    )

    assert state.activity is AgentActivity.WORKING
    assert state.active_scope_id == "turn-b"


def test_completion_that_arrives_before_its_prompt_remains_terminal() -> None:
    state = reduce_activity_state(
        ActivityReducerState(),
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.TURN_COMPLETED,
            scope_id="turn-a",
        ),
    )

    state = reduce_activity_state(
        state,
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.PROMPT_SUBMITTED,
            scope_id="turn-a",
        ),
    )

    assert state.activity is AgentActivity.DONE


def test_provisional_stop_allows_same_scope_to_resume_working() -> None:
    state = reduce_activity_state(
        ActivityReducerState(),
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.PROMPT_SUBMITTED,
            scope_id="turn-a",
        ),
    )
    state = reduce_activity_state(
        state,
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.TURN_STOP_REQUESTED,
            scope_id="turn-a",
        ),
    )

    state = reduce_activity_state(
        state,
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.TOOL_STARTED,
            scope_id="turn-a",
        ),
    )

    assert state.activity is AgentActivity.WORKING
    assert state.active_scope_id == "turn-a"
    assert "turn-a" not in state.closed_scope_ids


def test_superseded_provisional_stop_scope_rejects_late_work() -> None:
    state = reduce_activity_state(
        ActivityReducerState(),
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.TURN_STOP_REQUESTED,
            scope_id="turn-a",
        ),
    )
    state = reduce_activity_state(
        state,
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.PROMPT_SUBMITTED,
            scope_id="turn-b",
        ),
    )

    state = reduce_activity_state(
        state,
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.TOOL_STARTED,
            scope_id="turn-a",
        ),
    )

    assert state.activity is AgentActivity.WORKING
    assert state.active_scope_id == "turn-b"


def test_unscoped_observed_interruption_closes_the_active_scope() -> None:
    state = reduce_activity_state(
        ActivityReducerState(),
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.PROMPT_SUBMITTED,
            scope_id="turn-a",
        ),
    )

    state = reduce_activity_state(
        state,
        AgentActivityEvent("session-1", AgentActivityEventKind.INTERRUPTED),
    )
    state = reduce_activity_state(
        state,
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.TOOL_FINISHED,
            scope_id="turn-a",
        ),
    )

    assert state.activity is AgentActivity.IDLE
    assert "turn-a" in state.closed_scope_ids


def test_permission_that_arrives_before_its_prompt_remains_needs_input() -> None:
    state = reduce_activity_state(
        ActivityReducerState(activity=AgentActivity.DONE),
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.PERMISSION_REQUESTED,
            scope_id="turn-b",
        ),
    )

    state = reduce_activity_state(
        state,
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.PROMPT_SUBMITTED,
            scope_id="turn-b",
        ),
    )

    assert state.activity is AgentActivity.NEEDS_INPUT


def test_unknown_scoped_event_does_not_replace_the_active_scope() -> None:
    state = reduce_activity_state(
        ActivityReducerState(),
        AgentActivityEvent(
            "session-1",
            AgentActivityEventKind.PROMPT_SUBMITTED,
            scope_id="turn-a",
        ),
    )

    state = reduce_activity_state(
        state,
        AgentActivityEvent("session-1", "future_event", scope_id="turn-b"),
    )

    assert state.activity is AgentActivity.WORKING
    assert state.active_scope_id == "turn-a"


def test_manager_routes_activity_to_exact_loaded_agent(
    sleeping_harness,
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
    lifecycle_states = (first.state, second.state)

    changed = manager.apply_activity_event(
        AgentActivityEvent(first.id, AgentActivityEventKind.PROMPT_SUBMITTED)
    )

    assert changed is True
    assert first.activity is AgentActivity.WORKING
    assert second.activity is AgentActivity.UNKNOWN
    assert (first.state, second.state) == lifecycle_states


def test_manager_retains_scope_change_when_visible_activity_is_unchanged(
    sleeping_harness,
) -> None:
    manager = SessionManager()
    session = manager.create(
        name="Agent",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    manager.apply_activity_event(
        AgentActivityEvent(
            session.id,
            AgentActivityEventKind.PROMPT_SUBMITTED,
            scope_id="turn-a",
        )
    )

    assert (
        manager.apply_activity_event(
            AgentActivityEvent(
                session.id,
                AgentActivityEventKind.PROMPT_SUBMITTED,
                scope_id="turn-b",
            )
        )
        is False
    )
    assert (
        manager.apply_activity_event(
            AgentActivityEvent(
                session.id,
                AgentActivityEventKind.TURN_COMPLETED,
                scope_id="turn-a",
            )
        )
        is False
    )
    assert session.activity is AgentActivity.WORKING


def test_manager_reports_unchanged_and_unknown_events_without_raising(
    sleeping_harness,
) -> None:
    manager = SessionManager()
    session = manager.create(
        name="Agent",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    assert (
        manager.apply_activity_event(AgentActivityEvent(session.id, "future_provider_event"))
        is False
    )
    assert (
        manager.apply_activity_event(
            AgentActivityEvent("missing", AgentActivityEventKind.SESSION_STARTED)
        )
        is False
    )
    assert session.activity is AgentActivity.UNKNOWN


def test_manager_ignores_activity_for_shells_and_unloaded_agents(
    sleeping_harness,
) -> None:
    manager = SessionManager()
    shell = manager.create(
        name="Shell",
        kind=SessionKind.SHELL,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    unloaded = manager.add_discovered(
        native_session=NativeSession(
            harness_id=sleeping_harness.id,
            native_session_id="native-1",
            name="Unloaded",
            cwd=Path.cwd(),
        ),
        harness=sleeping_harness,
    )

    event_kind = AgentActivityEventKind.PROMPT_SUBMITTED
    assert manager.apply_activity_event(AgentActivityEvent(shell.id, event_kind)) is False
    assert manager.apply_activity_event(AgentActivityEvent(unloaded.id, event_kind)) is False
    assert shell.activity is AgentActivity.UNKNOWN
    assert unloaded.activity is AgentActivity.UNKNOWN


def test_detaching_runtime_resets_activity_to_unknown(sleeping_harness) -> None:
    manager = SessionManager()
    session = manager.create(
        name="Agent",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    terminal = session.terminal
    manager.apply_activity_event(
        AgentActivityEvent(
            session.id,
            AgentActivityEventKind.TURN_COMPLETED,
            scope_id="turn-a",
        )
    )

    assert manager.detach_terminal(session.id) is terminal
    assert session.activity is AgentActivity.UNKNOWN
    assert session.state is SessionState.UNLOADED

    assert terminal is not None
    manager.attach_terminal(session.id, terminal)
    assert manager.apply_activity_event(
        AgentActivityEvent(
            session.id,
            AgentActivityEventKind.PROMPT_SUBMITTED,
            scope_id="turn-a",
        )
    )
    assert session.activity is AgentActivity.WORKING


def test_native_deletion_resets_activity_to_unknown(sleeping_harness) -> None:
    manager = SessionManager()
    session = manager.create(
        name="Agent",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    session.native_session_id = "native-1"
    manager.apply_activity_event(
        AgentActivityEvent(session.id, AgentActivityEventKind.PERMISSION_REQUESTED)
    )

    manager.begin_native_deletion(session.id)

    assert session.activity is AgentActivity.UNKNOWN
    assert session.state is SessionState.DELETING
