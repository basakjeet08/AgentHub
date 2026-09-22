"""Confirmation dialog for irreversible provider-native conversation deletion."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class SessionDeleteConfirmationModal(ModalScreen[bool]):
    """Confirm permanent deletion of one already-resolved Agent row."""

    CSS_PATH = "../styles/modals/session_delete_confirmation.tcss"
    BINDINGS: ClassVar = [
        Binding("escape", "cancel", show=False),
        Binding("left", "focus_cancel", show=False),
        Binding("right", "focus_delete", show=False),
    ]

    def __init__(self, session_name: str) -> None:
        super().__init__()
        self._session_name = session_name

    def compose(self) -> ComposeResult:
        """Compose the destructive prompt with a safe default action."""

        with Vertical(id="session-delete-confirmation-dialog"):
            yield Static(
                f'Delete "{self._session_name}" permanently?',
                id="session-delete-confirmation-copy",
                markup=False,
            )
            with Horizontal(id="session-delete-confirmation-actions"):
                yield Button("Cancel", id="session-delete-confirmation-cancel")
                yield Button(
                    "Delete",
                    id="session-delete-confirmation-confirm",
                    variant="error",
                )

    def on_mount(self) -> None:
        """Keep accidental Enter presses on the non-destructive choice."""

        self.query_one("#session-delete-confirmation-cancel", Button).focus()

    def on_button_pressed(self, message: Button.Pressed) -> None:
        """Return whether the destructive action was explicitly selected."""

        message.stop()
        self.dismiss(message.button.id == "session-delete-confirmation-confirm")

    def action_cancel(self) -> None:
        """Dismiss without changing the logical or native session."""

        self.dismiss(False)

    def action_focus_cancel(self) -> None:
        """Move keyboard selection to the safe action."""

        self.query_one("#session-delete-confirmation-cancel", Button).focus()

    def action_focus_delete(self) -> None:
        """Move keyboard selection to the destructive action."""

        self.query_one("#session-delete-confirmation-confirm", Button).focus()
