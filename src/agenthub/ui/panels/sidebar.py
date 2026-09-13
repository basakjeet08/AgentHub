"""Persistent session navigation and primary application action panel."""

from collections.abc import Iterable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Button, Label, OptionList, Static
from textual.widgets.option_list import Option

from agenthub.sessions import AgentSession


class SessionSidebar(Vertical):
    """Thin session panel with no knowledge of coordination or terminals."""

    class NewSessionRequested(Message):
        """The user invoked the sidebar's primary session action."""

    class SessionSelected(Message):
        """A user selected an AgentHub session."""

        def __init__(self, session_id: str) -> None:
            super().__init__()
            self.session_id = session_id

    def __init__(
        self,
        sessions: Iterable[AgentSession],
        *,
        id: str | None = None,
    ) -> None:
        """Retain AgentHub identity and display data for composition."""

        super().__init__(id=id)
        self._sessions = tuple(sessions)

    def compose(self) -> ComposeResult:
        """Keep the empty sidebar sparse and add navigation only when useful."""

        yield Static("AGENTHUB", id="sidebar-brand")
        yield Button("＋ New Session", id="sidebar-new-session")
        if self._sessions:
            yield Label("SESSIONS", id="sidebar-section-title", classes="section-title")
            yield OptionList(
                *(Option(session.name, id=session.id) for session in self._sessions),
                id="session-list",
            )

    def set_active(self, session_id: str) -> None:
        """Highlight the row corresponding to the active session."""

        session_list = self.query_one("#session-list", OptionList)
        session_list.highlighted = session_list.get_option_index(session_id)

    def focus_primary(self) -> None:
        """Focus sessions when present, otherwise the New Session action."""

        session_lists = self.query(OptionList).nodes
        if session_lists:
            session_lists[0].focus()
        else:
            self.query_one("#sidebar-new-session", Button).focus()

    def on_button_pressed(self, message: Button.Pressed) -> None:
        """Translate the sidebar CTA into application-level intent."""

        if message.button.id == "sidebar-new-session":
            message.stop()
            self.post_message(self.NewSessionRequested())

    def on_option_list_option_selected(
        self,
        message: OptionList.OptionSelected,
    ) -> None:
        """Translate a Textual option event into an AgentHub session event."""

        message.stop()
        if message.option_id is not None:
            self.post_message(self.SessionSelected(message.option_id))
