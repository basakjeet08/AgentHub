"""Deterministic transitions for provider-neutral Agent activity."""

from dataclasses import dataclass, replace

from .model import AgentActivity, AgentActivityEvent, AgentActivityEventKind

_MAX_CLOSED_SCOPES = 32
_SCOPED_EVENT_KINDS = {
    AgentActivityEventKind.PROMPT_SUBMITTED,
    AgentActivityEventKind.TOOL_STARTED,
    AgentActivityEventKind.PERMISSION_REQUESTED,
    AgentActivityEventKind.INPUT_REQUESTED,
    AgentActivityEventKind.TOOL_FINISHED,
    AgentActivityEventKind.TURN_COMPLETED,
    AgentActivityEventKind.INTERRUPTED,
}
_TERMINAL_EVENT_KINDS = {
    AgentActivityEventKind.TURN_COMPLETED,
    AgentActivityEventKind.INTERRUPTED,
}

_ACTIVITY_BY_EVENT = {
    AgentActivityEventKind.SESSION_STARTED: AgentActivity.IDLE,
    AgentActivityEventKind.PROMPT_SUBMITTED: AgentActivity.WORKING,
    AgentActivityEventKind.TOOL_STARTED: AgentActivity.WORKING,
    AgentActivityEventKind.PERMISSION_REQUESTED: AgentActivity.NEEDS_INPUT,
    AgentActivityEventKind.INPUT_REQUESTED: AgentActivity.NEEDS_INPUT,
    AgentActivityEventKind.TOOL_FINISHED: AgentActivity.WORKING,
    AgentActivityEventKind.TURN_COMPLETED: AgentActivity.DONE,
    AgentActivityEventKind.INTERRUPTED: AgentActivity.IDLE,
}


@dataclass(frozen=True)
class ActivityReducerState:
    """Activity plus bounded ordering context for asynchronous provider events."""

    activity: AgentActivity = AgentActivity.UNKNOWN
    active_scope_id: str | None = None
    closed_scope_ids: tuple[str, ...] = ()


def reduce_activity(
    current: AgentActivity,
    event: AgentActivityEvent,
) -> AgentActivity:
    """Return the next activity without mutating session or lifecycle state."""

    if event.kind == AgentActivityEventKind.ATTENTION_ACKNOWLEDGED:
        return AgentActivity.IDLE if current is AgentActivity.DONE else current
    if current is AgentActivity.NEEDS_INPUT and event.kind == AgentActivityEventKind.TOOL_STARTED:
        return current
    if current is AgentActivity.DONE and event.kind in {
        AgentActivityEventKind.TOOL_STARTED,
        AgentActivityEventKind.PERMISSION_REQUESTED,
        AgentActivityEventKind.INPUT_REQUESTED,
        AgentActivityEventKind.TOOL_FINISHED,
    }:
        return current
    return _ACTIVITY_BY_EVENT.get(event.kind, current)


def _close_scope(state: ActivityReducerState, scope_id: str) -> ActivityReducerState:
    """Remember a completed or superseded scope within a small bounded history."""

    closed = tuple(item for item in state.closed_scope_ids if item != scope_id)
    closed = (*closed, scope_id)[-_MAX_CLOSED_SCOPES:]
    return replace(state, closed_scope_ids=closed)


def reduce_activity_state(
    state: ActivityReducerState,
    event: AgentActivityEvent,
) -> ActivityReducerState:
    """Apply activity while rejecting late events from closed provider scopes."""

    scope_id = event.scope_id
    if (
        not isinstance(scope_id, str)
        or not scope_id
        or event.kind not in _SCOPED_EVENT_KINDS
    ):
        return replace(state, activity=reduce_activity(state.activity, event))

    if scope_id in state.closed_scope_ids:
        return state

    if scope_id != state.active_scope_id:
        if state.active_scope_id is not None:
            state = _close_scope(state, state.active_scope_id)
        state = replace(
            state,
            activity=AgentActivity.UNKNOWN,
            active_scope_id=scope_id,
        )
    elif (
        state.activity is AgentActivity.NEEDS_INPUT
        and event.kind == AgentActivityEventKind.PROMPT_SUBMITTED
    ):
        return state

    state = replace(state, activity=reduce_activity(state.activity, event))
    if event.kind in _TERMINAL_EVENT_KINDS:
        state = _close_scope(state, scope_id)
    return state
