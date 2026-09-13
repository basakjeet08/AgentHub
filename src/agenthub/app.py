"""Application shell: layout, key bindings, and widget orchestration."""

from pathlib import Path
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding

from agenthub.harnesses import DEFAULT_HARNESS, HARNESSES, AgentHarness
from agenthub.sessions import SessionManager
from agenthub.terminal import AgentTerminal


class AgentHubApp(App):
    """Fullscreen Textual host for the currently active managed session."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+q", "quit", "Quit", priority=True)
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
        """Mount the active session's terminal in the Textual DOM."""

        session = self.session_manager.active_session
        if session is not None:
            yield session.terminal

    def on_mount(self) -> None:
        """Focus the terminal once mounted so keystrokes reach the agent."""

        session = self.session_manager.active_session
        if session is not None:
            self.set_focus(session.terminal)

    def on_terminal_process_exited(
        self,
        _message: AgentTerminal.ProcessExited,
    ) -> None:
        """Quit the app when the agent process exits."""

        self.exit()
