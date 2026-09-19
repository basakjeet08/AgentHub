"""Persistent tabbed session navigation for AgentHub."""

from collections.abc import Iterable
from enum import StrEnum
from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical
from textual.content import Content
from textual.message import Message
from textual.timer import Timer
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option, OptionDoesNotExist

from agenthub.activity import AgentActivity
from agenthub.harnesses import ANTIGRAVITY, CODEX, DEVIN, OPENCODE, AgentHarness
from agenthub.sessions import AgentSession, SessionKind

_ACTIVE_INDICATOR = "▌"
_INACTIVE_INDICATOR = " "
_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
_ANIMATION_TICK_SECONDS = 0.05
_WORKING_TICKS_PER_FRAME = 2
_ANIMATION_CYCLE_TICKS = 20
_STATIC_ACTIVITY_PRESENTATION = {
    AgentActivity.UNKNOWN: ("·", "Unknown", "$text-muted"),
    AgentActivity.IDLE: ("·", "Idle", "$text-muted"),
    AgentActivity.NEEDS_INPUT: ("!", "Needs Input", "bold $warning"),
    AgentActivity.DONE: ("✓", "Done", "$success"),
}


class SidebarTab(StrEnum):
    """The mutually exclusive session categories shown in the sidebar."""

    LOADED = "loaded"
    UNLOADED = "unloaded"
    SHELLS = "shells"


_TAB_ORDER = (SidebarTab.LOADED, SidebarTab.UNLOADED, SidebarTab.SHELLS)
_TAB_TITLES = {
    SidebarTab.LOADED: "LOADED",
    SidebarTab.UNLOADED: "UNLOADED",
    SidebarTab.SHELLS: "SHELLS",
}
_EMPTY_COPY = {
    SidebarTab.LOADED: "No loaded Agent sessions.",
    SidebarTab.UNLOADED: "No unloaded Agent sessions.",
    SidebarTab.SHELLS: "No Shell sessions.",
}


class SessionSidebar(Vertical):
    """Present one session category without owning activation or lifecycle logic."""

    can_focus = True
    BINDINGS: ClassVar = [
        Binding("left", "previous_tab", "Previous sidebar section", show=False),
        Binding("right", "next_tab", "Next sidebar section", show=False),
    ]

    class SessionSelected(Message):
        """A user selected an AgentHub session."""

        def __init__(self, session_id: str) -> None:
            super().__init__()
            self.session_id = session_id

    def __init__(
        self,
        sessions: Iterable[AgentSession],
        *,
        harnesses: Iterable[AgentHarness] | None = None,
        id: str | None = None,
    ) -> None:
        """Retain application-owned session identity for tab presentation."""

        super().__init__(id=id)
        self._sessions = tuple(sessions)
        self._session_snapshot_value = self._session_snapshot(self._sessions)
        self._selected_tab = SidebarTab.LOADED
        self._cursor_session_ids: dict[SidebarTab, str | None] = {
            tab: None for tab in _TAB_ORDER
        }
        self._active_session_id: str | None = None
        self._pending_cursor_session_id: str | None = None
        self._cursor_visible = True
        self._animation_tick = 0
        self._activity_animation_timer: Timer | None = None
        self._harnesses: tuple[AgentHarness, ...] = (
            (ANTIGRAVITY, CODEX, DEVIN, OPENCODE)
            if harnesses is None
            else tuple(sorted(harnesses, key=lambda harness: harness.display_name.casefold()))
        )

    @property
    def selected_tab(self) -> SidebarTab:
        """Return the currently displayed sidebar category."""

        return self._selected_tab

    @property
    def tab_counts(self) -> dict[SidebarTab, int]:
        """Return current session counts for all sidebar categories."""

        return {tab: len(self._sessions_for_tab(tab)) for tab in _TAB_ORDER}

    @property
    def visible_session_ids(self) -> tuple[str, ...]:
        """Return session IDs in the selected tab's display order."""

        return tuple(session.id for session in self._sessions_for_tab(self._selected_tab))

    def update_sessions(self, sessions: Iterable[AgentSession]) -> None:
        """Refresh category presentation from application-owned session state."""

        next_sessions = tuple(sessions)
        next_snapshot = self._session_snapshot(next_sessions)
        if next_snapshot == self._session_snapshot_value:
            return

        activity_changes = self._activity_only_changes(
            self._session_snapshot_value,
            next_snapshot,
        )
        if activity_changes is not None:
            self._sessions = next_sessions
            self._session_snapshot_value = next_snapshot
            if self.is_mounted:
                self.call_next(self._refresh_activity_rows, activity_changes)
            return

        if self.is_mounted:
            self._remember_visible_cursor()
        self._sessions = next_sessions
        self._session_snapshot_value = next_snapshot
        self._discard_invalid_cursors()
        if self.is_mounted:
            self.call_next(self._refresh_presentation)

    @staticmethod
    def _activity_only_changes(
        current: tuple[tuple[str, str, str, str, SessionKind, bool, AgentActivity], ...],
        updated: tuple[tuple[str, str, str, str, SessionKind, bool, AgentActivity], ...],
    ) -> frozenset[str] | None:
        """Return changed IDs when activity is the only presentation difference."""

        if len(current) != len(updated):
            return None
        changed: set[str] = set()
        for old_row, new_row in zip(current, updated, strict=True):
            if old_row[:-1] != new_row[:-1]:
                return None
            if old_row[-1] is not new_row[-1]:
                changed.add(new_row[0])
        return frozenset(changed)

    @staticmethod
    def _session_snapshot(
        sessions: tuple[AgentSession, ...],
    ) -> tuple[tuple[str, str, str, str, SessionKind, bool, AgentActivity], ...]:
        """Capture the session fields that affect sidebar presentation."""

        return tuple(
            (
                session.id,
                session.name,
                session.harness.display_name,
                session.harness.icon,
                session.kind,
                session.terminal is None,
                session.activity,
            )
            for session in sessions
        )

    @staticmethod
    def _tab_for_session(session: AgentSession) -> SidebarTab:
        """Classify one session from stable kind and current runtime attachment."""

        if session.kind is SessionKind.SHELL:
            return SidebarTab.SHELLS
        if session.terminal is None:
            return SidebarTab.UNLOADED
        return SidebarTab.LOADED

    def _sessions_for_tab(self, tab: SidebarTab) -> tuple[AgentSession, ...]:
        """Return sessions belonging to one tab while preserving manager order."""

        return tuple(
            session for session in self._sessions if self._tab_for_session(session) is tab
        )

    def _option_prompt(self, session: AgentSession) -> Content:
        """Format and style a session independently from the navigation cursor."""

        is_active = session.id == self._active_session_id
        indicator = _ACTIVE_INDICATOR if is_active else _INACTIVE_INDICATOR
        badge = (
            f"{session.harness.icon} "
            if session.harness.icon
            else f"{session.harness.display_name} · "
        )
        if session.kind is SessionKind.AGENT and session.terminal is not None:
            activity_indicator, activity_label, activity_style = (
                self._activity_presentation(session.activity)
            )
            activity_indent = " " * Content(badge).cell_length
            indicator_part: str | tuple[str, str] = (
                (f"{indicator} ", "$secondary") if is_active else f"{indicator} "
            )
            activity_indicator_part: str | tuple[str, str] = (
                (f"\n{indicator} ", "$secondary") if is_active else f"\n{indicator} "
            )
            return Content.assemble(
                indicator_part,
                (badge, "$foreground"),
                (session.name, "bold $foreground" if is_active else "$foreground"),
                activity_indicator_part,
                activity_indent,
                (f"{activity_indicator} {activity_label}", activity_style),
            )
        prompt = Content(f"{indicator} {badge}{session.name}")
        prompt = prompt.stylize("$foreground", 2)
        if is_active:
            prompt = prompt.stylize("$secondary", 0, 1)
        return prompt.stylize("bold", 2) if is_active else prompt

    def _activity_presentation(self, activity: AgentActivity) -> tuple[str, str, str]:
        """Render provider-neutral activity using the shared animation phase."""

        if activity is AgentActivity.WORKING:
            frame = _SPINNER_FRAMES[
                (self._animation_tick // _WORKING_TICKS_PER_FRAME)
                % len(_SPINNER_FRAMES)
            ]
            return frame, "Working...", "$primary"
        return _STATIC_ACTIVITY_PRESENTATION[activity]

    def _options_for_selected_tab(self) -> tuple[Option, ...]:
        """Build selectable options for only the current category."""

        return tuple(
            Option(self._option_prompt(session), id=session.id)
            for session in self._sessions_for_tab(self._selected_tab)
        )

    def compose(self) -> ComposeResult:
        """Compose a fixed tab strip and one category-owned session area."""

        yield Static(">_  AGENTHUB", id="sidebar-brand")
        with Horizontal(id="sidebar-tabs"):
            counts = self.tab_counts
            for tab in _TAB_ORDER:
                yield Static(
                    f"{_TAB_TITLES[tab]} {counts[tab]}",
                    id=f"sidebar-tab-{tab.value}",
                    classes="sidebar-tab selected" if tab is self._selected_tab else "sidebar-tab",
                )
        with Vertical(id="sidebar-session-area"):
            yield OptionList(
                *self._options_for_selected_tab(),
                id="sidebar-session-list",
                classes="session-list",
                compact=True,
            )
            yield Static(
                _EMPTY_COPY[self._selected_tab],
                id="sidebar-empty-state",
                classes="sidebar-empty-state",
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

    def on_mount(self) -> None:
        """Synchronize empty-state and legend visibility after composition."""

        self._activity_animation_timer = self.set_interval(
            _ANIMATION_TICK_SECONDS,
            self._advance_activity_animation,
            name="sidebar-activity-animation",
            pause=True,
        )
        self.call_after_refresh(self._refresh_presentation)

    def _refresh_presentation(self, *, restore_focus: bool | None = None) -> None:
        """Refresh tabs and the selected list while preserving sidebar focus."""

        if not self.is_mounted:
            return

        had_focus = self.has_focus_within if restore_focus is None else restore_focus
        session_list = self.query_one("#sidebar-session-list", OptionList)
        session_list.set_options(self._options_for_selected_tab())

        counts = self.tab_counts
        for tab in _TAB_ORDER:
            tab_widget = self.query_one(f"#sidebar-tab-{tab.value}", Static)
            tab_widget.update(f"{_TAB_TITLES[tab]} {counts[tab]}")
            tab_widget.set_class(tab is self._selected_tab, "selected")

        visible_sessions = self._sessions_for_tab(self._selected_tab)
        empty_state = self.query_one("#sidebar-empty-state", Static)
        empty_state.update(_EMPTY_COPY[self._selected_tab])
        empty_state.display = not visible_sessions
        session_list.display = bool(visible_sessions)

        legends = self.query("#agent-legend").nodes
        if legends:
            legends[0].display = self._selected_tab is not SidebarTab.SHELLS

        if self._cursor_visible or had_focus:
            self._restore_selected_cursor(focus=had_focus)
        else:
            session_list.highlighted = None
        self._sync_activity_animation()

    def _visible_animated_sessions(self) -> tuple[AgentSession, ...]:
        """Return visible Loaded Agents whose activity has animated frames."""

        if self._selected_tab is not SidebarTab.LOADED:
            return ()
        return tuple(
            session
            for session in self._sessions_for_tab(SidebarTab.LOADED)
            if session.activity is AgentActivity.WORKING
        )

    def _sync_activity_animation(self) -> None:
        """Run the single shared timer only while an animated row is visible."""

        timer = self._activity_animation_timer
        if timer is None:
            return
        if self._visible_animated_sessions():
            timer.resume()
        else:
            timer.pause()

    def _advance_activity_animation(self) -> None:
        """Advance shared spinner phases and refresh only frames that changed."""

        previous_tick = self._animation_tick
        self._animation_tick = (self._animation_tick + 1) % _ANIMATION_CYCLE_TICKS
        if (
            previous_tick // _WORKING_TICKS_PER_FRAME
            != self._animation_tick // _WORKING_TICKS_PER_FRAME
        ):
            self._refresh_option_prompts(
                frozenset(
                    session.id
                    for session in self._visible_animated_sessions()
                )
            )

    def _refresh_activity_rows(self, session_ids: frozenset[str]) -> None:
        """Refresh only sessions whose activity state changed."""

        self._refresh_option_prompts(session_ids)
        self._sync_activity_animation()

    def _remember_visible_cursor(self) -> None:
        """Remember the selected tab's highlighted session identity."""

        highlighted_id = self._highlighted_session_id()
        if highlighted_id is not None:
            self._cursor_session_ids[self._selected_tab] = highlighted_id

    def _discard_invalid_cursors(self) -> None:
        """Forget cursor identities that no longer belong to their recorded tab."""

        for tab in _TAB_ORDER:
            remembered_id = self._cursor_session_ids[tab]
            if remembered_id is None:
                continue
            if all(session.id != remembered_id for session in self._sessions_for_tab(tab)):
                self._cursor_session_ids[tab] = None

    def _cursor_target_id(self) -> str | None:
        """Choose the selected tab's cursor using the documented fallback order."""

        sessions = self._sessions_for_tab(self._selected_tab)
        session_ids = {session.id for session in sessions}
        remembered_id = self._cursor_session_ids[self._selected_tab]
        if remembered_id in session_ids:
            return remembered_id
        if self._active_session_id in session_ids:
            return self._active_session_id
        return sessions[0].id if sessions else None

    def _restore_selected_cursor(self, *, focus: bool) -> None:
        """Restore the selected tab cursor and optionally keyboard focus."""

        session_list = self.query_one("#sidebar-session-list", OptionList)
        target_id = self._pending_cursor_session_id or self._cursor_target_id()
        session_list.highlighted = None
        if target_id is not None:
            try:
                session_list.highlighted = session_list.get_option_index(target_id)
                self._cursor_session_ids[self._selected_tab] = target_id
            except OptionDoesNotExist:
                target_id = None
        self._pending_cursor_session_id = None

        if not focus:
            return
        if target_id is None:
            self.focus()
        else:
            session_list.focus()

    def select_tab(self, tab: SidebarTab, *, focus: bool = True) -> None:
        """Select one category without activating a session."""

        if self.is_mounted:
            self._remember_visible_cursor()
        self._selected_tab = tab
        self._cursor_visible = True
        if self.is_mounted:
            self._refresh_presentation()
            if focus and not self.has_focus_within:
                self._restore_selected_cursor(focus=True)

    def action_next_tab(self) -> None:
        """Select the next sidebar category, wrapping at the end."""

        current_index = _TAB_ORDER.index(self._selected_tab)
        self.select_tab(_TAB_ORDER[(current_index + 1) % len(_TAB_ORDER)])

    def action_previous_tab(self) -> None:
        """Select the previous sidebar category, wrapping at the start."""

        current_index = _TAB_ORDER.index(self._selected_tab)
        self.select_tab(_TAB_ORDER[(current_index - 1) % len(_TAB_ORDER)])

    def on_click(self, event: events.Click) -> None:
        """Select a clicked tab without introducing focusable tab controls."""

        widget_id = event.widget.id if event.widget is not None else None
        for tab in _TAB_ORDER:
            if widget_id == f"sidebar-tab-{tab.value}":
                event.stop()
                self.select_tab(tab)
                return

    def set_active(self, session_id: str) -> None:
        """Style the active row without changing tab or navigation cursor."""

        self._active_session_id = session_id
        self._refresh_option_prompts()

    def clear_active(self) -> None:
        """Clear active-row styling without changing navigation state."""

        self._active_session_id = None
        self._refresh_option_prompts()

    def _refresh_option_prompts(
        self,
        session_ids: frozenset[str] | None = None,
    ) -> None:
        """Refresh row styles after the active session changes."""

        if not self.is_mounted:
            return
        session_list = self.query_one("#sidebar-session-list", OptionList)
        for session in self._sessions_for_tab(self._selected_tab):
            if session_ids is not None and session.id not in session_ids:
                continue
            try:
                session_list.replace_option_prompt(session.id, self._option_prompt(session))
            except OptionDoesNotExist:
                continue

    def clear_navigation(self) -> None:
        """Clear the visible cursor without discarding per-tab cursor memory."""

        self._pending_cursor_session_id = None
        self._cursor_visible = False
        self.query_one("#sidebar-session-list", OptionList).highlighted = None

    def move_cursor_to_session(self, session_id: str) -> None:
        """Move sidebar context explicitly without activating the session."""

        session = next((session for session in self._sessions if session.id == session_id), None)
        if session is None:
            return
        target_tab = self._tab_for_session(session)
        self._cursor_session_ids[target_tab] = session_id
        self._pending_cursor_session_id = session_id
        self._selected_tab = target_tab
        self._cursor_visible = True
        if self.is_mounted:
            self._refresh_presentation(restore_focus=False)

    def focus_sidebar(self) -> None:
        """Focus the selected tab and restore its remembered cursor."""

        self._cursor_visible = True
        self._restore_selected_cursor(focus=True)

    @property
    def selected_session_id(self) -> str | None:
        """Return the session ID under the focused sidebar cursor, if any."""

        session_list = self.query_one("#sidebar-session-list", OptionList)
        if not session_list.has_focus:
            return None
        return self._highlighted_session_id()

    def _highlighted_session_id(self) -> str | None:
        """Return the visible cursor's AgentHub session identity."""

        session_list = self.query_one("#sidebar-session-list", OptionList)
        if session_list.highlighted is None:
            return None
        try:
            return session_list.get_option_at_index(session_list.highlighted).id
        except OptionDoesNotExist:
            return None

    def on_option_list_option_highlighted(
        self,
        message: OptionList.OptionHighlighted,
    ) -> None:
        """Remember cursor selection by session ID for the selected tab."""

        if message.option_list.id == "sidebar-session-list" and message.option_id is not None:
            self._cursor_visible = True
            self._cursor_session_ids[self._selected_tab] = message.option_id

    def on_option_list_option_selected(
        self,
        message: OptionList.OptionSelected,
    ) -> None:
        """Translate a Textual option event into an AgentHub session event."""

        message.stop()
        if message.option_id is not None:
            self.post_message(self.SessionSelected(message.option_id))
