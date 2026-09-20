"""Manual reconciliation picker for a fresh native-agent runtime."""

from collections.abc import Iterable
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from agenthub.sessions import AgentSession


class NativeSessionLinkModal(ModalScreen[str]):
    """Return the AgentHub row ID of a user-selected native conversation."""

    CSS_PATH = "../styles/modals/native_session_link.tcss"
    BINDINGS: ClassVar = [Binding("escape", "cancel", show=False)]

    def __init__(
        self,
        pending_session: AgentSession,
        candidates: Iterable[AgentSession],
    ) -> None:
        """Retain an already-filtered candidate snapshot for presentation."""

        super().__init__()
        self._pending_session = pending_session
        self._candidates = tuple(candidates)

    def compose(self) -> ComposeResult:
        """Compose a context-rich native-session picker."""

        with Vertical(id="native-session-link-dialog"):
            with Horizontal(id="native-session-link-header"):
                yield Label(
                    f"Link {self._pending_session.harness.display_name} Session",
                    id="native-session-link-title",
                )
                with Horizontal(
                    id="native-session-link-cancel",
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
                "Choose the native conversation opened by this running terminal.",
                id="native-session-link-copy",
                classes="muted",
            )
            yield OptionList(
                *(
                    Option(
                        session.name,
                        id=session.id,
                    )
                    for session in self._candidates
                ),
                id="native-session-link-list",
            )
            with Grid(id="native-session-link-help", classes="modal-shortcut-grid"):
                yield Static("↑/↓", classes="modal-shortcut-key")
                yield Static("Navigate", classes="modal-shortcut-description")
                yield Static("Enter", classes="modal-shortcut-key")
                yield Static("Link", classes="modal-shortcut-description")

    def on_mount(self) -> None:
        """Select and focus the first native conversation."""

        session_list = self.query_one("#native-session-link-list", OptionList)
        if session_list.options:
            session_list.highlighted = 0
        session_list.focus()

    def on_option_list_option_selected(
        self,
        message: OptionList.OptionSelected,
    ) -> None:
        """Dismiss with AgentHub row identity for app-level revalidation."""

        message.stop()
        if message.option_id is not None:
            self.dismiss(message.option_id)

    def action_cancel(self) -> None:
        """Close without changing either logical session."""

        self.dismiss(None)
