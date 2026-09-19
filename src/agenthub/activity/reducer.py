"""Deterministic transitions for provider-neutral Agent activity."""

from .model import AgentActivity, AgentActivityEvent, AgentActivityEventKind

_ACTIVITY_BY_EVENT = {
    AgentActivityEventKind.SESSION_STARTED: AgentActivity.IDLE,
    AgentActivityEventKind.PROMPT_SUBMITTED: AgentActivity.WORKING,
    AgentActivityEventKind.TOOL_STARTED: AgentActivity.WORKING,
    AgentActivityEventKind.PERMISSION_REQUESTED: AgentActivity.NEEDS_INPUT,
    AgentActivityEventKind.TOOL_FINISHED: AgentActivity.WORKING,
    AgentActivityEventKind.TURN_COMPLETED: AgentActivity.DONE,
    AgentActivityEventKind.INTERRUPTED: AgentActivity.IDLE,
}


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
        AgentActivityEventKind.TOOL_FINISHED,
    }:
        return current
    return _ACTIVITY_BY_EVENT.get(event.kind, current)
