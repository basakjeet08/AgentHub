"""Integration coverage for grouped sidebar presentation and ordering."""

from collections.abc import Mapping
from pathlib import Path

from textual.app import App, ComposeResult
from textual.content import Content
from textual.widgets import OptionList

from agenthub.harnesses import CODEX, FISH, OPENCODE, AgentHarness
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
        shortcut_slots: Mapping[str, int] | None = None,
    ) -> None:
        super().__init__()
        self.agent_sessions = agent_sessions
        self.shell_sessions = shell_sessions
        self.shortcut_slots = shortcut_slots or {}
        self.selected_session_id: str | None = None
        self.selected_shell_slot: int | None = None

    def compose(self) -> ComposeResult:
        yield SessionSidebar(
            self.agent_sessions,
            shell_sessions=self.shell_sessions,
            shortcut_slots=self.shortcut_slots,
        )

    def on_session_sidebar_session_selected(
        self,
        message: SessionSidebar.SessionSelected,
    ) -> None:
        self.selected_session_id = message.session_id

    def on_session_sidebar_shell_slot_selected(
        self,
        message: SessionSidebar.ShellSlotSelected,
    ) -> None:
        self.selected_shell_slot = message.slot


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


async def test_sidebar_numbers_shell_slots_and_emits_same_intent(
    sleeping_harness: AgentHarness,
) -> None:
    agents = _sessions(sleeping_harness, SessionKind.AGENT, "AgentHub", "Backend")
    shells = _sessions(
        sleeping_harness,
        SessionKind.SHELL,
        "AgentHub Shell",
        "Backend Server",
    )
    shortcut_slots = {
        shells[0].id: 1,
        shells[1].id: 3,
    }
    app = SidebarTestApp(agents, shells, shortcut_slots)

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
            "● [ 1 ] Test Sleeper · AgentHub",
            "● [ 2 ] Test Sleeper · Backend",
            "● [ 1 ] Test Sleeper · AgentHub Shell",
            "● [ 3 ] Test Sleeper · Backend Server",
        ]

        shell_list = app.query_one("#shell-session-list", OptionList)
        shell_list.highlighted = 0
        shell_list.focus()
        await pilot.press("enter")
        assert app.selected_session_id == shells[0].id

        sidebar.focus_agents()
        await pilot.press("2")
        assert app.selected_session_id == agents[1].id

        sidebar.focus_shells()
        await pilot.press("3")
        assert app.selected_session_id == shells[1].id

        sidebar.focus_shells()
        await pilot.press("2")
        assert app.selected_shell_slot == 2


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

        assert agent_list.highlighted == 0
        assert prompt_styles(running) == ["$foreground", "$foreground"]
        assert prompt_styles(active) == ["$success", "$foreground", "bold"]
        assert prompt_styles(unloaded) == ["$text-muted", "$foreground"]
        unloaded_prompt = str(agent_list.get_option(unloaded.id).prompt)
        assert unloaded_prompt.startswith("○ ")
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
        shortcut_slots={fish_session.id: 1},
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        option_prompts = [
            str(option.prompt)
            for option_list in app.query(OptionList)
            for option in option_list.options
        ]
        assert option_prompts == [
            "● [ 1 ] 🌀 Auth Refactor",
            "● [ 2 ] 💻 API Cleanup",
            "● [ 1 ] 🐟 Fish Slot",
        ]


async def test_sidebar_renders_agent_harness_legend() -> None:
    app = SidebarTestApp((), ())

    async with app.run_test() as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        legend = sidebar.query_one("#agent-legend")
        items = list(legend.query(".legend-item"))
        assert [str(item.content) for item in items] == [
            "✨ Antigravity",
            "🌀 Codex",
            "🟩 Devin",
            "💻 OpenCode",
        ]
        assert items[0].region.x < items[1].region.x
        assert items[1].region.x == items[0].region.x + items[0].region.width
        assert items[0].region.width == items[1].region.width
        assert items[2].region.x == items[0].region.x
        assert items[3].region.x == items[1].region.x
        assert items[2].region.width == items[3].region.width

