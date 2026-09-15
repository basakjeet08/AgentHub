"""Integration coverage for temporary agent and Fish creation shortcuts."""

import sys
from pathlib import Path
from unittest.mock import Mock

from bittty import constants
from textual.widgets import ContentSwitcher, Input, OptionList, Static

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.sessions import SessionKind
from agenthub.terminal import AgentTerminal
from agenthub.ui import AgentHubStatusBar, SessionSidebar
from agenthub.ui.modals import WorkingDirectoryModal


async def _create_named_agent(
    app: AgentHubApp,
    pilot,
    name: str,
) -> None:
    """Complete the three-stage New Agent Session workflow."""

    await pilot.press("ctrl+n")
    await pilot.press("enter")
    await pilot.pause()
    app.screen.query_one("#session-name-input", Input).value = name
    await pilot.press("enter")
    await pilot.pause()
    assert isinstance(app.screen, WorkingDirectoryModal)
    await pilot.press("enter")
    await pilot.pause()


async def test_ctrl_n_modals_create_and_mount_named_agent(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(agent_harnesses={sleeping_harness.id: sleeping_harness})

    async with app.run_test() as pilot:
        await _create_named_agent(app, pilot, "Named Agent")

        sessions = app.session_manager.sessions
        assert len(sessions) == 1
        session = sessions[0]
        assert session.kind is SessionKind.AGENT
        assert session.harness is sleeping_harness
        assert session.name == "Named Agent"
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


async def test_ctrl_s_then_1_to_9_create_stable_fish_slots(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        shell_harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await _create_named_agent(app, pilot, "First Agent")
        first_agent = app.session_manager.active_session
        assert first_agent is not None

        await pilot.press("ctrl+s")
        await pilot.press("1")
        await pilot.pause()
        shell_one = app.session_manager.active_session
        assert shell_one is not None
        assert shell_one.kind is SessionKind.SHELL
        assert shell_one.cwd == Path.cwd().resolve()
        assert shell_one.terminal.working_directory == Path.cwd().resolve()
        assert shell_one is not first_agent
        assert not isinstance(app.screen, WorkingDirectoryModal)
        assert app.shell_session_slots == {1: shell_one.id}
        agent_list = app.query_one("#agent-session-list", OptionList)
        shell_list = app.query_one("#shell-session-list", OptionList)
        assert agent_list.highlighted is None
        assert shell_list.highlighted == shell_list.get_option_index(shell_one.id)

        await pilot.press("ctrl+s")
        await pilot.press("2")
        await pilot.pause()
        shell_two = app.session_manager.active_session
        assert shell_two is not None
        assert shell_two.kind is SessionKind.SHELL
        assert shell_two not in (first_agent, shell_one)
        assert app.shell_session_slots == {
            1: shell_one.id,
            2: shell_two.id,
        }
        agent_list = app.query_one("#agent-session-list", OptionList)
        shell_list = app.query_one("#shell-session-list", OptionList)
        assert agent_list.highlighted is None
        assert shell_list.highlighted == shell_list.get_option_index(shell_two.id)

        await pilot.press("ctrl+s")
        await pilot.press("1")
        assert app.session_manager.active_session is shell_one
        assert len(app.session_manager.sessions) == 3
        assert shell_list.highlighted == shell_list.get_option_index(shell_one.id)


async def test_mixed_sessions_update_grouped_sidebar_and_status(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        shell_harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await _create_named_agent(app, pilot, "First Agent")
        first_agent = app.session_manager.active_session
        assert first_agent is not None

        await pilot.press("ctrl+s")
        await pilot.press("1")
        shell_one = app.session_manager.active_session
        assert shell_one is not None

        await pilot.press("ctrl+s")
        await pilot.press("2")
        shell_two = app.session_manager.active_session
        assert shell_two is not None

        await _create_named_agent(app, pilot, "Second Agent")
        second_agent = app.session_manager.active_session
        assert second_agent is not None
        assert second_agent not in (first_agent, shell_one, shell_two)

        await pilot.press("ctrl+a")
        await pilot.press("2")
        assert app.session_manager.active_session is second_agent

        await pilot.press("ctrl+s")
        await pilot.press("2")
        assert app.session_manager.active_session is shell_two

        await pilot.press("ctrl+a")
        await pilot.press("1")
        assert app.session_manager.active_session is first_agent

        await pilot.press("ctrl+s")
        await pilot.press("1")
        await pilot.press("ctrl+a")
        await pilot.press("1")
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
            "[ 1 ] Test Sleeper · First Agent",
            "[ 2 ] Test Sleeper · Second Agent",
            "[ 1 ] Test Sleeper · Shell 1",
            "[ 2 ] Test Sleeper · Shell 2",
        ]

        status = app.query_one(AgentHubStatusBar)
        assert status.query_one("#session-count", Static).content == "Sessions 4"
        assert status.query_one("#agent-count", Static).content == "Agents 2"


async def test_exited_shell_slot_is_released_and_can_be_created_again(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "first-shell-exited"
    reusable_shell = AgentHarness(
        id="test-reusable-shell",
        display_name="Test Shell",
        command=(
            sys.executable,
            "-c",
            (
                "import pathlib, sys, time; "
                "marker = pathlib.Path(sys.argv[1]); "
                "marker.touch() if not marker.exists() else time.sleep(30)"
            ),
            str(marker),
        ),
        scroll=None,
    )
    app = AgentHubApp(shell_harness=reusable_shell)

    async with app.run_test() as pilot:
        await pilot.press("ctrl+s")
        await pilot.press("1")
        for _ in range(20):
            if marker.exists() and not app.session_manager.sessions:
                break
            await pilot.pause(0.05)
        await pilot.pause()

        assert app.is_running
        assert app.session_manager.sessions == ()
        assert app.shell_session_slots == {}

        await pilot.press("ctrl+s")
        await pilot.press("1")
        await pilot.pause()
        recreated = app.session_manager.active_session
        assert recreated is not None
        assert recreated.kind is SessionKind.SHELL
        assert recreated.terminal.is_process_running
        assert app.shell_session_slots == {1: recreated.id}


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
        await pilot.press("ctrl+s")
        await pilot.press("1")
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
