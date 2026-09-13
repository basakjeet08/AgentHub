"""Persistent application status and compact contextual metrics."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class AgentHubStatusBar(Horizontal):
    """Display real application state without speculative provider metrics."""

    def __init__(
        self,
        *,
        session_count: int = 0,
        agent_count: int = 0,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._session_count = session_count
        self._agent_count = agent_count

    def compose(self) -> ComposeResult:
        """Compose application status and runtime counts."""

        yield Static("●", id="status-indicator")
        yield Static("Ready", id="status-label")
        yield Static(f"Sessions {self._session_count}", id="session-count")
        yield Static(f"Agents {self._agent_count}", id="agent-count")

    def update_state(self, *, session_count: int, agent_count: int) -> None:
        """Refresh status from current AgentHub runtime facts."""

        self._session_count = session_count
        self._agent_count = agent_count
        if not self.is_mounted:
            return

        running = agent_count > 0
        self.query_one("#status-label", Static).update("Running" if running else "Ready")
        self.query_one("#session-count", Static).update(f"Sessions {session_count}")
        self.query_one("#agent-count", Static).update(f"Agents {agent_count}")
