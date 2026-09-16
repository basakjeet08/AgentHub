"""Runtime model for one AgentHub-managed terminal session."""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from agenthub.harnesses import AgentHarness
from agenthub.terminal import AgentTerminal


class SessionKind(StrEnum):
    """Semantic category of one AgentHub-managed terminal session."""

    AGENT = "agent"
    SHELL = "shell"


class SessionState(StrEnum):
    """Transient lifecycle state for an in-memory logical session."""

    UNLOADED = "unloaded"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    DELETING = "deleting"
    ERROR = "error"


@dataclass
class AgentSession:
    """In-memory identity and optional runtime for one hosted conversation."""

    id: str
    name: str
    kind: SessionKind
    cwd: Path | None
    harness: AgentHarness
    terminal: AgentTerminal | None
    native_session_id: str | None = None
    state: SessionState = SessionState.RUNNING
