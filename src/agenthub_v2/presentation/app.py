"""Textual Application Entry Point."""

from pathlib import PurePath
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import BindingType
from textual.containers import Horizontal

from agenthub_v2.session import SessionController

from .key_bindings import APPLICATION_BINDINGS
from .views import HomeView


class AgentHubApp(App[None]):
    """Main entrypoint for textual app."""

    CSS_PATH: ClassVar[list[str | PurePath]] = [
        "./styles/theme.tcss",
        "./styles/app.tcss",
        "./styles/views/home.tcss",
    ]

    BINDINGS: ClassVar[list[BindingType]] = list(APPLICATION_BINDINGS)

    def __init__(self, *, session_controller: SessionController | None = None) -> None:
        """Initialize textual app."""

        super().__init__()

        self.theme = "monokai"
        self._session_controller = (
            session_controller if session_controller is not None else SessionController()
        )

    def compose(self) -> ComposeResult:
        """Build the main textual app content."""

        with Horizontal(id="application-body"):
            yield HomeView()

    def action_hub_lock(self) -> None:
        """Triggers when the user presses Ctrl + G."""

        self.notify("AgentHub Lock Mode is not yet implemented.")

    def action_refresh_sessions(self) -> None:
        """Triggers when the user presses Ctrl + Shift + R."""

        self.notify("AgentHub Refresh Session is not yet implemented.")

    def action_focus_sidebar(self) -> None:
        """Triggers when the user presses Ctrl + S."""

        self.notify("AgentHub Focus Sidebar is not yet implemented.")
