"""Textual Application Entry Point."""

from pathlib import PurePath
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from agenthub_v2.session import SessionController


class AgentHubApp(App[None]):
    """Main entrypoint for textual app."""

    CSS_PATH: ClassVar[list[str | PurePath]] = [
        "./styles/theme.tcss",
        "./styles/app.tcss",
    ]

    def __init__(self, *, session_controller: SessionController | None = None):
        """Initialize textual app."""

        super().__init__()

        self.theme = "monokai"
        self._session_controller = (
            session_controller if session_controller is not None else SessionController()
        )

    def compose(self) -> ComposeResult:
        """Build the main textual app content."""

        with Horizontal(id="application-body"):
            yield Static("AgentHub", id="home-title")
