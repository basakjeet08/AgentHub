"""Persistent session navigation and primary application action panel."""

from collections.abc import Iterable, Mapping

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option, OptionDoesNotExist

from agenthub.sessions import AgentSession


class SessionSidebar(Vertical):
    """Thin session panel with no knowledge of coordination or terminals."""

    can_focus = True

    class SessionSelected(Message):
        """A user selected an AgentHub session."""

        def __init__(self, session_id: str) -> None:
            super().__init__()
            self.session_id = session_id

    def __init__(
        self,
        agent_sessions: Iterable[AgentSession],
        *,
        shell_sessions: Iterable[AgentSession] = (),
        shortcut_slots: Mapping[str, int] | None = None,
        id: str | None = None,
    ) -> None:
        """Retain AgentHub identity and display data for composition."""

        super().__init__(id=id)
        self._agent_sessions = tuple(agent_sessions)
        self._shell_sessions = tuple(shell_sessions)
        self._visible_sessions = self._agent_sessions + self._shell_sessions
        self._shortcut_slots = dict(shortcut_slots or {})
        self._active_session_id: str | None = None

    @property
    def visible_session_ids(self) -> tuple[str, ...]:
        """Return session IDs in their exact visible order."""

        return tuple(session.id for session in self._visible_sessions)

    @property
    def shortcut_slots(self) -> dict[str, int]:
        """Return the visible session-to-shortcut mapping."""

        return self._shortcut_slots.copy()

    def update_sessions(
        self,
        agent_sessions: Iterable[AgentSession],
        *,
        shell_sessions: Iterable[AgentSession] = (),
        shortcut_slots: Mapping[str, int] | None = None,
    ) -> None:
        """Refresh grouped presentation from application-owned session state."""

        next_agents = tuple(agent_sessions)
        next_shells = tuple(shell_sessions)
        next_shortcuts = dict(shortcut_slots or {})
        if (
            next_agents == self._agent_sessions
            and next_shells == self._shell_sessions
            and next_shortcuts == self._shortcut_slots
        ):
            return

        self._agent_sessions = next_agents
        self._shell_sessions = next_shells
        self._visible_sessions = self._agent_sessions + self._shell_sessions
        self._shortcut_slots = next_shortcuts
        if self.is_mounted:
            self.call_next(self._recompose_sessions)

    async def _recompose_sessions(self) -> None:
        """Rebuild session rows before restoring the active-row highlight."""

        await self.recompose()
        if self._active_session_id is not None:
            self.set_active(self._active_session_id)

    def _option_prompt(
        self,
        session: AgentSession,
        *,
        show_shortcut: bool = False,
    ) -> str:
        """Format a session, optionally showing its persistent shell slot."""

        slot = self._shortcut_slots.get(session.id) if show_shortcut else None
        prefix = f"{slot}  " if slot is not None else ""
        return f"{prefix}{session.harness.display_name} · {session.name}"

    def compose(self) -> ComposeResult:
        """Compose persistent, equally sized agent and shell session groups."""

        yield Static(">_  AGENTHUB", id="sidebar-brand")
        with Vertical(id="agent-section", classes="sidebar-section"):
            with Horizontal(classes="sidebar-section-header"):
                yield Label(
                    "AGENTS",
                    id="agent-section-title",
                    classes="sidebar-section-title section-title",
                )
                yield Static(
                    "Ctrl+A",
                    id="agent-section-shortcut",
                    classes="sidebar-section-shortcut",
                )
            yield OptionList(
                *(
                    Option(
                        self._option_prompt(session),
                        id=session.id,
                    )
                    for session in self._agent_sessions
                ),
                id="agent-session-list",
                classes="session-list",
            )
        with Vertical(id="shell-section", classes="sidebar-section"):
            with Horizontal(classes="sidebar-section-header"):
                yield Label(
                    "SHELLS",
                    id="shell-section-title",
                    classes="sidebar-section-title section-title",
                )
                yield Static(
                    "Ctrl+S",
                    id="shell-section-shortcut",
                    classes="sidebar-section-shortcut",
                )
            yield OptionList(
                *(
                    Option(
                        self._option_prompt(session, show_shortcut=True),
                        id=session.id,
                    )
                    for session in self._shell_sessions
                ),
                id="shell-session-list",
                classes="session-list",
            )

    def set_active(self, session_id: str) -> None:
        """Highlight the row corresponding to the active session."""

        self._active_session_id = session_id
        for session_list in self.query(OptionList):
            session_list.highlighted = None
            try:
                session_list.highlighted = session_list.get_option_index(session_id)
            except OptionDoesNotExist:
                continue

    def focus_primary(self) -> None:
        """Focus the first session group, or the empty sidebar itself."""

        for session_list in self.query(OptionList):
            if session_list.options:
                session_list.focus()
                return
        self.focus()

    def focus_agents(self) -> None:
        """Focus the agent-session list when it contains selectable rows."""

        self._focus_session_list("#agent-session-list")

    def focus_shells(self) -> None:
        """Focus the shell-session list when it contains selectable rows."""

        self._focus_session_list("#shell-session-list")

    def _focus_session_list(self, selector: str) -> None:
        """Focus one list and ensure its navigation cursor is immediately visible."""

        session_list = self.query_one(selector, OptionList)
        if session_list.options:
            for other_list in self.query(OptionList):
                other_list.highlighted = None
            session_list.highlighted = 0
            session_list.focus()
        else:
            self.focus()

    def on_option_list_option_selected(
        self,
        message: OptionList.OptionSelected,
    ) -> None:
        """Translate a Textual option event into an AgentHub session event."""

        message.stop()
        if message.option_id is not None:
            self.post_message(self.SessionSelected(message.option_id))
