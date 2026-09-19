"""Neutral Home presentation for empty or temporarily unselected sessions."""

from textual import events
from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, TabbedContent, TabPane, Tabs

_NARROW_LAYOUT_WIDTH = 80

_SESSION_TYPES = (
    ("Loaded", "Agent sessions currently running and ready to use."),
    ("Unloaded", "Existing agent conversations available to resume."),
    ("Shells", "Regular shell terminals running inside AgentHub."),
)

_QUICK_START_FLOWS = (
    ("New Agent", "Ctrl+P → New Agent → Choose Coding Agent → Choose Directory"),
    ("New Shell", "Ctrl+P → New Shell → Optionally Enter a Name"),
)

_COMMAND_PALETTE_STEPS = (
    ("Ctrl+P", "Open the Command Palette."),
    ("Search", "Start typing to filter actions and sessions."),
    ("↑ / ↓", "Move through the results."),
    ("Enter", "Run the highlighted option."),
)

_SIDEBAR_STEPS = (
    ("Ctrl+S", "Focus the sidebar."),
    ("← / →", "Switch between Loaded, Unloaded, and Shells."),
    ("↑ / ↓", "Move through sessions in the selected section."),
    ("Enter", "Open the selected session or resume an unloaded Agent."),
)

_KEYBOARD_MODES = (
    ("Unlocked", "AgentHub navigation shortcuts are active."),
    ("Locked", "Keyboard input is sent to the active terminal."),
    ("Ctrl+G", "Switch between Locked and Unlocked at any time."),
)

_GLOBAL_SHORTCUTS = (
    ("Ctrl+P", "Open the Command Palette."),
    ("Ctrl+S", "Focus the sidebar."),
    ("Ctrl+Shift+R", "Refresh native sessions."),
    ("Ctrl+G", "Lock or unlock AgentHub."),
)

_QUICK_REFERENCE = (
    "Ctrl+P Commands  •  Ctrl+S Sidebar  •  Ctrl+G Lock/Unlock  •  Ctrl+Shift+R Refresh"
)


class HomeScreen(VerticalScroll):
    """Beginner-friendly tabbed guide to AgentHub's core workflows."""

    def compose(self) -> ComposeResult:
        """Compose the persistent Home hero, tabbed guide, and quick reference."""

        with Vertical(id="home-content"):
            with Horizontal(id="home-heading"):
                yield Static("AgentHub", id="home-title")
                yield Static(
                    "Your agents live here.",
                    id="home-tagline",
                    classes="muted",
                )
            with TabbedContent(
                initial="home-pane-getting-started",
                id="home-tabs",
            ):
                with (
                    TabPane("Start Here", id="home-pane-getting-started"),
                    Vertical(
                        id="home-card-getting-started",
                        classes="home-card card",
                    ),
                ):
                    yield Static("GETTING STARTED", classes="home-card-title")
                    with Vertical(classes="home-card-section"):
                        yield Static(
                            "• What is AgentHub?",
                            classes="home-card-subheading",
                        )
                        yield Static(
                            "AgentHub is a terminal workspace for managing "
                            "coding-agent conversations and shell sessions from one place.",
                            classes="home-card-copy",
                        )
                    with Vertical(classes="home-card-section"):
                        yield Static(
                            "• What are Loaded, Unloaded, and Shells?",
                            classes="home-card-subheading",
                        )
                        with Grid(classes="home-pair-grid"):
                            for label, description in _SESSION_TYPES:
                                yield Static(label, classes="home-pair-key")
                                yield Static(
                                    description,
                                    classes="home-pair-description",
                                )
                    with Vertical(classes="home-card-section"):
                        yield Static("• Quick Start", classes="home-card-subheading")
                        with Grid(classes="home-pair-grid"):
                            for label, flow in _QUICK_START_FLOWS:
                                yield Static(label, classes="home-pair-key")
                                yield Static(flow, classes="home-flow")

                with (
                    TabPane("Navigation", id="home-pane-navigation-basics"),
                    Vertical(
                        id="home-card-navigation-basics",
                        classes="home-card card",
                    ),
                ):
                    yield Static("NAVIGATION BASICS", classes="home-card-title")
                    with Vertical(classes="home-card-section"):
                        yield Static(
                            "• Command Palette",
                            classes="home-card-subheading",
                        )
                        with Grid(classes="home-pair-grid"):
                            for label, description in _COMMAND_PALETTE_STEPS:
                                yield Static(label, classes="home-pair-key")
                                yield Static(
                                    description,
                                    classes="home-pair-description",
                                )
                        yield Static(
                            "Available options include New Agent, New Shell, Open Session, "
                            "Refresh Native Sessions, and Quit AgentHub. Link and Delete "
                            "appear when they apply to the currently open Agent.",
                            classes="home-card-note",
                        )
                    with Vertical(classes="home-card-section"):
                        yield Static(
                            "• Sidebar Navigation",
                            classes="home-card-subheading",
                        )
                        with Grid(classes="home-pair-grid"):
                            for label, description in _SIDEBAR_STEPS:
                                yield Static(label, classes="home-pair-key")
                                yield Static(
                                    description,
                                    classes="home-pair-description",
                                )

                with (
                    TabPane("Sessions", id="home-pane-session-management"),
                    Vertical(
                        id="home-card-session-management",
                        classes="home-card card",
                    ),
                ):
                    yield Static("SESSION MANAGEMENT", classes="home-card-title")
                    with Vertical(classes="home-card-section"):
                        yield Static(
                            "• Create a Session",
                            classes="home-card-subheading",
                        )
                        yield Static(
                            "Use Ctrl+P and select New Agent or New Shell.",
                            classes="home-card-copy",
                        )
                    with Vertical(classes="home-card-section"):
                        yield Static(
                            "• Resume an Existing Agent",
                            classes="home-card-subheading",
                        )
                        yield Static(
                            "Resume an unloaded Agent and continue its existing conversation.",
                            classes="home-card-copy",
                        )
                        yield Static(
                            "Ctrl+S → Unloaded → Choose Session → Enter",
                            classes="home-flow home-indented",
                        )
                    with Vertical(classes="home-card-section"):
                        yield Static("• Link an Agent", classes="home-card-subheading")
                        yield Static(
                            "Connect a newly created AgentHub session to its matching saved "
                            "conversation. The fresh Agent must be open in the main "
                            "terminal.",
                            classes="home-card-copy",
                        )
                        yield Static(
                            "Open Fresh Agent → Ctrl+P → Link → Choose Conversation",
                            classes="home-flow home-indented",
                        )
                    with Vertical(classes="home-card-section"):
                        yield Static(
                            "• Refresh Sessions",
                            classes="home-card-subheading",
                        )
                        yield Static(
                            "Scan supported coding agents for new, changed, or removed "
                            "conversations.",
                            classes="home-card-copy",
                        )
                        yield Static(
                            "Ctrl+Shift+R",
                            classes="home-flow home-indented",
                        )
                    with Vertical(classes="home-card-section"):
                        yield Static(
                            "• Delete an Agent",
                            classes="home-card-subheading",
                        )
                        yield Static(
                            "Permanently delete the currently open conversation where "
                            "supported. The Agent must be open in the main terminal.",
                            classes="home-card-copy",
                        )
                        yield Static(
                            "Open Agent → Ctrl+P → Delete",
                            classes="home-flow home-indented",
                        )
                    yield Static(
                        "Note — Link and Delete apply to the Agent open in the main "
                        "terminal, not the session merely highlighted in the sidebar.",
                        classes="home-card-note home-management-note",
                    )

                with (
                    TabPane("Shortcuts", id="home-pane-controls-shortcuts"),
                    Vertical(
                        id="home-card-controls-shortcuts",
                        classes="home-card card",
                    ),
                ):
                    yield Static("CONTROLS & SHORTCUTS", classes="home-card-title")
                    with Vertical(classes="home-card-section"):
                        yield Static(
                            "• Keyboard Control",
                            classes="home-card-subheading",
                        )
                        with Grid(classes="home-pair-grid"):
                            for label, description in _KEYBOARD_MODES:
                                yield Static(label, classes="home-pair-key")
                                yield Static(
                                    description,
                                    classes="home-pair-description",
                                )
                    with Vertical(classes="home-card-section"):
                        yield Static(
                            "• Global Shortcuts",
                            classes="home-card-subheading",
                        )
                        with Grid(classes="home-pair-grid"):
                            for label, description in _GLOBAL_SHORTCUTS:
                                yield Static(label, classes="home-pair-key")
                                yield Static(
                                    description,
                                    classes="home-pair-description",
                                )
                    with Vertical(classes="home-card-section"):
                        yield Static("• Quit AgentHub", classes="home-card-subheading")
                        yield Static(
                            "Ctrl+P → Quit AgentHub",
                            classes="home-flow home-indented",
                        )

            yield Static(
                _QUICK_REFERENCE,
                id="home-quick-reference",
                classes="muted",
            )

    def on_mount(self) -> None:
        """Keep Home section tabs mouse-only and out of the focus chain."""

        self.query_one("#home-tabs", TabbedContent).query_one(Tabs).can_focus = False

    def on_resize(self, event: events.Resize) -> None:
        """Keep the hero and content grids readable in narrow terminals."""

        self.set_class(event.size.width < _NARROW_LAYOUT_WIDTH, "narrow")
