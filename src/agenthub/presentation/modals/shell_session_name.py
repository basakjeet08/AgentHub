"""Session-name input for the New Shell Session workflow."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from agenthub.clipboard import ClipboardService

_CLIPBOARD_SERVICE = ClipboardService()


class SessionNameInput(Input):
    """Input whose Ctrl+V can read the surrounding OS clipboard."""

    def action_paste(self) -> None:
        """Read external clipboard text without blocking the Textual event loop."""

        self.run_worker(
            self._paste_system_clipboard(),
            group="clipboard-paste",
            exclusive=True,
            exit_on_error=False,
        )

    async def _paste_system_clipboard(self) -> None:
        """Paste external clipboard text or use Textual's local fallback."""

        clipboard = await _CLIPBOARD_SERVICE.read_text()
        if not self.is_mounted:
            return

        if clipboard is None:
            super().action_paste()
            return

        if not clipboard:
            return

        lines = clipboard.splitlines()
        first_line = lines[0] if lines else clipboard
        start, end = self.selection
        self.replace(first_line, start, end)


class ShellSessionNameModal(ModalScreen[str]):
    """Capture an optional shell-session name."""

    CSS_PATH = "../styles/modals/shell_session_name.tcss"
    BINDINGS: ClassVar = [Binding("escape", "cancel", show=False)]

    def compose(self) -> ComposeResult:
        """Compose the focused name input and keyboard guidance."""

        with Vertical(id="session-name-dialog"):
            with Horizontal(id="session-name-header"):
                yield Label("Name Shell Session", id="session-name-title")
                with Horizontal(
                    id="session-name-cancel",
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
            yield Label("Name", id="session-name-label")
            yield SessionNameInput(
                placeholder="Shell (optional)",
                id="session-name-input",
            )
            with Grid(id="session-name-help", classes="modal-shortcut-grid"):
                yield Static("Enter", classes="modal-shortcut-key")
                yield Static("Create", classes="modal-shortcut-description")

    def on_mount(self) -> None:
        """Place keyboard focus in the empty session-name input."""

        self.query_one("#session-name-input", Input).focus()

    def on_input_submitted(self, message: Input.Submitted) -> None:
        """Return a trimmed name or the default shell-session name."""

        self.dismiss(message.value.strip() or "Shell")

    def action_cancel(self) -> None:
        """Cancel the session naming workflow."""

        self.dismiss(None)
