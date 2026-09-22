"""Session-name input for the New Shell Session workflow."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static


class ShellSessionNameInputModal(ModalScreen[str]):
    """Capture an optional shell-session name."""

    CSS_PATH = "../styles/modals/shell_session_name_input.tcss"
    BINDINGS: ClassVar = [Binding("escape", "cancel", show=False)]

    def compose(self) -> ComposeResult:
        """Compose the focused name input and keyboard guidance."""

        with Vertical(id="shell-session-name-input-dialog"):
            with Horizontal(id="shell-session-name-input-header"):
                yield Label("Name Shell Session", id="shell-session-name-input-title")
                with Horizontal(
                    id="shell-session-name-input-cancel",
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
            yield Label("Name", id="shell-session-name-input-label")
            yield Input(
                placeholder="Shell (optional)",
                id="shell-session-name-input",
            )
            with Grid(
                id="shell-session-name-input-help",
                classes="modal-shortcut-grid",
            ):
                yield Static("Enter", classes="modal-shortcut-key")
                yield Static("Create", classes="modal-shortcut-description")

    def on_mount(self) -> None:
        """Place keyboard focus in the empty session-name input."""

        self.query_one("#shell-session-name-input", Input).focus()

    def on_input_submitted(self, message: Input.Submitted) -> None:
        """Return a trimmed name or the default shell-session name."""

        self.dismiss(message.value.strip() or "Shell")

    def action_cancel(self) -> None:
        """Cancel the session naming workflow."""

        self.dismiss(None)
