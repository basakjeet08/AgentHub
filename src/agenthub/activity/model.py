"""Provider-neutral activity state and normalized event models."""

from dataclasses import dataclass
from enum import StrEnum


class AgentActivity(StrEnum):
    """Current user-facing activity of one loaded coding Agent."""

    UNKNOWN = "unknown"
    IDLE = "idle"
    WORKING = "working"
    NEEDS_INPUT = "needs_input"
    DONE = "done"


class AgentActivityEventKind(StrEnum):
    """Provider-neutral lifecycle signals understood by the activity reducer."""

    SESSION_STARTED = "session_started"
    PROMPT_SUBMITTED = "prompt_submitted"
    TOOL_STARTED = "tool_started"
    PERMISSION_REQUESTED = "permission_requested"
    INPUT_REQUESTED = "input_requested"
    TOOL_FINISHED = "tool_finished"
    TURN_COMPLETED = "turn_completed"
    INTERRUPTED = "interrupted"
    ATTENTION_ACKNOWLEDGED = "attention_acknowledged"


@dataclass(frozen=True)
class AgentActivityEvent:
    """One normalized activity signal routed by AgentHub session identity."""

    session_id: str
    kind: AgentActivityEventKind | str
    scope_id: str | None = None
