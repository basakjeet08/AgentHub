"""Central catalog of AgentHub's static Textual key bindings."""

from textual.binding import Binding

TOGGLE_HUB_LOCK_BINDING = Binding(
    "ctrl+g",
    "toggle_hub_lock",
    "Lock / unlock AgentHub",
    key_display="Ctrl+G",
    priority=True,
)

COMMAND_PALETTE_BINDING = Binding(
    "ctrl+p",
    "command_palette",
    "Command palette",
    key_display="Ctrl+P",
    priority=True,
)

RESYNC_SESSIONS_BINDING = Binding(
    "ctrl+shift+r",
    "resync_sessions",
    "Re-sync native sessions",
    key_display="Ctrl+Shift+R",
    priority=True,
)

FOCUS_SIDEBAR_BINDING = Binding(
    "ctrl+s",
    "focus_sidebar",
    "Focus sidebar",
    key_display="Ctrl+S",
    priority=True,
)

# These actions belong to AgentHub only while the hub owns navigation keys. A
# failed check_action deliberately lets the original key reach AgentTerminal.
TERMINAL_GATED_ACTIONS = frozenset(
    {
        "command_palette",
        "focus_sidebar",
        "resync_sessions",
    }
)

APPLICATION_BINDINGS = (
    TOGGLE_HUB_LOCK_BINDING,
    COMMAND_PALETTE_BINDING,
    RESYNC_SESSIONS_BINDING,
    FOCUS_SIDEBAR_BINDING,
)

HOME_SHORTCUTS = (
    *(
        (binding.key_display or binding.key, binding.description)
        for binding in (
            TOGGLE_HUB_LOCK_BINDING,
            COMMAND_PALETTE_BINDING,
            RESYNC_SESSIONS_BINDING,
        )
    ),
    ("Ctrl+S", "Focus sidebar"),
    ("← / →", "Change sidebar tab"),
    ("↑ / ↓, Enter", "Navigate / open session"),
)

__all__ = [
    "APPLICATION_BINDINGS",
    "COMMAND_PALETTE_BINDING",
    "FOCUS_SIDEBAR_BINDING",
    "HOME_SHORTCUTS",
    "RESYNC_SESSIONS_BINDING",
    "TERMINAL_GATED_ACTIONS",
    "TOGGLE_HUB_LOCK_BINDING",
]
