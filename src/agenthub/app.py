"""Application shell: Home layout, key bindings, and widget orchestration."""

from collections.abc import Iterable, Mapping
from functools import partial
from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult, SystemCommand
from textual.command import CommandPalette
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import ContentSwitcher

from agenthub.harnesses import FISH, HARNESSES, AgentHarness
from agenthub.sessions import AgentSession, SessionKind, SessionManager
from agenthub.terminal import AgentTerminal
from agenthub.ui import (
    AgentHubStatusBar,
    HomeScreen,
    SessionSidebar,
)
from agenthub.ui.bindings import APPLICATION_BINDINGS, TERMINAL_GATED_ACTIONS
from agenthub.ui.modals import (
    HarnessSelectionModal,
    SessionNameModal,
    WorkingDirectoryModal,
)

_NEW_SESSION_MODALS = (
    HarnessSelectionModal,
    SessionNameModal,
    WorkingDirectoryModal,
)


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
        agent_harnesses: Mapping[str, AgentHarness] | None = None,
        shell_harness: AgentHarness = FISH,
        working_directory_root: Path | None = None,
    ) -> None:
        """Create the AgentHub shell without launching a coding harness."""

        super().__init__()
        self.theme = "tokyo-night"
        self.session_manager = SessionManager()
        self._agent_harnesses = dict(
            HARNESSES if agent_harnesses is None else agent_harnesses
        )
        self._shell_harness = shell_harness
        self._working_directory_root = (
            Path.home() if working_directory_root is None else working_directory_root
        )
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

        current_screen = self.screen
        terminal_is_active = self.session_manager.active_session is not None
        if isinstance(current_screen, CommandPalette) or (
            terminal_is_active and isinstance(current_screen, ModalScreen)
        ):
            current_screen.dismiss()
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
            kind=SessionKind.SHELL,
            cwd=Path.cwd(),
            shell_slot=slot,
        )
        self._refresh_sidebar()
        if session in self.session_manager.sessions:
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

    def action_new_session(self) -> None:
        """Begin the user-driven New Agent Session modal workflow."""

        if isinstance(self.screen, _NEW_SESSION_MODALS):
            return

        self.push_screen(
            HarnessSelectionModal(self._agent_harnesses.values()),
            self._on_harness_selected,
        )

    def _on_harness_selected(self, harness_id: str | None) -> None:
        """Continue the workflow by prompting for the selected harness's name."""

        if harness_id is None:
            return

        harness = self._agent_harnesses[harness_id]
        self.push_screen(
            SessionNameModal(harness.display_name),
            partial(self._on_session_name_selected, harness),
        )

    def _on_session_name_selected(
        self,
        harness: AgentHarness,
        name: str | None,
    ) -> None:
        """Continue the workflow by prompting for the working directory."""

        if name is None:
            return

        normalized_name = name.strip()
        if not normalized_name:
            return

        self.push_screen(
            WorkingDirectoryModal(root=self._working_directory_root),
            partial(self._on_working_directory_selected, harness, normalized_name),
        )

    async def _on_working_directory_selected(
        self,
        harness: AgentHarness,
        name: str,
        cwd: Path | None,
    ) -> None:
        """Create the runtime only after all three modal stages are confirmed."""

        if cwd is None:
            return

        await self._create_agent_session(
            harness=harness,
            name=name,
            cwd=cwd,
        )

    async def _create_agent_session(
        self,
        *,
        harness: AgentHarness,
        name: str,
        cwd: Path,
    ) -> AgentSession:
        """Apply Agent-session policy around generic runtime creation."""

        session = await self._create_and_mount_session(
            name=name,
            harness=harness,
            kind=SessionKind.AGENT,
            cwd=cwd,
        )
        self._refresh_sidebar()
        if session in self.session_manager.sessions:
            self.show_session(session.id)
        return session

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
        kind: SessionKind,
        cwd: Path,
        shell_slot: int | None = None,
    ) -> AgentSession:
        """Create one manager-owned session and mount its terminal in the shell."""

        previous_session = self.session_manager.active_session
        session = self.session_manager.create(
            name=name,
            kind=kind,
            cwd=cwd,
            harness=harness,
        )
        session.terminal.id = self._terminal_dom_id(session.id)
        if shell_slot is not None:
            self._shell_session_slots[shell_slot] = session.id
        try:
            await self.query_one("#session-content", ContentSwitcher).mount(session.terminal)
        except Exception:
            if shell_slot is not None and self._shell_session_slots.get(shell_slot) == session.id:
                self._shell_session_slots.pop(shell_slot, None)
            if session in self.session_manager.sessions:
                self.session_manager.remove(session.id)
                if previous_session in self.session_manager.sessions:
                    self.session_manager.select(previous_session.id)
            raise
        self.call_after_refresh(self._refresh_status)
        return session

    def _agent_sessions(self) -> tuple[AgentSession, ...]:
        """Return managed coding-agent sessions in creation order."""

        return tuple(
            session
            for session in self.session_manager.sessions
            if session.kind is SessionKind.AGENT
        )

    def _shell_sessions(self) -> tuple[AgentSession, ...]:
        """Return shell sessions with numbered slots first in numeric order."""

        shell_sessions = tuple(
            session
            for session in self.session_manager.sessions
            if session.kind is SessionKind.SHELL
        )
        sessions_by_id = {session.id: session for session in shell_sessions}
        slotted = tuple(
            sessions_by_id[session_id]
            for _slot, session_id in sorted(self._shell_session_slots.items())
            if session_id in sessions_by_id
        )
        slotted_ids = {session.id for session in slotted}
        return slotted + tuple(
            session for session in shell_sessions if session.id not in slotted_ids
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

    async def on_session_sidebar_shell_slot_selected(
        self,
        message: SessionSidebar.ShellSlotSelected,
    ) -> None:
        """Open or create a shell slot selected through the shell sidebar."""

        await self.action_open_shell(message.slot)

    async def on_agent_terminal_process_exited(
        self,
        message: AgentTerminal.ProcessExited,
    ) -> None:
        """Resolve terminal exit events to their owning AgentHub session."""

        session = next(
            (
                session
                for session in self.session_manager.sessions
                if session.terminal is message.control
            ),
            None,
        )
        if session is not None:
            await self._handle_session_process_exited(session, message.exit_code)

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

    async def _handle_session_process_exited(
        self,
        session: AgentSession,
        _exit_code: int,
    ) -> None:
        """Remove an exited runtime and show Home when it was active."""

        await self._remove_exited_session(session)

    async def _remove_exited_session(self, session: AgentSession) -> None:
        """Synchronize process-exit cleanup across manager, DOM, slots, and UI."""

        if session not in self.session_manager.sessions:
            return

        was_active = self.session_manager.active_session is session
        for slot, session_id in tuple(self._shell_session_slots.items()):
            if session_id == session.id:
                del self._shell_session_slots[slot]

        self.session_manager.remove(session.id)
        if was_active:
            self._show_home()

        if session.terminal.is_mounted:
            await session.terminal.remove()

        self._refresh_sidebar()
        self._refresh_status()

    def _show_home(self) -> None:
        """Display and focus Home without changing keyboard-ownership mode."""

        home = self.query_one(HomeScreen)
        home.update_for_sessions(bool(self.session_manager.sessions))
        self.query_one("#session-content", ContentSwitcher).current = "home-screen"
        self.query_one(SessionSidebar).clear_active()
        self.set_focus(home)
