"""Session navigation panel that reports application session identities."""

from collections.abc import Iterable

from textual.message import Message
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from agenthub.sessions import AgentSession


class SessionSidebar(OptionList):
    """Thin session panel with no knowledge of coordination or terminals."""

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
        """Build options from AgentHub identity and display data only."""

        super().__init__(
            *(Option(session.name, id=session.id) for session in sessions),
            id=id,
        )

    def set_active(self, session_id: str) -> None:
        """Highlight the row corresponding to the active session."""

        self.highlighted = self.get_option_index(session_id)

    def on_option_list_option_selected(
        self,
        message: OptionList.OptionSelected,
    ) -> None:
        """Translate a Textual option event into an AgentHub session event."""

        message.stop()
        if message.option_id is not None:
            self.post_message(self.SessionSelected(message.option_id))
