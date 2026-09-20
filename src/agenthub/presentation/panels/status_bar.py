"""Persistent application status and compact contextual metrics."""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

LOCKED_ICON = "●"
UNLOCKED_ICON = "○"


def _mode_content(locked: bool) -> tuple[str, str, str]:
    """Return the icon, label, and action hint for one ownership mode."""

    if locked:
        return LOCKED_ICON, "Locked", "Ctrl+G Unlock"
    return UNLOCKED_ICON, "Unlocked", "Ctrl+G Lock"


class AgentHubStatusBar(Horizontal):
    """Display real application state without speculative provider metrics."""

    def __init__(
        self,
        *,
        session_count: int = 0,
        running_count: int = 0,
        locked: bool = False,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self._session_count = session_count
        self._running_count = running_count
        self.update_mode(locked)

    def compose(self) -> ComposeResult:
        """Compose application status and runtime counts."""

        icon, label, action = _mode_content(self._locked)
        with Horizontal(id="session-metrics"):
            yield Static(f"Sessions {self._session_count}", id="session-count")
            yield Static(f"Running {self._running_count}", id="running-count")
        with Horizontal(id="lock-status"):
            yield Static(icon, id="mode-indicator")
            yield Static(label, id="mode-label")
            yield Static(action, id="mode-action")

    def update_state(
        self,
        *,
        session_count: int,
        running_count: int,
        locked: bool,
    ) -> None:
        """Refresh status from current AgentHub runtime facts."""

        self._session_count = session_count
        self._running_count = running_count
        self.update_mode(locked)
        if not self.is_mounted:
            return

        self.query_one("#session-count", Static).update(f"Sessions {session_count}")
        self.query_one("#running-count", Static).update(f"Running {running_count}")

    def update_mode(self, locked: bool) -> None:
        """Update authoritative keyboard-ownership text and its visual cue."""

        self._locked = locked
        self.set_class(locked, "-locked")
        self.set_class(not locked, "-unlocked")
        if not self.is_mounted:
            return

        icon, label, action = _mode_content(locked)
        self.query_one("#mode-indicator", Static).update(icon)
        self.query_one("#mode-label", Static).update(label)
        self.query_one("#mode-action", Static).update(action)
