"""Neutral Home presentation shown when AgentHub has no sessions."""

from textual.app import ComposeResult
from textual.containers import Center, Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Label, Static

from agenthub.ui.bindings import HOME_SHORTCUTS


class HomeScreen(VerticalScroll):
    """Polished empty state with focused application-level guidance."""

    def compose(self) -> ComposeResult:
        """Compose the centered empty state and compact shortcut reference."""

        with Vertical(id="home-content"):
            with Horizontal(id="home-heading"):
                yield Static("AgentHub", id="home-title")
                yield Static(
                    "Your agents live here.",
                    id="home-tagline",
                    classes="muted",
                )
            yield Static(
                "No sessions yet. Start your first\ncoding-agent session.",
                id="home-empty-copy",
            )
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
