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


class SessionNameModal(ModalScreen[str]):
    """Capture and validate an optional AgentHub shell-session name."""

    CSS_PATH = "../styles/modals/session_name.tcss"
    BINDINGS: ClassVar = [Binding("escape", "cancel", show=False)]

    def __init__(
        self,
        harness_display_name: str,
        *,
        default_name: str | None = None,
        placeholder: str | None = None,
    ) -> None:
        """Retain presentation-only harness context and optional default name."""

        super().__init__()
        self._harness_display_name = harness_display_name
        self._default_name = default_name
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        """Compose the focused name input and keyboard guidance."""

        with Vertical(id="session-name-dialog"):
            with Horizontal(id="session-name-header"):
                yield Label("Name Session", id="session-name-title")
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
            yield Static(
                f"Harness: {self._harness_display_name}",
                id="session-name-harness",
            )
            yield Label("Name", id="session-name-label")
            yield SessionNameInput(
                placeholder=self._placeholder or "",
                id="session-name-input",
            )
            yield Static("", id="session-name-error")
            with Grid(id="session-name-help", classes="modal-shortcut-grid"):
                yield Static("Enter", classes="modal-shortcut-key")
                yield Static("Create", classes="modal-shortcut-description")

    def on_mount(self) -> None:
        """Place keyboard focus in the empty session-name input."""

        self.query_one("#session-name-input", Input).focus()

    def on_input_submitted(self, message: Input.Submitted) -> None:
        """Return a trimmed non-empty name, or default if optional, or retain focus with validation."""

        name = message.value.strip()
        if not name:
            if self._default_name is not None:
                self.dismiss(self._default_name)
                return

            message.input.add_class("invalid-name")
            self.query_one("#session-name-error", Static).update("Enter a session name.")
            message.input.focus()
            return

        self.dismiss(name)

    def on_input_changed(self, message: Input.Changed) -> None:
        """Clear validation feedback once the input becomes usable."""

        if message.value.strip() or self._default_name is not None:
            message.input.remove_class("invalid-name")
            self.query_one("#session-name-error", Static).update("")

    def action_cancel(self) -> None:
        """Cancel the session naming workflow."""

        self.dismiss(None)
