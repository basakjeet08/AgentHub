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


@dataclass
class AgentSession:
    """AgentHub identity and runtime objects for one hosted CLI process."""

    id: str
    name: str
    kind: SessionKind
    cwd: Path
    harness: AgentHarness
    terminal: AgentTerminal
