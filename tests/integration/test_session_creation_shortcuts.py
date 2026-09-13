"""Integration coverage for temporary agent and Fish creation shortcuts."""

import sys
from unittest.mock import Mock

from bittty import constants
from textual.widgets import ContentSwitcher, OptionList, Static

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.terminal import AgentTerminal
from agenthub.ui import AgentHubStatusBar, SessionSidebar


async def test_ctrl_n_creates_and_mounts_agent_without_a_modal(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(agent_harness=sleeping_harness)

    async with app.run_test() as pilot:
        await pilot.press("ctrl+n")
        await pilot.pause()

        sessions = app.session_manager.sessions
        assert len(sessions) == 1
        session = sessions[0]
        assert session.harness is sleeping_harness
        assert session.terminal.is_mounted
        assert session.terminal.has_focus
        assert app.session_manager.active_session is session
        assert not app.hub_locked
        sidebar = app.query_one(SessionSidebar)
        assert sidebar.visible_session_ids == (session.id,)
        assert sidebar.shortcut_slots == {}
        assert app.query_one("#session-content", ContentSwitcher).current == (
            app._terminal_dom_id(session.id)
        )


async def test_ctrl_1_to_9_create_stable_fish_slots(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(
        agent_harness=sleeping_harness,
        shell_harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await pilot.press("ctrl+n")
        first_agent = app.session_manager.active_session
        assert first_agent is not None

        await pilot.press("ctrl+1")
        await pilot.pause()
        shell_one = app.session_manager.active_session
        assert shell_one is not None
        assert shell_one is not first_agent
        assert app.shell_session_slots == {1: shell_one.id}
        agent_list = app.query_one("#agent-session-list", OptionList)
        shell_list = app.query_one("#shell-session-list", OptionList)
        assert agent_list.highlighted is None
        assert shell_list.highlighted == shell_list.get_option_index(shell_one.id)

        await pilot.press("ctrl+2")
        await pilot.pause()
        shell_two = app.session_manager.active_session
        assert shell_two is not None
        assert shell_two not in (first_agent, shell_one)
        assert app.shell_session_slots == {
            1: shell_one.id,
            2: shell_two.id,
        }
        agent_list = app.query_one("#agent-session-list", OptionList)
        shell_list = app.query_one("#shell-session-list", OptionList)
        assert agent_list.highlighted is None
        assert shell_list.highlighted == shell_list.get_option_index(shell_two.id)

        await pilot.press("ctrl+1")
        assert app.session_manager.active_session is shell_one
        assert len(app.session_manager.sessions) == 3
        assert shell_list.highlighted == shell_list.get_option_index(shell_one.id)


async def test_mixed_sessions_update_grouped_sidebar_and_status(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(
        agent_harness=sleeping_harness,
        shell_harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await pilot.press("ctrl+n")
        first_agent = app.session_manager.active_session
        assert first_agent is not None

        await pilot.press("ctrl+1")
        shell_one = app.session_manager.active_session
        assert shell_one is not None

        await pilot.press("ctrl+2")
        shell_two = app.session_manager.active_session
        assert shell_two is not None

        await pilot.press("ctrl+n")
        await pilot.pause()
        second_agent = app.session_manager.active_session
        assert second_agent is not None
        assert second_agent not in (first_agent, shell_one, shell_two)

        await pilot.press("ctrl+a")
        await pilot.press("enter")
        assert app.session_manager.active_session is first_agent

        await pilot.press("ctrl+1")
        await pilot.press("ctrl+a")
        await pilot.press("enter")
        assert app.session_manager.active_session is first_agent

        sidebar = app.query_one(SessionSidebar)
        assert sidebar.visible_session_ids == (
            first_agent.id,
            second_agent.id,
            shell_one.id,
            shell_two.id,
        )
        assert sidebar.shortcut_slots == {
            shell_one.id: 1,
            shell_two.id: 2,
        }
        headings = [str(heading.content) for heading in sidebar.query(".sidebar-section-title")]
        assert headings == ["AGENTS", "SHELLS"]
        option_prompts = [
            str(option.prompt)
            for option_list in sidebar.query(OptionList)
            for option in option_list.options
        ]
        assert option_prompts == [
            "Test Sleeper · Test Sleeper",
            "Test Sleeper · Test Sleeper 2",
            "1  Test Sleeper · Shell 1",
            "2  Test Sleeper · Shell 2",
        ]

        status = app.query_one(AgentHubStatusBar)
        assert status.query_one("#session-count", Static).content == "Sessions 4"
        assert status.query_one("#agent-count", Static).content == "Agents 2"


async def test_mounted_shell_scrollback_renders_without_crashing() -> None:
    shell_harness = AgentHarness(
        id="test-output-shell",
        display_name="Test Shell",
        command=(
            sys.executable,
            "-c",
            "import time; [print(number, flush=True) for number in range(80)]; time.sleep(30)",
        ),
        scroll=None,
    )
    app = AgentHubApp(shell_harness=shell_harness)

    async with app.run_test(size=(100, 24)) as pilot:
        await pilot.press("ctrl+1")
        terminal = app.query_one(AgentTerminal)
        for _ in range(20):
            if terminal.scrollback_line_count:
                break
            await pilot.pause(0.05)

        event = Mock()
        terminal._wheel(event, constants.MOUSE_BUTTON_WHEEL_UP, "up")
        await pilot.pause()

        assert terminal.scrollback_offset > 0
        assert app.is_running
        event.stop.assert_called_once_with()
