"""Neutral Home presentation for empty or temporarily unselected sessions."""

from textual.app import ComposeResult
from textual.containers import Center, Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Label, Static

from agenthub.ui.bindings import HOME_SHORTCUTS

_EMPTY_COPY = "No sessions yet. Start your first\ncoding-agent session."
_SESSIONS_COPY = "Select a session from the sidebar\nor start a new coding-agent session."


class HomeScreen(VerticalScroll):
    """Polished landing state with focused application-level guidance."""

    def compose(self) -> ComposeResult:
        """Compose centered session guidance and a compact shortcut reference."""

        with Vertical(id="home-content"):
            with Horizontal(id="home-heading"):
                yield Static("AgentHub", id="home-title")
                yield Static(
                    "Your agents live here.",
                    id="home-tagline",
                    classes="muted",
                )
            yield Static(_EMPTY_COPY, id="home-empty-copy")
            with (
                Center(id="shortcuts-card-container"),
                Vertical(id="shortcuts-card", classes="card"),
            ):
                yield Static("⌨  Shortcuts", classes="section-title")
                with Grid(id="shortcut-grid"):
                    for key_display, description in HOME_SHORTCUTS:
                        yield Label(
                            key_display,
                            classes="shortcut-key",
                        )
                        yield Label(
                            description,
                            classes="shortcut-description",
                        )
                yield Static(
                    "Hub shortcuts require Unlocked mode while a terminal is active.",
                    id="shortcut-mode-note",
                    classes="muted",
                )
                yield Static(
                    "Note: To quit AgentHub, press Ctrl+P and select Quit AgentHub.",
                    id="shortcut-quit-note",
                )

    def update_for_sessions(self, has_sessions: bool) -> None:
        """Keep Home guidance accurate when live sessions remain available."""

        if self.is_mounted:
            self.query_one("#home-empty-copy", Static).update(
                _SESSIONS_COPY if has_sessions else _EMPTY_COPY
            )
