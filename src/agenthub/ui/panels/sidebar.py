"""Persistent session navigation and primary application action panel."""

from collections.abc import Iterable
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.content import Content
from textual.message import Message
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option, OptionDoesNotExist

from agenthub.harnesses import ANTIGRAVITY, CODEX, DEVIN, OPENCODE, AgentHarness
from agenthub.sessions import AgentSession, SessionKind
from agenthub.ui.bindings import NUMBERED_SESSION_BINDINGS

_RUNNING_INDICATOR = "●"
_UNLOADED_INDICATOR = "○"


class SessionSidebar(Vertical):
    """Thin session panel with no knowledge of coordination or terminals."""

    can_focus = True
    BINDINGS: ClassVar = list(NUMBERED_SESSION_BINDINGS)

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
        harnesses: Iterable[AgentHarness] | None = None,
        id: str | None = None,
    ) -> None:
        """Retain AgentHub identity and display data for composition."""

        super().__init__(id=id)
        self._agent_sessions = tuple(agent_sessions)
        self._shell_sessions = tuple(shell_sessions)
        self._visible_sessions = self._agent_sessions + self._shell_sessions
        self._agent_session_snapshot = self._session_snapshot(self._agent_sessions)
        self._shell_session_snapshot = self._session_snapshot(self._shell_sessions)
        self._active_session_id: str | None = None
        self._focused_kind: SessionKind | None = None
        self._last_agent_selection_id: str | None = None
        self._last_shell_selection_id: str | None = None
        self._harnesses: tuple[AgentHarness, ...] = (
            (ANTIGRAVITY, CODEX, DEVIN, OPENCODE)
            if harnesses is None
            else tuple(sorted(harnesses, key=lambda h: h.display_name.casefold()))
        )

    @property
    def visible_session_ids(self) -> tuple[str, ...]:
        """Return session IDs in their exact visible order."""

        return tuple(session.id for session in self._visible_sessions)

    def update_sessions(
        self,
        agent_sessions: Iterable[AgentSession],
        *,
        shell_sessions: Iterable[AgentSession] = (),
    ) -> None:
        """Refresh grouped presentation from application-owned session state."""

        next_agents = tuple(agent_sessions)
        next_shells = tuple(shell_sessions)
        next_agent_snapshot = self._session_snapshot(next_agents)
        next_shell_snapshot = self._session_snapshot(next_shells)
        if (
            next_agent_snapshot == self._agent_session_snapshot
            and next_shell_snapshot == self._shell_session_snapshot
        ):
            return

        self._agent_sessions = next_agents
        self._shell_sessions = next_shells
        self._visible_sessions = self._agent_sessions + self._shell_sessions
        self._agent_session_snapshot = next_agent_snapshot
        self._shell_session_snapshot = next_shell_snapshot
        if self.is_mounted:
            self.call_next(self._recompose_sessions)

    @staticmethod
    def _session_snapshot(
        sessions: tuple[AgentSession, ...],
    ) -> tuple[tuple[str, str, str, str, SessionKind, bool], ...]:
        """Capture the session fields that affect sidebar presentation."""

        return tuple(
            (
                session.id,
                session.name,
                session.harness.display_name,
                session.harness.icon,
                session.kind,
                session.terminal is None,
            )
            for session in sessions
        )

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
    ) -> Content:
        """Format and style a session independently from the navigation cursor."""

        is_active = session.id == self._active_session_id
        is_unloaded = session.kind is SessionKind.AGENT and session.terminal is None
        indicator = _UNLOADED_INDICATOR if is_unloaded else _RUNNING_INDICATOR
        indicator_style = (
            "$success" if is_active else "$text-muted" if is_unloaded else "$foreground"
        )
        badge = (
            f"{session.harness.icon} "
            if session.harness.icon
            else f"{session.harness.display_name} · "
        )
        prompt = Content(f"{indicator} {badge}{session.name}")
        prompt = prompt.stylize(indicator_style, 0, 1).stylize("$foreground", 2)
        return prompt.stylize("bold", 2) if is_active else prompt

    def _refresh_option_prompts(self) -> None:
        """Refresh row styles after the active session changes."""

        if not self.is_mounted:
            return
        for session_list in self.query(OptionList):
            is_agent_list = session_list.id == "agent-session-list"
            sessions = self._agent_sessions if is_agent_list else self._shell_sessions
            for session in sessions:
                try:
                    session_list.replace_option_prompt(
                        session.id,
                        self._option_prompt(session),
                    )
                except OptionDoesNotExist:
                    # Session data may lead the mounted options during recomposition.
                    continue

    def compose(self) -> ComposeResult:
        """Compose persistent agent and shell groups using the configured split."""

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
            if self._harnesses:
                with Grid(id="agent-legend", classes="sidebar-legend"):
                    for harness in self._harnesses:
                        label = (
                            f"{harness.icon} {harness.display_name}"
                            if harness.icon
                            else harness.display_name
                        )
                        yield Static(label, classes="legend-item")
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
                        self._option_prompt(session),
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
        self._refresh_option_prompts()
        for session_list in self.query(OptionList):
            session_list.highlighted = None
            try:
                session_list.highlighted = session_list.get_option_index(session_id)
            except OptionDoesNotExist:
                continue

    def clear_active(self) -> None:
        """Clear the retained active identity and all visible highlights."""

        self._active_session_id = None
        self._refresh_option_prompts()
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

        self._focus_session_list(
            "#agent-session-list",
            SessionKind.AGENT,
            self._last_agent_selection_id,
        )

    def focus_shells(self) -> None:
        """Focus the shell-session list when it contains selectable rows."""

        self._focus_session_list(
            "#shell-session-list",
            SessionKind.SHELL,
            self._last_shell_selection_id,
        )

    def _focus_session_list(
        self,
        selector: str,
        kind: SessionKind,
        previous_selection_id: str | None,
    ) -> None:
        """Focus one list and ensure its navigation cursor is restored or active."""

        self._focused_kind = kind
        session_list = self.query_one(selector, OptionList)
        if not session_list.options:
            self.focus()
            return

        for other_list in self.query(OptionList):
            if other_list is not session_list:
                other_list.highlighted = None

        target_highlight: int | None = None
        if self._active_session_id is not None:
            try:
                target_highlight = session_list.get_option_index(self._active_session_id)
            except OptionDoesNotExist:
                target_highlight = None

        if target_highlight is None and previous_selection_id is not None:
            try:
                target_highlight = session_list.get_option_index(previous_selection_id)
            except OptionDoesNotExist:
                target_highlight = None

        if target_highlight is None:
            target_highlight = 0

        session_list.highlighted = target_highlight
        session_list.focus()

    def select_numbered_agent(self, number: int) -> None:
        """Move agent cursor only; never activate."""

        index = number - 1
        agent_list = self.query_one("#agent-session-list", OptionList)
        if 0 <= index < len(self._agent_sessions):
            for other_list in self.query(OptionList):
                if other_list is not agent_list:
                    other_list.highlighted = None
            agent_list.highlighted = index
            self._last_agent_selection_id = self._agent_sessions[index].id
            agent_list.focus()

    @property
    def selected_session_id(self) -> str | None:
        """Return the session ID under the current sidebar cursor, if any."""

        for session_list in self.query(OptionList):
            if session_list.has_focus and session_list.highlighted is not None:
                try:
                    option = session_list.get_option_at_index(session_list.highlighted)
                    return option.id
                except OptionDoesNotExist:
                    continue
        return None

    def action_select_numbered_session(self, number: int) -> None:
        """Focus an agent ordinal when the agent list is active."""

        agent_list = self.query_one("#agent-session-list", OptionList)
        shell_list = self.query_one("#shell-session-list", OptionList)
        if agent_list.has_focus:
            focused_kind = SessionKind.AGENT
        elif shell_list.has_focus:
            focused_kind = SessionKind.SHELL
        else:
            focused_kind = self._focused_kind

        if focused_kind is SessionKind.AGENT:
            self.select_numbered_agent(number)

    def on_option_list_option_highlighted(
        self,
        message: OptionList.OptionHighlighted,
    ) -> None:
        """Remember previous cursor selection by session ID for the focused list."""

        if message.option_id is None:
            return
        if message.option_list.id == "agent-session-list":
            self._last_agent_selection_id = message.option_id
        elif message.option_list.id == "shell-session-list":
            self._last_shell_selection_id = message.option_id

    def on_option_list_option_selected(
        self,
        message: OptionList.OptionSelected,
    ) -> None:
        """Translate a Textual option event into an AgentHub session event."""

        message.stop()
        if message.option_id is not None:
            self.post_message(self.SessionSelected(message.option_id))
