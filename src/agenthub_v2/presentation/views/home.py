"""Lightweight Home orientation and shortcut reference."""

from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Static

from agenthub_v2.presentation.key_bindings import (
    COMMAND_PALETTE_BINDING,
    FOCUS_SIDEBAR_BINDING,
    HUB_LOCK_BINDING,
    REFRESH_SESSIONS_BINDING,
    SIDEBAR_NEXT_SESSION_BINDING,
    SIDEBAR_NEXT_TAB_BINDING,
    SIDEBAR_OPEN_SESSION_BINDING,
    SIDEBAR_PREVIOUS_SESSION_BINDING,
    SIDEBAR_PREVIOUS_TAB_BINDING,
    binding_key,
)

_GLOBAL_SHORTCUTS = (
    (binding_key(HUB_LOCK_BINDING), "Lock / unlock"),
    (binding_key(COMMAND_PALETTE_BINDING), "Command palette"),
    (binding_key(FOCUS_SIDEBAR_BINDING), "Focus sidebar"),
    (binding_key(REFRESH_SESSIONS_BINDING), "Refresh sessions"),
)

_SIDEBAR_SHORTCUTS = (
    (
        (f"{binding_key(SIDEBAR_PREVIOUS_TAB_BINDING)} / {binding_key(SIDEBAR_NEXT_TAB_BINDING)}"),
        "Change sidebar tab",
    ),
    (
        (
            f"{binding_key(SIDEBAR_PREVIOUS_SESSION_BINDING)} / "
            f"{binding_key(SIDEBAR_NEXT_SESSION_BINDING)}"
        ),
        "Navigate sessions",
    ),
    (binding_key(SIDEBAR_OPEN_SESSION_BINDING), "Open / resume"),
)


class HomeView(VerticalScroll):
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
                f"Select a session from the sidebar\n"
                f"or start a new session with "
                f"[$secondary]{binding_key(COMMAND_PALETTE_BINDING)}[/].",
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
