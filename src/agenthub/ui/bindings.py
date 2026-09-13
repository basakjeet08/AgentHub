"""Central catalog of AgentHub's static Textual key bindings."""

from textual.binding import Binding

NEW_SESSION_BINDING = Binding(
    "ctrl+n",
    "new_session",
    "New session",
    key_display="Ctrl+N",
    priority=True,
)

FOCUS_SIDEBAR_BINDING = Binding(
    "ctrl+left",
    "focus_sidebar",
    "Focus sidebar",
    key_display="Ctrl+←",
    priority=True,
)

FOCUS_WORKSPACE_BINDING = Binding(
    "ctrl+right",
    "focus_workspace",
    "Focus workspace",
    key_display="Ctrl+→",
    priority=True,
)

QUIT_BINDING = Binding(
    "ctrl+q",
    "quit",
    "Quit",
    key_display="Ctrl+Q",
    priority=True,
)

APPLICATION_BINDINGS = (
    NEW_SESSION_BINDING,
    FOCUS_SIDEBAR_BINDING,
    FOCUS_WORKSPACE_BINDING,
    QUIT_BINDING,
)

HOME_SHORTCUT_BINDINGS = (
    NEW_SESSION_BINDING,
    FOCUS_SIDEBAR_BINDING,
    FOCUS_WORKSPACE_BINDING,
)

__all__ = [
    "APPLICATION_BINDINGS",
    "FOCUS_SIDEBAR_BINDING",
    "FOCUS_WORKSPACE_BINDING",
    "HOME_SHORTCUT_BINDINGS",
    "NEW_SESSION_BINDING",
    "QUIT_BINDING",
]
