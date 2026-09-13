"""Application shell: layout, key bindings, and widget orchestration."""

from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import ContentSwitcher

from agenthub.harnesses import DEFAULT_HARNESS, HARNESSES, AgentHarness
from agenthub.sessions import AgentSession, SessionManager
from agenthub.terminal import AgentTerminal
from agenthub.ui import SessionSidebar


class AgentHubApp(App):
    """Fullscreen Textual host for the currently active managed session."""

    CSS_PATH: ClassVar[list[str]] = [
        "ui/app.tcss",
        "ui/panels/sidebar.tcss",
    ]

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+1", "select_session(0)", "Session 1", priority=True),
        Binding("ctrl+2", "select_session(1)", "Session 2", priority=True),
        Binding("ctrl+q", "quit", "Quit", priority=True),
    ]

    def __init__(
        self,
        harness: AgentHarness | None = None,
        *,
        cwd: Path | None = None,
    ) -> None:
        """Create one initial session using the given or default harness."""

        super().__init__()
        selected_harness = harness or HARNESSES[DEFAULT_HARNESS]
        self.session_manager = SessionManager()
        self.session_manager.create(
            name=selected_harness.display_name,
            cwd=cwd or Path.cwd(),
            harness=selected_harness,
        )

    def compose(self) -> ComposeResult:
        """Mount every managed terminal while displaying only the active one."""

        sessions = self.session_manager.sessions
        active_session = self.session_manager.active_session
        for session in sessions:
            session.terminal.id = self._terminal_dom_id(session.id)

        initial = (
            self._terminal_dom_id(active_session.id)
            if active_session is not None
            else None
        )
        yield Horizontal(
            SessionSidebar(sessions, id="session-sidebar"),
            ContentSwitcher(
                *(session.terminal for session in sessions),
                initial=initial,
                id="session-content",
            ),
        )

    def on_mount(self) -> None:
        """Focus the terminal once mounted so keystrokes reach the agent."""

        session = self.session_manager.active_session
        if session is not None:
            self.show_session(session.id)

    @staticmethod
    def _terminal_dom_id(session_id: str) -> str:
        """Map application identity to Textual identity at the UI boundary."""

        return f"terminal-{session_id}"

    def show_session(self, session_id: str) -> AgentSession:
        """Select, display, and focus one managed session."""

        session = self.session_manager.select(session_id)
        self.query_one("#session-content", ContentSwitcher).current = self._terminal_dom_id(
            session.id
        )
        self.query_one(SessionSidebar).set_active(session.id)
        self.set_focus(session.terminal)
        return session

    def action_select_session(self, index: int) -> None:
        """Select a session by creation-order index when that slot exists."""

        sessions = self.session_manager.sessions
        if 0 <= index < len(sessions):
            self.show_session(sessions[index].id)

    def on_session_sidebar_session_selected(
        self,
        message: SessionSidebar.SessionSelected,
    ) -> None:
        """Route sidebar navigation through the shared switching operation."""

        self.show_session(message.session_id)

    def on_agent_terminal_process_exited(
        self,
        message: AgentTerminal.ProcessExited,
    ) -> None:
        """Resolve terminal exit events to their owning AgentHub session."""

        session = next(
            session
            for session in self.session_manager.sessions
            if session.terminal is message.control
        )
        self._handle_session_process_exited(session, message.exit_code)

    def _handle_session_process_exited(
        self,
        _session: AgentSession,
        _exit_code: int,
    ) -> None:
        """Preserve single-session exit policy; defer multi-session policy."""

        if len(self.session_manager.sessions) == 1:
            self.exit()
