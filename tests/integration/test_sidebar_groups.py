"""Integration coverage for grouped sidebar presentation and ordering."""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.content import Content
from textual.widgets import OptionList

from agenthub.harnesses import ANTIGRAVITY, CODEX, DEVIN, FISH, OPENCODE, AgentHarness
from agenthub.native_sessions import NativeSession
from agenthub.sessions import AgentSession, SessionKind, SessionManager
from agenthub.ui import SessionSidebar


class SidebarTestApp(App):
    """Mount a sidebar without mounting the sessions' terminal widgets."""

    CSS_PATH = Path(__file__).parents[2] / "src/agenthub/ui/panels/sidebar.tcss"

    def __init__(
        self,
        agent_sessions: tuple[AgentSession, ...],
        shell_sessions: tuple[AgentSession, ...],
    ) -> None:
        super().__init__()
        self.agent_sessions = agent_sessions
        self.shell_sessions = shell_sessions
        self.selected_session_id: str | None = None

    def compose(self) -> ComposeResult:
        yield SessionSidebar(
            self.agent_sessions,
            shell_sessions=self.shell_sessions,
        )

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


async def test_empty_sidebar_allocates_more_space_to_agent_sessions() -> None:
    app = SidebarTestApp((), ())

    async with app.run_test(size=(100, 36)) as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        headings = [str(label.content) for label in app.query(".sidebar-section-title")]
        sections = app.query(".sidebar-section").nodes

        assert headings == ["AGENTS", "SHELLS"]
        assert len(sections) == 2
        assert sections[0].size.height > sections[1].size.height
        assert str(sections[0].styles.height) == "7fr"
        assert str(sections[1].styles.height) == "3fr"
        assert len(sidebar.query(OptionList).nodes) == 2
        assert all(not option_list.options for option_list in sidebar.query(OptionList))
        assert sidebar.styles.scrollbar_size_vertical == 1
        assert all(
            option_list.styles.scrollbar_size_vertical == 1
            for option_list in sidebar.query(OptionList)
        )


async def test_sidebar_keeps_empty_shell_group_when_agents_exist(
    sleeping_harness: AgentHarness,
) -> None:
    agents = _sessions(sleeping_harness, SessionKind.AGENT, "AgentHub", "Backend")
    app = SidebarTestApp(agents, ())

    async with app.run_test() as pilot:
        await pilot.pause()
        headings = [str(label.content) for label in app.query(".sidebar-section-title")]
        assert headings == ["AGENTS", "SHELLS"]
        assert not app.query_one("#shell-session-list", OptionList).options
        assert app.query_one(SessionSidebar).visible_session_ids == tuple(
            session.id for session in agents
        )


async def test_sidebar_groups_navigation_and_selection(
    sleeping_harness: AgentHarness,
) -> None:
    agents = _sessions(sleeping_harness, SessionKind.AGENT, "AgentHub", "Backend")
    shells = _sessions(
        sleeping_harness,
        SessionKind.SHELL,
        "AgentHub Shell",
        "Backend Server",
    )
    app = SidebarTestApp(agents, shells)

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        headings = [str(label.content) for label in app.query(".sidebar-section-title")]
        assert headings == ["AGENTS", "SHELLS"]
        assert sidebar.visible_session_ids == tuple(session.id for session in (*agents, *shells))

        option_prompts = [
            str(option.prompt)
            for option_list in app.query(OptionList)
            for option in option_list.options
        ]
        assert option_prompts == [
            "LOADED · 2",
            "  Test Sleeper · AgentHub",
            "  Test Sleeper · Backend",
            "  Test Sleeper · AgentHub Shell",
            "  Test Sleeper · Backend Server",
        ]

        shell_list = app.query_one("#shell-session-list", OptionList)
        agent_list = app.query_one("#agent-session-list", OptionList)

        sidebar.focus_shells()
        await pilot.pause()
        assert shell_list.has_focus
        assert shell_list.highlighted == 0
        await pilot.press("down")
        assert shell_list.highlighted == 1
        await pilot.press("enter")
        assert app.selected_session_id == shells[1].id

        sidebar.focus_agents()
        await pilot.pause()
        assert agent_list.has_focus
        assert agent_list.highlighted == agent_list.get_option_index(agents[0].id)
        await pilot.press("down")
        assert agent_list.highlighted == agent_list.get_option_index(agents[1].id)
        assert agent_list.has_focus
        assert app.selected_session_id == shells[1].id
        await pilot.press("enter")
        assert app.selected_session_id == agents[1].id

        sidebar.focus_shells()
        await pilot.pause()
        shell_list.highlighted = 0
        await pilot.press("2")
        assert shell_list.highlighted == 0
        await pilot.press("3")
        assert shell_list.highlighted == 0


async def test_sidebar_styles_active_running_and_unloaded_sessions_independently(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    running = manager.create(
        name="Running",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    active = manager.create(
        name="Active",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    unloaded = manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "native-unloaded",
            "Unloaded",
            Path.cwd(),
        ),
        harness=sleeping_harness,
    )
    app = SidebarTestApp((running, active, unloaded), ())

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        agent_list = app.query_one("#agent-session-list", OptionList)

        sidebar.set_active(active.id)
        sidebar.focus_agents()
        await pilot.pause()

        def prompt_styles(session: AgentSession) -> list[str]:
            prompt = agent_list.get_option(session.id).prompt
            assert isinstance(prompt, Content)
            assert prompt.spans
            styles = [span.style for span in prompt.spans]
            assert all(isinstance(style, str) for style in styles)
            return styles  # type: ignore[return-value]

        assert agent_list.highlighted == agent_list.get_option_index(running.id)
        assert prompt_styles(running) == ["$foreground"]
        assert prompt_styles(active) == ["$foreground", "$secondary", "bold"]
        assert prompt_styles(unloaded) == ["$foreground"]
        assert str(agent_list.get_option(running.id).prompt).startswith("  ")
        assert str(agent_list.get_option(active.id).prompt).startswith("▌ ")
        unloaded_prompt = str(agent_list.get_option(unloaded.id).prompt)
        assert unloaded_prompt.startswith("  ")
        assert "UNLOADED" not in unloaded_prompt


async def test_sidebar_displays_harness_icon() -> None:
    manager = SessionManager()
    codex_session = manager.create(
        name="Auth Refactor",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=CODEX,
    )
    opencode_session = manager.create(
        name="API Cleanup",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=OPENCODE,
    )
    fish_session = manager.create(
        name="Fish Slot",
        kind=SessionKind.SHELL,
        cwd=Path.cwd(),
        harness=FISH,
    )
    app = SidebarTestApp(
        (codex_session, opencode_session),
        (fish_session,),
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        option_prompts = [
            str(option.prompt)
            for option_list in app.query(OptionList)
            for option in option_list.options
        ]
        assert option_prompts == [
            "LOADED · 2",
            "  🌀 Auth Refactor",
            "  💻 API Cleanup",
            "  🐟 Fish Slot",
        ]


async def test_sidebar_ellipsizes_long_options_to_one_line(
    sleeping_harness: AgentHarness,
) -> None:
    (agent,) = _sessions(
        sleeping_harness,
        SessionKind.AGENT,
        "WhatsApp OTP verification for opportunities",
    )
    app = SidebarTestApp((agent,), ())

    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.pause()
        agent_list = app.query_one("#agent-session-list", OptionList)

        assert agent_list.compact
        assert agent_list.virtual_size.height == len(agent_list.options)
        rendered_option = agent_list.render_line(1).text.rstrip()
        assert rendered_option.endswith("…")
        assert agent.name not in rendered_option


async def test_sidebar_renders_agent_harness_legend() -> None:
    app = SidebarTestApp((), ())

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        legend = sidebar.query_one("#agent-legend")
        items = list(legend.query(".legend-item"))
        assert [str(item.content) for item in items] == [
            "🛸 Antigravity",
            "🌀 Codex",
            "🤖 Devin",
            "💻 OpenCode",
        ]
        assert items[0].region.x < items[1].region.x
        assert items[1].region.x == items[0].region.x + items[0].region.width
        assert items[0].region.width == items[1].region.width
        assert items[2].region.x == items[0].region.x
        assert items[3].region.x == items[1].region.x
        assert items[2].region.width == items[3].region.width


async def test_sidebar_restores_cursor_by_session_identity_on_mutation(
    sleeping_harness: AgentHarness,
) -> None:
    agents = _sessions(sleeping_harness, SessionKind.AGENT, "Agent 1", "Agent 2")
    shells = _sessions(
        sleeping_harness,
        SessionKind.SHELL,
        "Shell A",
        "Shell B",
        "Shell C",
    )
    app = SidebarTestApp(agents, shells)

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        shell_list = app.query_one("#shell-session-list", OptionList)

        # Focus shells and move cursor to Shell B (index 1)
        sidebar.focus_shells()
        await pilot.pause()
        await pilot.press("down")
        assert shell_list.highlighted == 1

        # Switch focus to agents
        sidebar.focus_agents()
        await pilot.pause()

        # Shell A exits in background: remaining shells are Shell B (now index 0) and Shell C (now index 1)
        sidebar.update_sessions(agents, shell_sessions=(shells[1], shells[2]))
        await pilot.pause()

        # Focus shells again: cursor must resolve to Shell B (index 0) rather than obsolete index 1
        sidebar.focus_shells()
        await pilot.pause()
        current_shell_list = app.query_one("#shell-session-list", OptionList)
        assert current_shell_list.highlighted == 0
        assert current_shell_list.get_option_at_index(current_shell_list.highlighted).id == shells[1].id

        # Switch away, then Shell B exits: remaining shell is only Shell C
        sidebar.focus_agents()
        await pilot.pause()
        sidebar.update_sessions(agents, shell_sessions=(shells[2],))
        await pilot.pause()

        # Focus shells again: Shell B is gone, defaults gracefully to index 0 (Shell C)
        sidebar.focus_shells()
        await pilot.pause()
        current_shell_list = app.query_one("#shell-session-list", OptionList)
        assert current_shell_list.highlighted == 0
        assert current_shell_list.get_option_at_index(current_shell_list.highlighted).id == shells[2].id


async def test_sidebar_keeps_active_identity_separate_from_agent_cursor(
    sleeping_harness: AgentHarness,
) -> None:
    agents = _sessions(
        sleeping_harness,
        SessionKind.AGENT,
        "Active Agent",
        "Highlighted Agent",
    )
    app = SidebarTestApp(agents, ())

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        sidebar.set_active(agents[0].id)
        sidebar.move_cursor_to_session(agents[0].id)
        sidebar.focus_agents()
        await pilot.press("down")

        assert sidebar.focused_session_kind is SessionKind.AGENT
        assert sidebar.selected_session_id == agents[1].id

        agents[1].name = "Linked Provider Title"
        sidebar.update_sessions(agents)
        await pilot.pause()

        current_agent_list = app.query_one("#agent-session-list", OptionList)
        assert sidebar.focused_session_kind is SessionKind.AGENT
        assert sidebar.selected_session_id == agents[1].id
        assert current_agent_list.highlighted == current_agent_list.get_option_index(
            agents[1].id
        )

        active_prompt = current_agent_list.get_option(agents[0].id).prompt
        highlighted_prompt = current_agent_list.get_option(agents[1].id).prompt
        assert isinstance(active_prompt, Content)
        assert isinstance(highlighted_prompt, Content)
        assert str(active_prompt).startswith("▌ ")
        assert str(highlighted_prompt).startswith("  ")
        assert any(span.style == "bold" for span in active_prompt.spans)
        assert all(span.style != "bold" for span in highlighted_prompt.spans)


async def test_agent_rows_group_loaded_before_unloaded_and_skip_headers(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    loaded_one = manager.create(
        name="Loaded One",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    unloaded_one = manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "native-one",
            "Unloaded One",
            Path.cwd(),
        ),
        harness=sleeping_harness,
    )
    loaded_two = manager.create(
        name="Loaded Two",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    unloaded_two = manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "native-two",
            "Unloaded Two",
            Path.cwd(),
        ),
        harness=sleeping_harness,
    )
    app = SidebarTestApp(
        (unloaded_one, loaded_one, unloaded_two, loaded_two),
        (),
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        agent_list = app.query_one("#agent-session-list", OptionList)

        assert sidebar.visible_session_ids == (
            loaded_one.id,
            loaded_two.id,
            unloaded_one.id,
            unloaded_two.id,
        )
        assert [str(option.prompt) for option in agent_list.options] == [
            "LOADED · 2",
            "  Test Sleeper · Loaded One",
            "  Test Sleeper · Loaded Two",
            "",
            "UNLOADED · 2",
            "  Test Sleeper · Unloaded One",
            "  Test Sleeper · Unloaded Two",
        ]
        assert [option.disabled for option in agent_list.options] == [
            True,
            False,
            False,
            True,
            True,
            False,
            False,
        ]

        sidebar.focus_agents()
        await pilot.pause()
        assert sidebar.selected_session_id == loaded_one.id
        await pilot.press("down")
        assert sidebar.selected_session_id == loaded_two.id
        await pilot.press("down")
        assert sidebar.selected_session_id == unloaded_one.id
        await pilot.press("up")
        assert sidebar.selected_session_id == loaded_two.id

        await pilot.press("down")
        assert sidebar.selected_session_id == unloaded_one.id
        await pilot.press("enter")
        assert app.selected_session_id == unloaded_one.id


async def test_agent_groups_preserve_existing_order_within_each_group() -> None:
    manager = SessionManager()
    devin_loaded = manager.create(
        name="Beta",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=DEVIN,
    )
    codex_zulu = manager.create(
        name="Zulu",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=CODEX,
    )
    antigravity_loaded = manager.create(
        name="Middle",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=ANTIGRAVITY,
    )
    codex_alpha = manager.create(
        name="alpha",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=CODEX,
    )
    opencode_unloaded = manager.add_discovered(
        native_session=NativeSession(
            OPENCODE.id,
            "opencode-native",
            "First",
            Path.cwd(),
        ),
        harness=OPENCODE,
    )
    codex_unloaded = manager.add_discovered(
        native_session=NativeSession(
            CODEX.id,
            "codex-native",
            "Second",
            Path.cwd(),
        ),
        harness=CODEX,
    )
    app = SidebarTestApp(manager.sessions, ())

    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one(SessionSidebar).visible_session_ids == (
            devin_loaded.id,
            codex_zulu.id,
            antigravity_loaded.id,
            codex_alpha.id,
            opencode_unloaded.id,
            codex_unloaded.id,
        )


async def test_agent_group_headers_are_hidden_when_empty(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    unloaded = manager.add_discovered(
        native_session=NativeSession(
            sleeping_harness.id,
            "native-only",
            "Unloaded Only",
            Path.cwd(),
        ),
        harness=sleeping_harness,
    )
    app = SidebarTestApp((unloaded,), ())

    async with app.run_test() as pilot:
        await pilot.pause()
        agent_list = app.query_one("#agent-session-list", OptionList)

        assert [str(option.prompt) for option in agent_list.options] == [
            "UNLOADED · 1",
            "  Test Sleeper · Unloaded Only",
        ]
        assert agent_list.options[0].disabled
        assert not agent_list.options[1].disabled


async def test_agent_cursor_follows_session_identity_between_groups(
    sleeping_harness: AgentHarness,
) -> None:
    manager = SessionManager()
    stays_loaded = manager.create(
        name="Stays Loaded",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    moves_to_unloaded = manager.create(
        name="Moves To Unloaded",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    moves_to_unloaded.native_session_id = "native-moving"
    app = SidebarTestApp((stays_loaded, moves_to_unloaded), ())

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        sidebar.set_active(stays_loaded.id)
        sidebar.move_cursor_to_session(moves_to_unloaded.id)
        sidebar.focus_agents()
        await pilot.pause()
        assert sidebar.selected_session_id == moves_to_unloaded.id

        manager.detach_terminal(moves_to_unloaded.id)
        sidebar.update_sessions(manager.sessions)
        await pilot.pause()

        agent_list = app.query_one("#agent-session-list", OptionList)
        assert [str(option.prompt) for option in agent_list.options] == [
            "LOADED · 1",
            "▌ Test Sleeper · Stays Loaded",
            "",
            "UNLOADED · 1",
            "  Test Sleeper · Moves To Unloaded",
        ]
        assert sidebar.selected_session_id == moves_to_unloaded.id
        assert agent_list.highlighted == agent_list.get_option_index(moves_to_unloaded.id)

        active_prompt = agent_list.get_option(stays_loaded.id).prompt
        cursor_prompt = agent_list.get_option(moves_to_unloaded.id).prompt
        assert isinstance(active_prompt, Content)
        assert isinstance(cursor_prompt, Content)
        assert any(span.style == "bold" for span in active_prompt.spans)
        assert all(span.style != "bold" for span in cursor_prompt.spans)
