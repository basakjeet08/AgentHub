"""Application shell: Home layout, key bindings, and widget orchestration."""

from collections.abc import Iterable
from typing import ClassVar

from textual.app import App, ComposeResult, SystemCommand
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import ContentSwitcher

from agenthub.sessions import AgentSession, SessionManager
from agenthub.terminal import AgentTerminal
from agenthub.ui import (
    AgentHubStatusBar,
    HomeScreen,
    SessionSidebar,
)
from agenthub.ui.bindings import APPLICATION_BINDINGS


class AgentHubApp(App):
    """Fullscreen AgentHub shell for Home and managed terminal sessions."""

    CSS_PATH: ClassVar[list[str]] = [
        "ui/theme.tcss",
        "ui/app.tcss",
        "ui/screens/home.tcss",
        "ui/panels/sidebar.tcss",
        "ui/panels/status_bar.tcss",
    ]

    BINDINGS: ClassVar = list(APPLICATION_BINDINGS)

    def __init__(self) -> None:
        """Create the AgentHub shell without launching a coding harness."""

        super().__init__()
        self.theme = "tokyo-night"
        self.session_manager = SessionManager()

    def compose(self) -> ComposeResult:
        """Compose persistent application chrome and the current main content."""

        sessions = self.session_manager.sessions
        active_session = self.session_manager.active_session
        for session in sessions:
            session.terminal.id = self._terminal_dom_id(session.id)

        initial = (
            self._terminal_dom_id(active_session.id)
            if active_session is not None
            else "home-screen"
        )
        with Vertical(id="app-shell"):
            with Horizontal(id="application-body"):
                yield SessionSidebar(sessions, id="session-sidebar")
                yield ContentSwitcher(
                    HomeScreen(id="home-screen"),
                    *(session.terminal for session in sessions),
                    initial=initial,
                    id="session-content",
                )
            yield AgentHubStatusBar(
                session_count=len(sessions),
                agent_count=0,
                id="status-bar",
            )

    def on_mount(self) -> None:
        """Focus the terminal once mounted so keystrokes reach the agent."""

        session = self.session_manager.active_session
        if session is not None:
            self.show_session(session.id)
        else:
            self.query_one(HomeScreen).focus()
        self.call_after_refresh(self._refresh_status)

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

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        """Expose Textual's Keys command using AgentHub product language."""

        for command in super().get_system_commands(screen):
            if command.title == "Keys":
                yield SystemCommand(
                    "Shortcuts",
                    command.help,
                    command.callback,
                    command.discover,
                )
            else:
                yield command

    def action_new_session(self) -> None:
        """Acknowledge session intent while creation remains deliberately deferred."""

        self.notify("Session creation is coming in the next phase.", title="New Session")

    def action_focus_sidebar(self) -> None:
        """Move keyboard focus to the sidebar's most useful control."""

        self.query_one(SessionSidebar).focus_primary()

    def action_focus_workspace(self) -> None:
        """Move focus to the active terminal or the Home primary action."""

        session = self.session_manager.active_session
        if session is not None:
            self.set_focus(session.terminal)
        else:
            self.query_one(HomeScreen).focus()

    def on_session_sidebar_new_session_requested(
        self,
        _message: SessionSidebar.NewSessionRequested,
    ) -> None:
        """Route sidebar intent through the same application-owned action."""

        self.action_new_session()

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
        self._refresh_status()

    def _refresh_status(self) -> None:
        """Update the status bar using only current runtime facts."""

        sessions = self.session_manager.sessions
        running_agents = sum(session.terminal.is_process_running for session in sessions)
        self.query_one(AgentHubStatusBar).update_state(
            session_count=len(sessions),
            agent_count=running_agents,
        )

    def _handle_session_process_exited(
        self,
        _session: AgentSession,
        _exit_code: int,
    ) -> None:
        """Preserve single-session exit policy; defer multi-session policy."""

        if len(self.session_manager.sessions) == 1:
            self.exit()
