"""Coding-agent harness selection for the New Agent Session workflow."""

from collections.abc import Iterable
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from agenthub.harnesses import AgentHarness


class HarnessSelectionModal(ModalScreen[str]):
    """Return the stable ID of a user-selected coding-agent harness."""

    CSS_PATH = "harness_selection.tcss"
    BINDINGS: ClassVar = [Binding("escape", "cancel", show=False)]

    def __init__(self, harnesses: Iterable[AgentHarness]) -> None:
        """Retain the registry-derived harnesses in their supplied order."""

        super().__init__()
        self._harnesses = tuple(harnesses)

    def compose(self) -> ComposeResult:
        """Compose a compact launcher-style harness picker."""

        with Vertical(id="harness-selection-dialog"):
            yield Label("Select a harness", id="harness-selection-title")
            yield OptionList(
                *(
                    Option(harness.display_name, id=harness.id)
                    for harness in self._harnesses
                ),
                id="harness-selection-list",
            )
            yield Static(
                "↑/↓ Navigate     Enter Select     Esc Close",
                id="harness-selection-help",
            )

    def on_mount(self) -> None:
        """Select and focus the first registered harness when available."""

        harness_list = self.query_one("#harness-selection-list", OptionList)
        if harness_list.options:
            harness_list.highlighted = 0
        harness_list.focus()

    def on_option_list_option_selected(
        self,
        message: OptionList.OptionSelected,
    ) -> None:
        """Dismiss with stable harness identity rather than presentation text."""

        message.stop()
        if message.option_id is not None:
            self.dismiss(message.option_id)

    def action_cancel(self) -> None:
        """Close the workflow without selecting a harness."""

        self.dismiss(None)
