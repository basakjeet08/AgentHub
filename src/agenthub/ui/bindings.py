"""Central catalog of AgentHub's static Textual key bindings."""

from textual.binding import Binding

TOGGLE_HUB_LOCK_BINDING = Binding(
    "ctrl+g",
    "toggle_hub_lock",
    "Lock / unlock AgentHub",
    key_display="Ctrl+G",
    priority=True,
)

NEW_SESSION_BINDING = Binding(
    "ctrl+n",
    "new_session",
    "New agent session",
    key_display="Ctrl+N",
    priority=True,
)

NEW_SHELL_BINDING = Binding(
    "ctrl+shift+s",
    "new_shell",
    "New shell",
    key_display="Ctrl+Shift+S",
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

LINK_NATIVE_SESSION_BINDING = Binding(
    "alt+m",
    "link_native_session",
    "Link native session",
    key_display="Alt+M",
    priority=True,
)

FOCUS_AGENTS_BINDING = Binding(
    "ctrl+a",
    "focus_agents",
    "Focus agent sessions",
    key_display="Ctrl+A",
    priority=True,
)

FOCUS_SHELLS_BINDING = Binding(
    "ctrl+s",
    "focus_shells",
    "Focus shell sessions",
    key_display="Ctrl+S",
    priority=True,
)

QUIT_BINDING = Binding(
    "ctrl+q",
    "quit",
    "Quit",
    key_display="Ctrl+Q",
    priority=True,
)

NUMBERED_SESSION_BINDINGS = tuple(
    Binding(
        str(number),
        f"select_numbered_session({number})",
        f"Select session {number}",
        show=False,
    )
    for number in range(1, 10)
)

# These actions belong to AgentHub only while the hub owns navigation keys. A
# failed check_action deliberately lets the original key reach AgentTerminal.
TERMINAL_GATED_ACTIONS = frozenset(
    {
        "command_palette",
        "focus_agents",
        "focus_shells",
        "link_native_session",
        "new_session",
        "new_shell",
        "quit",
        "resync_sessions",
    }
)

APPLICATION_BINDINGS = (
    TOGGLE_HUB_LOCK_BINDING,
    NEW_SESSION_BINDING,
    NEW_SHELL_BINDING,
    COMMAND_PALETTE_BINDING,
    RESYNC_SESSIONS_BINDING,
    LINK_NATIVE_SESSION_BINDING,
    FOCUS_AGENTS_BINDING,
    FOCUS_SHELLS_BINDING,
    QUIT_BINDING,
)

HOME_SHORTCUTS = (
    *(
        (binding.key_display or binding.key, binding.description)
        for binding in (
            TOGGLE_HUB_LOCK_BINDING,
            NEW_SESSION_BINDING,
            NEW_SHELL_BINDING,
            COMMAND_PALETTE_BINDING,
            RESYNC_SESSIONS_BINDING,
        )
    ),
    ("Ctrl+A, 1…9, Enter", "Navigate / open agent"),
    ("Ctrl+S, ↑↓, Enter", "Navigate / open shell"),
)

__all__ = [
    "APPLICATION_BINDINGS",
    "COMMAND_PALETTE_BINDING",
    "FOCUS_AGENTS_BINDING",
    "FOCUS_SHELLS_BINDING",
    "HOME_SHORTCUTS",
    "LINK_NATIVE_SESSION_BINDING",
    "NEW_SESSION_BINDING",
    "NEW_SHELL_BINDING",
    "NUMBERED_SESSION_BINDINGS",
    "QUIT_BINDING",
    "RESYNC_SESSIONS_BINDING",
    "TERMINAL_GATED_ACTIONS",
    "TOGGLE_HUB_LOCK_BINDING",
]
