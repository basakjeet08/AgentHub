"""Unified picker for opening a managed Agent or Shell session."""

from collections.abc import Iterable
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, OptionList, Static
from textual.widgets.option_list import Option, OptionDoesNotExist

from agenthub.sessions import AgentSession


def _session_option_prompt(session: AgentSession) -> str:
    """Format one session as only its harness icon and title."""

    prefix = f"{session.harness.icon} " if session.harness.icon else ""
    return f"{prefix}{session.name}"


class SessionSelectionModal(ModalScreen[str]):
    """Return the AgentHub ID of a user-selected openable session."""

    CSS_PATH = "../styles/modals/session_selection.tcss"
    BINDINGS: ClassVar = [
        Binding("escape", "cancel", show=False),
        Binding("up", "cursor_up", show=False, priority=True),
        Binding("down", "cursor_down", show=False, priority=True),
    ]

    def __init__(
        self,
        sessions: Iterable[AgentSession],
    ) -> None:
        """Retain an ordered session snapshot for presentation."""

        super().__init__()
        self._sessions = tuple(sessions)
        self._harnesses = tuple(
            {
                session.harness.id: session.harness
                for session in self._sessions
            }.values()
        )

    def compose(self) -> ComposeResult:
        """Compose the unified Agent and Shell picker."""

        with Vertical(id="session-selection-dialog"):
            with Horizontal(id="session-selection-header"):
                yield Label("Open Session", id="session-selection-title")
                with Horizontal(
                    id="session-selection-cancel",
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
                "Choose an Agent or Shell session to open.",
                id="session-selection-copy",
                classes="muted",
            )
            yield Input(
                placeholder="Search by harness or session title",
                id="session-selection-search",
            )
            yield OptionList(
                *(
                    Option(
                        _session_option_prompt(session),
                        id=session.id,
                    )
                    for session in self._sessions
                ),
                id="session-selection-list",
            )
            yield Static(
                "No matching sessions.",
                id="session-selection-empty",
                classes="muted",
            )
            yield Static(
                "Harnesses",
                id="session-selection-legend-title",
                classes="muted",
            )
            with Grid(id="session-selection-legend"):
                for harness in self._harnesses:
                    meaning = (
                        f"{harness.icon} {harness.display_name}"
                        if harness.icon
                        else harness.display_name
                    )
                    yield Static(meaning, classes="session-selection-legend-item")
            with Grid(id="session-selection-help", classes="modal-shortcut-grid"):
                yield Static("↑/↓", classes="modal-shortcut-key")
                yield Static("Navigate", classes="modal-shortcut-description")
                yield Static("Enter", classes="modal-shortcut-key")
                yield Static("Open", classes="modal-shortcut-description")

    def on_mount(self) -> None:
        """Select the first session and focus the search field."""

        session_list = self.query_one("#session-selection-list", OptionList)
        if session_list.options:
            session_list.highlighted = 0
        self.query_one("#session-selection-search", Input).focus()

    def on_input_changed(self, message: Input.Changed) -> None:
        """Filter sessions by harness name or provider-owned session title."""

        if message.input.id != "session-selection-search":
            return

        query = message.value.strip().casefold()
        sessions = tuple(
            session
            for session in self._sessions
            if not query
            or query in session.harness.display_name.casefold()
            or query in session.name.casefold()
        )
        session_list = self.query_one("#session-selection-list", OptionList)
        session_list.clear_options().add_options(
            Option(
                _session_option_prompt(session),
                id=session.id,
            )
            for session in sessions
        )
        session_list.highlighted = 0 if sessions else None
        self.query_one("#session-selection-empty", Static).display = not sessions

    def on_input_submitted(self, message: Input.Submitted) -> None:
        """Open the highlighted filtered session directly from search."""

        if message.input.id != "session-selection-search":
            return

        message.stop()
        session_list = self.query_one("#session-selection-list", OptionList)
        if session_list.highlighted is None:
            return
        try:
            option = session_list.get_option_at_index(session_list.highlighted)
        except OptionDoesNotExist:
            return
        if option.id is not None:
            self.dismiss(option.id)

    def on_option_list_option_selected(
        self,
        message: OptionList.OptionSelected,
    ) -> None:
        """Dismiss with stable AgentHub identity for app-level revalidation."""

        message.stop()
        if message.option_id is not None:
            self.dismiss(message.option_id)

    def action_cancel(self) -> None:
        """Close without changing the active session."""

        self.dismiss(None)

    def action_cursor_up(self) -> None:
        """Move through filtered results without leaving the search field."""

        self.query_one("#session-selection-list", OptionList).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move through filtered results without leaving the search field."""

        self.query_one("#session-selection-list", OptionList).action_cursor_down()
