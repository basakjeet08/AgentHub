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

COMMAND_PALETTE_BINDING = Binding(
    "ctrl+p",
    "command_palette",
    "Command palette",
    key_display="Ctrl+P",
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
        "new_session",
        "quit",
    }
)

APPLICATION_BINDINGS = (
    TOGGLE_HUB_LOCK_BINDING,
    NEW_SESSION_BINDING,
    COMMAND_PALETTE_BINDING,
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
            COMMAND_PALETTE_BINDING,
        )
    ),
    ("Ctrl+A, then 1…9", "Switch agent session"),
    ("Ctrl+S, then 1…9", "Open / switch shell"),
)

__all__ = [
    "APPLICATION_BINDINGS",
    "COMMAND_PALETTE_BINDING",
    "FOCUS_AGENTS_BINDING",
    "FOCUS_SHELLS_BINDING",
    "HOME_SHORTCUTS",
    "NEW_SESSION_BINDING",
    "NUMBERED_SESSION_BINDINGS",
    "QUIT_BINDING",
    "TERMINAL_GATED_ACTIONS",
    "TOGGLE_HUB_LOCK_BINDING",
]
