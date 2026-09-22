"""Unified picker for opening a managed Agent or Shell session."""

from collections.abc import Iterable
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from agenthub.sessions import AgentSession


class SessionPickerModal(ModalScreen[str]):
    """Return the AgentHub ID of a user-selected openable session."""

    CSS_PATH = "../styles/modals/session_picker.tcss"
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
            {session.harness.id: session.harness for session in self._sessions}.values()
        )

    def compose(self) -> ComposeResult:
        """Compose the unified Agent and Shell picker."""

        options = []
        for session in self._sessions:
            options.append(
                Option(
                    f"{session.harness.icon} {session.name}",
                    id=session.id,
                )
            )

        with Vertical(id="session-picker-dialog"):
            with Horizontal(id="session-picker-header"):
                yield Label("Open Session", id="session-picker-title")
                with Horizontal(
                    id="session-picker-cancel",
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
                id="session-picker-copy",
                classes="muted",
            )
            yield Input(
                placeholder="Search by harness or session title",
                id="session-picker-search",
            )
            yield OptionList(*options, id="session-picker-list")
            yield Static(
                "No matching sessions.",
                id="session-picker-empty",
                classes="muted",
            )
            yield Static(
                "Harnesses",
                id="session-picker-legend-title",
                classes="muted",
            )
            with Grid(id="session-picker-legend"):
                for harness in self._harnesses:
                    yield Static(
                        f"{harness.icon} {harness.display_name}",
                        classes="session-picker-legend-item",
                    )
            with Grid(id="session-picker-help", classes="modal-shortcut-grid"):
                yield Static("↑/↓", classes="modal-shortcut-key")
                yield Static("Navigate", classes="modal-shortcut-description")
                yield Static("Enter", classes="modal-shortcut-key")
                yield Static("Open", classes="modal-shortcut-description")

    def on_mount(self) -> None:
        """Select the first session and focus the search field."""

        session_list = self.query_one("#session-picker-list", OptionList)
        if session_list.options:
            session_list.highlighted = 0

        self.query_one("#session-picker-search", Input).focus()

    def on_input_changed(self, message: Input.Changed) -> None:
        """Filter sessions by harness name or session title."""

        options = []
        query = message.value.strip().casefold()
        for session in self._sessions:
            matches = (
                not query
                or query in session.harness.display_name.casefold()
                or query in session.name.casefold()
            )

            if matches:
                options.append(
                    Option(
                        f"{session.harness.icon} {session.name}",
                        id=session.id,
                    )
                )

        session_list = self.query_one("#session-picker-list", OptionList)
        session_list.clear_options().add_options(options)
        session_list.highlighted = 0 if options else None
        self.query_one("#session-picker-empty", Static).display = not options

    def on_input_submitted(self, message: Input.Submitted) -> None:
        """Open the highlighted filtered session directly from search."""

        message.stop()
        self.query_one("#session-picker-list", OptionList).action_select()

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

        self.query_one("#session-picker-list", OptionList).action_cursor_up()

    def action_cursor_down(self) -> None:
        """Move through filtered results without leaving the search field."""

        self.query_one("#session-picker-list", OptionList).action_cursor_down()
