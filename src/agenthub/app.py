"""Application shell: layout, key bindings, and widget orchestration."""

from typing import ClassVar

from textual.app import App, ComposeResult

from agenthub.terminal import DEFAULT_HARNESS, HARNESSES, AgentHarness


class AgentHubApp(App):
    """Fullscreen host for one agent harness session."""

    BINDINGS: ClassVar[list[tuple[str, str, str]]] = [
        ("ctrl+q", "quit", "Quit")
    ]

    def __init__(self, harness: AgentHarness | None = None) -> None:
        """Use the given harness (default: opencode)."""

        super().__init__()
        self.harness = harness or HARNESSES[DEFAULT_HARNESS]

    def compose(self) -> ComposeResult:
        """Build the widget tree from the active harness's widget."""

        yield self.harness.create_widget(id="shell")

    def on_mount(self) -> None:
        """Focus the terminal once mounted so keystrokes reach the agent."""

        self.set_focus(self.query_one("#shell"))

    def on_terminal_process_exited(self, message) -> None:
        """Quit the app when the agent process exits."""

        self.exit()
