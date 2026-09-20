"""Lightweight Home orientation and shortcut reference."""

from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Static

from agenthub.presentation.key_bindings import (
    COMMAND_PALETTE_BINDING,
    FOCUS_SIDEBAR_BINDING,
    RESYNC_SESSIONS_BINDING,
    TOGGLE_HUB_LOCK_BINDING,
)


def _display_key(binding_key: str | None, fallback: str) -> str:
    """Return a binding's display label with its configured key as fallback."""

    return binding_key or fallback


_GLOBAL_SHORTCUTS = (
    (
        _display_key(COMMAND_PALETTE_BINDING.key_display, COMMAND_PALETTE_BINDING.key),
        "Command palette",
    ),
    (
        _display_key(FOCUS_SIDEBAR_BINDING.key_display, FOCUS_SIDEBAR_BINDING.key),
        "Focus sidebar",
    ),
    (
        _display_key(TOGGLE_HUB_LOCK_BINDING.key_display, TOGGLE_HUB_LOCK_BINDING.key),
        "Lock / unlock",
    ),
    (
        _display_key(RESYNC_SESSIONS_BINDING.key_display, RESYNC_SESSIONS_BINDING.key),
        "Refresh native sessions",
    ),
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
