"""Persistent session navigation and primary application action panel."""

from collections.abc import Iterable, Mapping
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option, OptionDoesNotExist

from agenthub.sessions import AgentSession, SessionKind
from agenthub.ui.bindings import NUMBERED_SESSION_BINDINGS


class SessionSidebar(Vertical):
    """Thin session panel with no knowledge of coordination or terminals."""

    can_focus = True
    BINDINGS: ClassVar = list(NUMBERED_SESSION_BINDINGS)

    class SessionSelected(Message):
        """A user selected an AgentHub session."""

        def __init__(self, session_id: str) -> None:
            super().__init__()
            self.session_id = session_id

    class ShellSlotSelected(Message):
        """A user selected a numbered shell slot."""

        def __init__(self, slot: int) -> None:
            super().__init__()
            self.slot = slot

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
        self._focused_kind: SessionKind | None = None

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
        else:
            self.clear_active()

    def _option_prompt(
        self,
        session: AgentSession,
        *,
        shortcut: int | None = None,
    ) -> str:
        """Format a session, optionally showing its persistent shell slot."""

        prefix = f"[ {shortcut} ] " if shortcut is not None else ""
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
                        self._option_prompt(
                            session,
                            shortcut=index if index <= 9 else None,
                        ),
                        id=session.id,
                    )
                    for index, session in enumerate(self._agent_sessions, start=1)
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
                        self._option_prompt(
                            session,
                            shortcut=self._shortcut_slots.get(session.id),
                        ),
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

    def clear_active(self) -> None:
        """Clear the retained active identity and all visible highlights."""

        self._active_session_id = None
        for session_list in self.query(OptionList):
            session_list.highlighted = None

    def focus_primary(self) -> None:
        """Focus the first session group, or the empty sidebar itself."""

        for kind, session_list in (
            (SessionKind.AGENT, self.query_one("#agent-session-list", OptionList)),
            (SessionKind.SHELL, self.query_one("#shell-session-list", OptionList)),
        ):
            if session_list.options:
                self._focused_kind = kind
                session_list.focus()
                return
        self.focus()

    def focus_agents(self) -> None:
        """Focus the agent-session list when it contains selectable rows."""

        self._focus_session_list("#agent-session-list", SessionKind.AGENT)

    def focus_shells(self) -> None:
        """Focus the shell-session list when it contains selectable rows."""

        self._focus_session_list("#shell-session-list", SessionKind.SHELL)

    def _focus_session_list(self, selector: str, kind: SessionKind) -> None:
        """Focus one list and ensure its navigation cursor is immediately visible."""

        self._focused_kind = kind
        session_list = self.query_one(selector, OptionList)
        if session_list.options:
            for other_list in self.query(OptionList):
                other_list.highlighted = None
            session_list.highlighted = 0
            session_list.focus()
        else:
            self.focus()

    def action_select_numbered_session(self, number: int) -> None:
        """Activate an agent ordinal or request a persistent shell slot."""

        agent_list = self.query_one("#agent-session-list", OptionList)
        shell_list = self.query_one("#shell-session-list", OptionList)
        if agent_list.has_focus:
            focused_kind = SessionKind.AGENT
        elif shell_list.has_focus:
            focused_kind = SessionKind.SHELL
        else:
            focused_kind = self._focused_kind

        if focused_kind is SessionKind.AGENT:
            index = number - 1
            if 0 <= index < len(self._agent_sessions):
                self.post_message(self.SessionSelected(self._agent_sessions[index].id))
            return

        if focused_kind is SessionKind.SHELL:
            session_id = next(
                (
                    session_id
                    for session_id, slot in self._shortcut_slots.items()
                    if slot == number
                ),
                None,
            )
            if session_id is None:
                self.post_message(self.ShellSlotSelected(number))
            else:
                self.post_message(self.SessionSelected(session_id))

    def on_option_list_option_selected(
        self,
        message: OptionList.OptionSelected,
    ) -> None:
        """Translate a Textual option event into an AgentHub session event."""

        message.stop()
        if message.option_id is not None:
            self.post_message(self.SessionSelected(message.option_id))
