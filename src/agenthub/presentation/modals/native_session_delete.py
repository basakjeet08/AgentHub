"""Confirmation dialog for irreversible provider-native conversation deletion."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class NativeSessionDeleteModal(ModalScreen[bool]):
    """Confirm permanent deletion of one already-resolved Agent row."""

    CSS_PATH = "../styles/modals/native_session_delete.tcss"
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

        with Vertical(id="native-session-delete-dialog"):
            yield Static(
                f'Delete "{self._session_name}" permanently?',
                id="native-session-delete-copy",
                markup=False,
            )
            with Horizontal(id="native-session-delete-actions"):
                yield Button("Cancel", id="native-session-delete-cancel")
                yield Button(
                    "Delete",
                    id="native-session-delete-confirm",
                    variant="error",
                )

    def on_mount(self) -> None:
        """Keep accidental Enter presses on the non-destructive choice."""

        self.query_one("#native-session-delete-cancel", Button).focus()

    def on_button_pressed(self, message: Button.Pressed) -> None:
        """Return whether the destructive action was explicitly selected."""

        message.stop()
        self.dismiss(message.button.id == "native-session-delete-confirm")

    def action_cancel(self) -> None:
        """Dismiss without changing the logical or native session."""

        self.dismiss(False)

    def action_focus_cancel(self) -> None:
        """Move keyboard selection to the safe action."""

        self.query_one("#native-session-delete-cancel", Button).focus()

    def action_focus_delete(self) -> None:
        """Move keyboard selection to the destructive action."""

        self.query_one("#native-session-delete-confirm", Button).focus()
