"""Integration coverage for grouped sidebar presentation and ordering."""

from collections.abc import Mapping
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import OptionList

from agenthub.harnesses import AgentHarness
from agenthub.sessions import AgentSession, SessionManager
from agenthub.ui import SessionSidebar


class SidebarTestApp(App):
    """Mount a sidebar without mounting the sessions' terminal widgets."""

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


def _sessions(
    harness: AgentHarness,
    *names: str,
) -> tuple[AgentSession, ...]:
    manager = SessionManager()
    return tuple(manager.create(name=name, cwd=Path.cwd(), harness=harness) for name in names)


async def test_empty_sidebar_shows_two_equal_empty_session_groups() -> None:
    app = SidebarTestApp((), ())

    async with app.run_test(size=(100, 36)) as pilot:
        await pilot.pause()
        sidebar = app.query_one(SessionSidebar)
        headings = [str(label.content) for label in app.query(".sidebar-section-title")]
        sections = app.query(".sidebar-section").nodes

        assert headings == ["AGENTS", "SHELLS"]
        assert len(sections) == 2
        # An odd number of terminal rows necessarily leaves one section a row taller.
        assert abs(sections[0].size.height - sections[1].size.height) <= 1
        assert len(sidebar.query(OptionList).nodes) == 2
        assert all(not option_list.options for option_list in sidebar.query(OptionList))


async def test_sidebar_keeps_empty_shell_group_when_agents_exist(
    sleeping_harness: AgentHarness,
) -> None:
    agents = _sessions(sleeping_harness, "AgentHub", "Backend")
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
    agents = _sessions(sleeping_harness, "AgentHub", "Backend")
    shells = _sessions(sleeping_harness, "AgentHub Shell", "Backend Server")
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
            "Test Sleeper · AgentHub",
            "Test Sleeper · Backend",
            "1  Test Sleeper · AgentHub Shell",
            "3  Test Sleeper · Backend Server",
        ]

        shell_list = app.query_one("#shell-session-list", OptionList)
        shell_list.highlighted = 0
        shell_list.focus()
        await pilot.press("enter")
        assert app.selected_session_id == shells[0].id
