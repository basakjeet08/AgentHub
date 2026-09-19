"""Integration coverage for tabbed sidebar presentation and navigation."""

from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

from textual.app import App, ComposeResult
from textual.content import Content
from textual.widgets import OptionList, Static

from agenthub.activity import AgentActivity
from agenthub.harnesses import ANTIGRAVITY, CODEX, DEVIN, FISH, OPENCODE, AgentHarness
from agenthub.native_sessions import NativeSession
from agenthub.sessions import AgentSession, SessionKind, SessionManager
from agenthub.ui import SessionSidebar, SidebarTab


class SidebarTestApp(App):
    """Mount a sidebar without mounting the sessions' terminal widgets."""

    CSS_PATH = Path(__file__).parents[2] / "src/agenthub/ui/panels/sidebar.tcss"

    def __init__(self, sessions: tuple[AgentSession, ...]) -> None:
        super().__init__()
        self.sessions = sessions
        self.selected_session_id: str | None = None

    def compose(self) -> ComposeResult:
        yield SessionSidebar(self.sessions)

    def on_session_sidebar_session_selected(
        self,
        message: SessionSidebar.SessionSelected,
    ) -> None:
        self.selected_session_id = message.session_id


def _sessions(
    harness: AgentHarness,
    kind: SessionKind,
    *names: str,
) -> tuple[AgentSession, ...]:
    manager = SessionManager()
    return tuple(
        manager.create(name=name, kind=kind, cwd=Path.cwd(), harness=harness)
        for name in names
    )


def _unloaded_session(
    manager: SessionManager,
    harness: AgentHarness,
    native_id: str,
    name: str,
) -> AgentSession:
    return manager.add_discovered(
        native_session=NativeSession(harness.id, native_id, name, Path.cwd()),
        harness=harness,
    )


async def test_sidebar_always_shows_three_counted_tabs_and_loaded_default() -> None:
    app = SidebarTestApp(())

    async with app.run_test(size=(100, 36)) as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        session_list = sidebar.query_one("#sidebar-session-list", OptionList)
        empty_state = sidebar.query_one("#sidebar-empty-state", Static)

        assert sidebar.selected_tab is SidebarTab.LOADED
        assert sidebar.tab_counts == {
            SidebarTab.LOADED: 0,
            SidebarTab.UNLOADED: 0,
            SidebarTab.SHELLS: 0,
        }
        assert [
            str(sidebar.query_one(f"#sidebar-tab-{tab.value}", Static).content)
            for tab in SidebarTab
        ] == ["LOADED 0", "UNLOADED 0", "SHELLS 0"]
        assert sidebar.query_one("#sidebar-tab-loaded", Static).has_class("selected")
        assert not session_list.display
        assert empty_state.display
        assert empty_state.content == "No loaded Agent sessions."
        assert len(sidebar.query(OptionList).nodes) == 1


async def test_sidebar_classifies_sessions_and_cycles_tabs(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    loaded = manager.create(
        name="Loaded Agent",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    unloaded = _unloaded_session(manager, sleeping_harness, "native-1", "Unloaded Agent")
    shell = manager.create(
        name="Shell",
        kind=SessionKind.SHELL,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    app = SidebarTestApp((loaded, unloaded, shell))

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        session_list = sidebar.query_one("#sidebar-session-list", OptionList)

        assert sidebar.tab_counts == {
            SidebarTab.LOADED: 1,
            SidebarTab.UNLOADED: 1,
            SidebarTab.SHELLS: 1,
        }
        assert sidebar.visible_session_ids == (loaded.id,)

        sidebar.focus_sidebar()
        await pilot.pause()
        assert session_list.has_focus
        await pilot.press("right")
        assert sidebar.selected_tab is SidebarTab.UNLOADED
        assert sidebar.visible_session_ids == (unloaded.id,)
        assert session_list.highlighted == 0

        await pilot.press("right")
        assert sidebar.selected_tab is SidebarTab.SHELLS
        assert sidebar.visible_session_ids == (shell.id,)

        await pilot.press("right")
        assert sidebar.selected_tab is SidebarTab.LOADED
        assert sidebar.visible_session_ids == (loaded.id,)

        await pilot.press("left")
        assert sidebar.selected_tab is SidebarTab.SHELLS
        await pilot.press("right")
        assert sidebar.selected_tab is SidebarTab.LOADED


async def test_arrows_and_enter_only_navigate_selected_tab(
    sleeping_harness: AgentHarness,
) -> None:
    loaded = _sessions(sleeping_harness, SessionKind.AGENT, "First", "Second")
    shells = _sessions(sleeping_harness, SessionKind.SHELL, "Shell One", "Shell Two")
    app = SidebarTestApp((*loaded, *shells))

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        session_list = sidebar.query_one("#sidebar-session-list", OptionList)

        sidebar.focus_sidebar()
        assert sidebar.visible_session_ids == tuple(session.id for session in loaded)
        await pilot.press("down")
        assert session_list.highlighted == 1
        await pilot.press("enter")
        assert app.selected_session_id == loaded[1].id

        await pilot.press("right", "right")
        assert sidebar.selected_tab is SidebarTab.SHELLS
        assert sidebar.visible_session_ids == tuple(session.id for session in shells)
        assert session_list.highlighted == 0
        await pilot.press("down", "enter")
        assert app.selected_session_id == shells[1].id


async def test_sidebar_restores_independent_cursors_by_session_id(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    loaded = tuple(
        manager.create(
            name=name,
            kind=SessionKind.AGENT,
            cwd=Path.cwd(),
            harness=sleeping_harness,
        )
        for name in ("Loaded A", "Loaded B", "Loaded C")
    )
    unloaded = tuple(
        _unloaded_session(manager, sleeping_harness, f"native-{index}", name)
        for index, name in enumerate(("Unloaded A", "Unloaded B"))
    )
    shell = manager.create(
        name="Shell",
        kind=SessionKind.SHELL,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    app = SidebarTestApp((*loaded, *unloaded, shell))

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        session_list = sidebar.query_one("#sidebar-session-list", OptionList)
        sidebar.focus_sidebar()

        await pilot.press("down")
        assert sidebar.selected_session_id == loaded[1].id
        await pilot.press("right", "down")
        assert sidebar.selected_session_id == unloaded[1].id
        await pilot.press("right")
        assert sidebar.selected_session_id == shell.id
        await pilot.press("right")
        assert sidebar.selected_session_id == loaded[1].id
        assert session_list.highlighted == session_list.get_option_index(loaded[1].id)
        await pilot.press("right")
        assert sidebar.selected_session_id == unloaded[1].id


async def test_refresh_preserves_cursor_identity_and_invalidates_moved_membership(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    first = manager.create(
        name="First",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    moving = manager.create(
        name="Moving",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    moving.native_session_id = "native-moving"
    app = SidebarTestApp((first, moving))

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        sidebar.focus_sidebar()
        await pilot.press("down")
        assert sidebar.selected_session_id == moving.id

        manager.detach_terminal(moving.id)
        sidebar.update_sessions(manager.sessions)
        await pilot.pause()

        assert sidebar.selected_tab is SidebarTab.LOADED
        assert sidebar.visible_session_ids == (first.id,)
        assert sidebar.selected_session_id == first.id
        assert sidebar.tab_counts[SidebarTab.UNLOADED] == 1

        await pilot.press("right")
        assert sidebar.visible_session_ids == (moving.id,)
        assert sidebar.selected_session_id == moving.id


async def test_active_style_remains_independent_from_cursor(
    sleeping_harness: AgentHarness,
) -> None:
    sessions = _sessions(sleeping_harness, SessionKind.AGENT, "Active", "Highlighted")
    app = SidebarTestApp(sessions)

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        session_list = sidebar.query_one("#sidebar-session-list", OptionList)
        sidebar.set_active(sessions[0].id)
        sidebar.focus_sidebar()
        await pilot.press("down")

        assert sidebar.selected_session_id == sessions[1].id
        active_lines = str(session_list.get_option(sessions[0].id).prompt).splitlines()
        inactive_lines = str(session_list.get_option(sessions[1].id).prompt).splitlines()
        assert all(line.startswith("▌") for line in active_lines)
        assert all(not line.startswith("▌") for line in inactive_lines)


async def test_loaded_agent_activity_updates_and_unloaded_agent_hides_it(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    loaded = manager.create(
        name="Loaded",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    unloaded = _unloaded_session(manager, sleeping_harness, "native", "Unloaded")
    shell = manager.create(
        name="Shell",
        kind=SessionKind.SHELL,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    app = SidebarTestApp(manager.sessions)

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        session_list = sidebar.query_one("#sidebar-session-list", OptionList)

        expected_labels = {
            AgentActivity.UNKNOWN: "· Unknown",
            AgentActivity.IDLE: "· Idle",
            AgentActivity.WORKING: "⠋ Working...",
            AgentActivity.NEEDS_INPUT: "! Needs Input",
            AgentActivity.DONE: "✓ Done",
        }
        for activity, label in expected_labels.items():
            loaded.activity = activity
            sidebar._animation_tick = 0
            sidebar.update_sessions(manager.sessions)
            await pilot.pause()
            lines = str(session_list.get_option(loaded.id).prompt).splitlines()
            assert lines == [
                "  Test Sleeper · Loaded",
                f"  {' ' * Content('Test Sleeper · ').cell_length}{label}",
            ]

        sidebar.select_tab(SidebarTab.UNLOADED)
        unloaded_prompt = str(session_list.get_option(unloaded.id).prompt)
        assert "Unknown" not in unloaded_prompt
        sidebar.select_tab(SidebarTab.SHELLS)
        shell_prompt = str(session_list.get_option(shell.id).prompt)
        assert "Unknown" not in shell_prompt


async def test_activity_text_aligns_with_title_after_wide_provider_icon() -> None:
    manager = SessionManager()
    session = manager.create(
        name="Aligned title",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=CODEX,
    )
    session.activity = AgentActivity.WORKING
    app = SidebarTestApp(manager.sessions)

    async with app.run_test() as pilot:
        await pilot.pause()
        option = app.query_one("#sidebar-session-list", OptionList).get_option(session.id)
        title_line, activity_line = str(option.prompt).splitlines()

        title_prefix = title_line[: title_line.index("Aligned title")]
        activity_prefix = activity_line[: activity_line.index("⠋")]
        assert Content(title_prefix).cell_length == Content(activity_prefix).cell_length


async def test_active_sessions_share_one_sidebar_animation_timer(
    sleeping_harness: AgentHarness,
) -> None:
    first, second = _sessions(
        sleeping_harness,
        SessionKind.AGENT,
        "First Active Agent",
        "Second Active Agent",
    )
    first.activity = AgentActivity.WORKING
    second.activity = AgentActivity.WORKING
    app = SidebarTestApp((first, second))

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        session_list = sidebar.query_one("#sidebar-session-list", OptionList)
        timer = sidebar._activity_animation_timer
        assert timer is not None
        timer.pause()
        matching_timers = [
            candidate
            for candidate in sidebar._timers
            if candidate.name == "sidebar-activity-animation"
        ]
        assert matching_timers == [timer]

        sidebar._animation_tick = 0
        sidebar._refresh_option_prompts()
        assert "⠋ Working..." in str(session_list.get_option(first.id).prompt)
        assert "⠋ Working..." in str(session_list.get_option(second.id).prompt)

        sidebar._advance_activity_animation()
        sidebar._advance_activity_animation()
        assert "⠙ Working..." in str(session_list.get_option(first.id).prompt)
        assert "⠙ Working..." in str(session_list.get_option(second.id).prompt)


async def test_static_activity_does_not_animate(
    sleeping_harness: AgentHarness,
) -> None:
    needs_input, done = _sessions(
        sleeping_harness,
        SessionKind.AGENT,
        "Needs Input Agent",
        "Done Agent",
    )
    needs_input.activity = AgentActivity.NEEDS_INPUT
    done.activity = AgentActivity.DONE
    app = SidebarTestApp((needs_input, done))

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        session_list = sidebar.query_one("#sidebar-session-list", OptionList)
        before = tuple(str(option.prompt) for option in session_list.options)

        for _ in range(10):
            sidebar._advance_activity_animation()

        assert tuple(str(option.prompt) for option in session_list.options) == before
        assert "! Needs Input" in before[0]
        assert "✓ Done" in before[1]


async def test_activity_change_refreshes_only_the_changed_session(
    sleeping_harness: AgentHarness,
    monkeypatch,
) -> None:
    first, second = _sessions(
        sleeping_harness,
        SessionKind.AGENT,
        "First",
        "Second",
    )
    first.activity = AgentActivity.IDLE
    second.activity = AgentActivity.IDLE
    app = SidebarTestApp((first, second))

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        session_list = sidebar.query_one("#sidebar-session-list", OptionList)
        replace_prompt = Mock(wraps=session_list.replace_option_prompt)
        monkeypatch.setattr(session_list, "replace_option_prompt", replace_prompt)

        second.activity = AgentActivity.DONE
        sidebar.update_sessions((first, second))
        await pilot.pause()

        assert replace_prompt.call_count == 1
        assert replace_prompt.call_args.args[0] == second.id
        assert "· Idle" in str(session_list.get_option(first.id).prompt)
        assert "✓ Done" in str(session_list.get_option(second.id).prompt)


async def test_empty_tabs_keep_focus_and_show_category_copy(
    sleeping_harness: AgentHarness,
) -> None:
    loaded = _sessions(sleeping_harness, SessionKind.AGENT, "Loaded")
    app = SidebarTestApp(loaded)

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        empty_state = sidebar.query_one("#sidebar-empty-state", Static)
        sidebar.focus_sidebar()

        await pilot.press("right")
        assert sidebar.selected_tab is SidebarTab.UNLOADED
        assert sidebar.has_focus
        assert empty_state.content == "No unloaded Agent sessions."

        await pilot.press("right")
        assert sidebar.selected_tab is SidebarTab.SHELLS
        assert sidebar.has_focus
        assert empty_state.content == "No Shell sessions."


async def test_harness_legend_is_shared_by_agent_tabs_and_hidden_for_shells() -> None:
    sessions = _sessions(FISH, SessionKind.SHELL, "Shell")
    app = SidebarTestApp(sessions)

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        legend = sidebar.query_one("#agent-legend")
        labels = [str(item.content) for item in legend.query(".legend-item")]
        assert labels == [
            f"{ANTIGRAVITY.icon} {ANTIGRAVITY.display_name}",
            f"{CODEX.icon} {CODEX.display_name}",
            f"{DEVIN.icon} {DEVIN.display_name}",
            f"{OPENCODE.icon} {OPENCODE.display_name}",
        ]
        assert legend.display

        sidebar.select_tab(SidebarTab.UNLOADED)
        assert legend.display
        sidebar.select_tab(SidebarTab.SHELLS)
        assert not legend.display


async def test_sidebar_displays_icon_and_ellipsizes_long_session_names(
    sleeping_harness: AgentHarness,
) -> None:
    harness = replace(sleeping_harness, id="icon-test", display_name="Icon Test", icon="🌀")
    session = _sessions(harness, SessionKind.AGENT, "A" * 200)[0]
    app = SidebarTestApp((session,))

    async with app.run_test(size=(60, 20)) as pilot:
        await pilot.pause()
        session_list = app.query_one("#sidebar-session-list", OptionList)
        prompt_lines = str(session_list.get_option(session.id).prompt).splitlines()
        assert prompt_lines[0].startswith("  🌀")
        assert prompt_lines[1] == "     · Unknown"
        assert str(session_list.styles.text_overflow) == "ellipsis"
        assert session_list.get_option(session.id).prompt.cell_length > session_list.size.width


async def test_explicit_cursor_movement_selects_the_sessions_current_tab(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    loaded = manager.create(
        name="Loaded",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    unloaded = _unloaded_session(manager, sleeping_harness, "native", "Unloaded")
    app = SidebarTestApp((loaded, unloaded))

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        sidebar.move_cursor_to_session(unloaded.id)

        assert sidebar.selected_tab is SidebarTab.UNLOADED
        assert sidebar.visible_session_ids == (unloaded.id,)
        sidebar.focus_sidebar()
        await pilot.pause()
        assert sidebar.selected_session_id == unloaded.id
