"""Central catalog of AgentHub's static Textual key bindings."""

from typing import cast

from textual.binding import Binding

HUB_LOCK_BINDING = Binding(
    "ctrl+g",
    "hub_lock",
    "Lock / unlock AgentHub",
    key_display="Ctrl + G",
    priority=True,
)

COMMAND_PALETTE_BINDING = Binding(
    "ctrl+p",
    "command_palette",
    "Command palette",
    key_display="Ctrl + P",
    priority=True,
)

REFRESH_SESSIONS_BINDING = Binding(
    "ctrl+shift+r",
    "refresh_sessions",
    "Refresh sessions",
    key_display="Ctrl + Shift + R",
    priority=True,
)

FOCUS_SIDEBAR_BINDING = Binding(
    "ctrl+s",
    "focus_sidebar",
    "Focus sidebar",
    key_display="Ctrl + S",
    priority=True,
)

SIDEBAR_PREVIOUS_TAB_BINDING = Binding(
    "left",
    "previous_tab",
    "Previous sidebar tab",
    key_display="←",
)

SIDEBAR_NEXT_TAB_BINDING = Binding(
    "right",
    "next_tab",
    "Next sidebar tab",
    key_display="→",
)

SIDEBAR_PREVIOUS_SESSION_BINDING = Binding(
    "up",
    "previous_session",
    "Previous session",
    key_display="↑",
)

SIDEBAR_NEXT_SESSION_BINDING = Binding(
    "down",
    "next_session",
    "Next session",
    key_display="↓",
)

SIDEBAR_OPEN_SESSION_BINDING = Binding(
    "enter",
    "open_session",
    "Open / resume",
    key_display="Enter",
)

# Global application shortcut bindings.
APPLICATION_BINDINGS = (
    HUB_LOCK_BINDING,
    COMMAND_PALETTE_BINDING,
    REFRESH_SESSIONS_BINDING,
    FOCUS_SIDEBAR_BINDING,
)

# Sidebar shortcut bindings.
SIDEBAR_BINDINGS = (
    SIDEBAR_PREVIOUS_TAB_BINDING,
    SIDEBAR_NEXT_TAB_BINDING,
    SIDEBAR_PREVIOUS_SESSION_BINDING,
    SIDEBAR_NEXT_SESSION_BINDING,
    SIDEBAR_OPEN_SESSION_BINDING,
)


# Helper functions.
def binding_key(binding: Binding) -> str:
    """Return the display text for a binding key."""

    return cast(str, binding.key_display)


__all__ = [
    "APPLICATION_BINDINGS",
    "COMMAND_PALETTE_BINDING",
    "FOCUS_SIDEBAR_BINDING",
    "HUB_LOCK_BINDING",
    "REFRESH_SESSIONS_BINDING",
    "SIDEBAR_BINDINGS",
    "SIDEBAR_NEXT_SESSION_BINDING",
    "SIDEBAR_NEXT_TAB_BINDING",
    "SIDEBAR_OPEN_SESSION_BINDING",
    "SIDEBAR_PREVIOUS_SESSION_BINDING",
    "SIDEBAR_PREVIOUS_TAB_BINDING",
    "binding_key",
]
