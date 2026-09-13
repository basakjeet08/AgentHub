"""Runtime model for one AgentHub-managed terminal session."""

from dataclasses import dataclass
from pathlib import Path

from agenthub.harnesses import AgentHarness
from agenthub.terminal import AgentTerminal


@dataclass
class AgentSession:
    """AgentHub identity and runtime objects for one hosted CLI process."""

    id: str
    name: str
    cwd: Path
    harness: AgentHarness
    terminal: AgentTerminal
