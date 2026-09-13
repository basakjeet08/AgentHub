"""Application shell: Home layout, key bindings, and widget orchestration."""

from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult, SystemCommand
from textual.command import CommandPalette
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import ContentSwitcher

from agenthub.harnesses import FISH, OPENCODE, AgentHarness
from agenthub.sessions import AgentSession, SessionManager
from agenthub.terminal import AgentTerminal
from agenthub.ui import (
    AgentHubStatusBar,
    HomeScreen,
    SessionSidebar,
)
from agenthub.ui.bindings import APPLICATION_BINDINGS, TERMINAL_GATED_ACTIONS


class AgentHubApp(App):
    """Fullscreen AgentHub shell for Home and managed terminal sessions."""

    hub_locked: reactive[bool] = reactive(False, bindings=True)

    CSS_PATH: ClassVar[list[str]] = [
        "ui/theme.tcss",
        "ui/app.tcss",
        "ui/screens/home.tcss",
        "ui/panels/sidebar.tcss",
        "ui/panels/status_bar.tcss",
    ]

    BINDINGS: ClassVar = list(APPLICATION_BINDINGS)

    def __init__(
        self,
        *,
        agent_harness: AgentHarness = OPENCODE,
        shell_harness: AgentHarness = FISH,
    ) -> None:
        """Create the AgentHub shell without launching a coding harness."""

        super().__init__()
        self.theme = "tokyo-night"
        self.session_manager = SessionManager()
        self._agent_harness = agent_harness
        self._shell_harness = shell_harness
        self._shell_session_slots: dict[int, str] = {}

    @property
    def shell_session_slots(self) -> dict[int, str]:
        """Return a copy of the lazy Fish slot mapping."""

        return self._shell_session_slots.copy()

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
                yield SessionSidebar(
                    self._agent_sessions(),
                    shell_sessions=self._shell_sessions(),
                    shortcut_slots=self._shortcut_slots(),
                    id="session-sidebar",
                )
                yield ContentSwitcher(
                    HomeScreen(id="home-screen"),
                    *(session.terminal for session in sessions),
                    initial=initial,
                    id="session-content",
                )
            yield AgentHubStatusBar(
                session_count=len(sessions),
                agent_count=0,
                locked=self.hub_locked,
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
        self.call_after_refresh(self._highlight_active_sidebar)
        self.set_focus(session.terminal)
        return session

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Gate hub-owned keys while an active terminal owns the keyboard."""

        if action == "open_shell" and (
            not parameters or not isinstance(parameters[0], int) or not 1 <= parameters[0] <= 9
        ):
            return False

        terminal_is_active = self.session_manager.active_session is not None
        if self.hub_locked and terminal_is_active and action in TERMINAL_GATED_ACTIONS:
            return False
        return super().check_action(action, parameters)

    def watch_hub_locked(self, locked: bool) -> None:
        """Keep binding metadata and the authoritative status text current."""

        self.refresh_bindings()
        if not self.is_running:
            return
        status_bars = self.query(AgentHubStatusBar).nodes
        if status_bars:
            status_bars[0].update_mode(locked)

    def action_toggle_hub_lock(self) -> None:
        """Transfer navigation-key ownership between AgentHub and the terminal."""

        self.hub_locked = not self.hub_locked
        if not self.hub_locked:
            return

        if isinstance(self.screen, CommandPalette):
            self.screen.dismiss()
        self.call_after_refresh(self._focus_active_terminal)

    async def action_open_shell(self, slot: int) -> None:
        """Open an existing Fish slot or create it lazily."""

        session_id = self._shell_session_slots.get(slot)
        if session_id is not None:
            self.show_session(session_id)
            return

        session = await self._create_and_mount_session(
            name=f"Shell {slot}",
            harness=self._shell_harness,
        )
        self._shell_session_slots[slot] = session.id
        self._refresh_sidebar()
        self.show_session(session.id)

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

    async def action_new_session(self) -> None:
        """Create and display an OpenCode session without configuration UI."""

        agent_number = len(self._agent_sessions()) + 1
        name = self._agent_harness.display_name
        if agent_number > 1:
            name = f"{name} {agent_number}"
        session = await self._create_and_mount_session(
            name=name,
            harness=self._agent_harness,
        )
        self._refresh_sidebar()
        self.show_session(session.id)

    def action_focus_agents(self) -> None:
        """Move keyboard focus to the agent-session list."""

        self.query_one(SessionSidebar).focus_agents()

    def action_focus_shells(self) -> None:
        """Move keyboard focus to the shell-session list."""

        self.query_one(SessionSidebar).focus_shells()

    async def _create_and_mount_session(
        self,
        *,
        name: str,
        harness: AgentHarness,
    ) -> AgentSession:
        """Create one manager-owned session and mount its terminal in the shell."""

        session = self.session_manager.create(
            name=name,
            cwd=Path.cwd(),
            harness=harness,
        )
        session.terminal.id = self._terminal_dom_id(session.id)
        await self.query_one("#session-content", ContentSwitcher).mount(session.terminal)
        self.call_after_refresh(self._refresh_status)
        return session

    def _is_shell_session(self, session_id: str) -> bool:
        """Return whether a session belongs to one of the fixed shell slots."""

        return session_id in self._shell_session_slots.values()

    def _agent_sessions(self) -> tuple[AgentSession, ...]:
        """Return managed coding-agent sessions in creation order."""

        return tuple(
            session
            for session in self.session_manager.sessions
            if not self._is_shell_session(session.id)
        )

    def _shell_sessions(self) -> tuple[AgentSession, ...]:
        """Return Fish sessions in numeric slot order."""

        sessions_by_id = {session.id: session for session in self.session_manager.sessions}
        return tuple(
            sessions_by_id[session_id]
            for _slot, session_id in sorted(self._shell_session_slots.items())
        )

    def _shortcut_slots(self) -> dict[str, int]:
        """Map currently addressable sessions to their reserved shortcuts."""

        return {session_id: slot for slot, session_id in self._shell_session_slots.items()}

    def _refresh_sidebar(self) -> None:
        """Synchronize grouped session presentation with application state."""

        sidebars = self.query(SessionSidebar).nodes
        if not sidebars:
            return
        sidebars[0].update_sessions(
            self._agent_sessions(),
            shell_sessions=self._shell_sessions(),
            shortcut_slots=self._shortcut_slots(),
        )

    def _highlight_active_sidebar(self) -> None:
        """Restore active highlighting after a sidebar recompose."""

        session = self.session_manager.active_session
        sidebars = self.query(SessionSidebar).nodes
        if session is not None and sidebars:
            sidebars[0].set_active(session.id)

    def _focus_active_terminal(self) -> None:
        """Restore active-row context and focus after entering terminal-first mode."""

        session = self.session_manager.active_session
        if session is not None:
            self.query_one(SessionSidebar).set_active(session.id)
            self.set_focus(session.terminal)

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
        running_agents = sum(
            session.terminal.is_process_running for session in self._agent_sessions()
        )
        self.query_one(AgentHubStatusBar).update_state(
            session_count=len(sessions),
            agent_count=running_agents,
            locked=self.hub_locked,
        )

    def _handle_session_process_exited(
        self,
        _session: AgentSession,
        _exit_code: int,
    ) -> None:
        """Preserve single-session exit policy; defer multi-session policy."""

        if len(self.session_manager.sessions) == 1:
            self.exit()
