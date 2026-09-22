"""Lightweight Home orientation and shortcut reference."""

from typing import cast

from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Static

from agenthub.presentation.key_bindings import (
    COMMAND_PALETTE_BINDING,
    FOCUS_SIDEBAR_BINDING,
    RESYNC_SESSIONS_BINDING,
    TOGGLE_HUB_LOCK_BINDING,
)

_GLOBAL_SHORTCUTS = (
    (cast(str, TOGGLE_HUB_LOCK_BINDING.key_display), "Lock / unlock"),
    (cast(str, COMMAND_PALETTE_BINDING.key_display), "Command palette"),
    (cast(str, FOCUS_SIDEBAR_BINDING.key_display), "Focus sidebar"),
    (cast(str, RESYNC_SESSIONS_BINDING.key_display), "Refresh native sessions"),
)

_SIDEBAR_SHORTCUTS = (
    ("← / →", "Change sidebar tab"),
    ("↑ / ↓", "Navigate sessions"),
    ("Enter", "Open / resume"),
)


class HomeScreen(VerticalScroll):
    """Centered landing screen with essential orientation and shortcuts."""

    def compose(self) -> ComposeResult:
        """Compose the static Home landing content."""

        with Vertical(id="home-content"):
            with Horizontal(id="home-heading"):
                yield Static("AgentHub", id="home-title")
                yield Static(
                    "Your agents live here.",
                    id="home-tagline",
                    classes="muted",
                )

            yield Static(
                "Select a session from the sidebar\nor start a new session with Ctrl+P.",
                id="home-orientation",
            )

            with Vertical(id="home-quick-reference", classes="card"):
                yield Static("QUICK REFERENCE", classes="home-reference-title")
                yield Static("GLOBAL", classes="home-reference-group")
                with Grid(classes="home-shortcut-grid"):
                    for key, description in _GLOBAL_SHORTCUTS:
                        yield Static(key, classes="home-shortcut-key")
                        yield Static(description, classes="home-shortcut-description")

                yield Static("SIDEBAR", classes="home-reference-group")
                with Grid(classes="home-shortcut-grid"):
                    for key, description in _SIDEBAR_SHORTCUTS:
                        yield Static(key, classes="home-shortcut-key")
                        yield Static(description, classes="home-shortcut-description")

            yield Static(
                "See [$secondary]README.md[/] for the full usage guide.",
                id="home-readme-hint",
                classes="muted",
            )
