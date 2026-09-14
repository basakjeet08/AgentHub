"""Session-name input for the New Agent Session workflow."""

import os
import shutil
import subprocess
import sys
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static


def _system_clipboard_command() -> tuple[str, ...] | None:
    """Return the first available native command for reading clipboard text."""

    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-paste"):
        return ("wl-paste", "--no-newline", "--type", "text")
    if os.environ.get("DISPLAY"):
        if shutil.which("xclip"):
            return ("xclip", "-selection", "clipboard", "-o")
        if shutil.which("xsel"):
            return ("xsel", "--clipboard", "--output")
    if sys.platform == "darwin" and shutil.which("pbpaste"):
        return ("pbpaste",)
    return None


def _read_system_clipboard() -> str | None:
    """Read OS clipboard text, falling back when no supported command exists."""

    command = _system_clipboard_command()
    if command is None:
        return None
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return ""
    try:
        return result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        return ""


class SessionNameInput(Input):
    """Input whose Ctrl+V can read the surrounding OS clipboard."""

    def action_paste(self) -> None:
        """Paste external clipboard text or use Textual's local fallback."""

        clipboard = _read_system_clipboard()
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
    """Capture and validate the user-provided AgentHub session name."""

    CSS_PATH = "session_name.tcss"
    BINDINGS: ClassVar = [Binding("escape", "cancel", show=False)]

    def __init__(self, harness_display_name: str) -> None:
        """Retain presentation-only harness context for the prompt."""

        super().__init__()
        self._harness_display_name = harness_display_name

    def compose(self) -> ComposeResult:
        """Compose the focused name input and keyboard guidance."""

        with Vertical(id="session-name-dialog"):
            yield Label("Name Session", id="session-name-title")
            yield Static(
                f"Harness: {self._harness_display_name}",
                id="session-name-harness",
            )
            yield Label("Name", id="session-name-label")
            yield SessionNameInput(id="session-name-input")
            yield Static("", id="session-name-error")
            yield Static(
                "Enter Create                 Esc Cancel",
                id="session-name-help",
            )

    def on_mount(self) -> None:
        """Place keyboard focus in the empty session-name input."""

        self.query_one("#session-name-input", Input).focus()

    def on_input_submitted(self, message: Input.Submitted) -> None:
        """Return a trimmed non-empty name or retain focus with validation."""

        name = message.value.strip()
        if not name:
            message.input.add_class("invalid-name")
            self.query_one("#session-name-error", Static).update("Enter a session name.")
            message.input.focus()
            return

        self.dismiss(name)

    def on_input_changed(self, message: Input.Changed) -> None:
        """Clear validation feedback once the input becomes usable."""

        if message.value.strip():
            message.input.remove_class("invalid-name")
            self.query_one("#session-name-error", Static).update("")

    def action_cancel(self) -> None:
        """Cancel the entire New Agent Session workflow."""

        self.dismiss(None)
