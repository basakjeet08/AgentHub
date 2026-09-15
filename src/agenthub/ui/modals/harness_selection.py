"""Coding-agent harness selection for the New Agent Session workflow."""

from collections.abc import Iterable
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
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
            with Horizontal(id="harness-selection-header"):
                yield Label("Select a harness", id="harness-selection-title")
                with Horizontal(
                    id="harness-selection-cancel",
                    classes="modal-cancel",
                ):
                    yield Static(
                        "Esc",
                        classes="modal-shortcut-key modal-cancel-key",
                    )
                    yield Static(
                        "Cancel",
                        classes="modal-shortcut-description modal-cancel-description",
                    )
            yield OptionList(
                *(
                    Option(harness.display_name, id=harness.id)
                    for harness in self._harnesses
                ),
                id="harness-selection-list",
            )
            with Grid(id="harness-selection-help", classes="modal-shortcut-grid"):
                yield Static("↑/↓", classes="modal-shortcut-key")
                yield Static("Navigate", classes="modal-shortcut-description")
                yield Static("Enter", classes="modal-shortcut-key")
                yield Static("Select", classes="modal-shortcut-description")

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
