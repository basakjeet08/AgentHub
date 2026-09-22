"""Integration coverage for Agent and Fish creation workflows."""

import sys
from pathlib import Path
from unittest.mock import Mock

from bittty import constants
from textual.content import Content
from textual.widgets import ContentSwitcher, Input, OptionList, Static

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.presentation import AgentHubStatusBar, SessionSidebar, SidebarTab
from agenthub.presentation.modals import (
    ShellSessionNameInputModal,
    WorkingDirectoryPickerModal,
)
from agenthub.sessions import SessionKind
from agenthub.terminal import AgentTerminal


async def _create_agent(app: AgentHubApp, pilot) -> None:
    """Complete the two-stage New Agent Session workflow."""

    app.action_new_session()
    await pilot.pause()
    await pilot.press("enter")
    await pilot.pause()
    assert isinstance(app.screen, WorkingDirectoryPickerModal)
    await pilot.press("enter")
    await pilot.pause()


async def _create_named_shell(
    app: AgentHubApp,
    pilot,
    name: str | None = None,
) -> None:
    """Complete the New Shell Session modal workflow."""

    app.action_new_shell()
    await pilot.pause()
    assert isinstance(app.screen, ShellSessionNameInputModal)
    if name is not None:
        app.screen.query_one("#shell-session-name-input", Input).value = name
    await pilot.press("enter")
    await pilot.pause()


async def test_new_agent_modals_create_and_mount_fresh_agent(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(agent_harnesses={sleeping_harness.id: sleeping_harness})

    async with app.run_test() as pilot:
        await _create_agent(app, pilot)

        sessions = app.session_manager.sessions
        assert len(sessions) == 1
        session = sessions[0]
        assert session.kind is SessionKind.AGENT
        assert session.harness is sleeping_harness
        assert session.name == "New session"
        assert session.native_session_id is None
        assert session.terminal.is_mounted
        assert session.terminal.has_focus
        assert app.session_manager.active_session is session
        assert not app.hub_locked
        sidebar = app.query_one(SessionSidebar)
        assert sidebar.visible_session_ids == (session.id,)
        assert app.query_one("#session-content", ContentSwitcher).current == (
            app._terminal_dom_id(session.id)
        )


async def test_new_shell_action_creates_fish_shells_and_ctrl_s_navigates(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        shell_harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await _create_agent(app, pilot)
        first_agent = app.session_manager.active_session
        assert first_agent is not None

        await _create_named_shell(app, pilot)
        shell_one = app.session_manager.active_session
        assert shell_one is not None
        assert shell_one.name == "Shell"
        assert shell_one.kind is SessionKind.SHELL
        assert shell_one.cwd == Path.cwd().resolve()
        assert shell_one.terminal.working_directory == Path.cwd().resolve()
        assert shell_one is not first_agent
        assert not isinstance(app.screen, WorkingDirectoryPickerModal)
        sidebar = app.query_one(SessionSidebar)
        session_list = app.query_one("#sidebar-session-list", OptionList)
        assert sidebar.selected_tab is SidebarTab.SHELLS
        assert session_list.highlighted == session_list.get_option_index(shell_one.id)

        await _create_named_shell(app, pilot, "Custom Shell")
        shell_two = app.session_manager.active_session
        assert shell_two is not None
        assert shell_two.name == "Custom Shell"
        assert shell_two.kind is SessionKind.SHELL
        assert shell_two not in (first_agent, shell_one)
        assert sidebar.selected_tab is SidebarTab.SHELLS
        assert session_list.highlighted == session_list.get_option_index(shell_two.id)

        await pilot.press("ctrl+s")
        await pilot.press("up")
        await pilot.press("enter")
        assert app.session_manager.active_session is shell_one
        assert len(app.session_manager.sessions) == 3
        assert session_list.highlighted == session_list.get_option_index(shell_one.id)


async def test_mixed_sessions_update_grouped_sidebar_and_status(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        shell_harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await _create_agent(app, pilot)
        first_agent = app.session_manager.active_session
        assert first_agent is not None

        await _create_named_shell(app, pilot, "Shell 1")
        shell_one = app.session_manager.active_session
        assert shell_one is not None

        await _create_named_shell(app, pilot, "Shell 2")
        shell_two = app.session_manager.active_session
        assert shell_two is not None

        await _create_agent(app, pilot)
        second_agent = app.session_manager.active_session
        assert second_agent is not None
        assert second_agent not in (first_agent, shell_one, shell_two)

        await pilot.press("ctrl+s")
        await pilot.press("enter")
        assert app.session_manager.active_session is second_agent

        await pilot.press("ctrl+s")
        await pilot.press("right", "right")
        await pilot.press("enter")
        assert app.session_manager.active_session is shell_two

        await pilot.press("ctrl+s")
        await pilot.press("right")
        await pilot.press("up")
        await pilot.press("enter")
        assert app.session_manager.active_session is first_agent

        await pilot.press("ctrl+s")
        await pilot.press("right", "right")
        await pilot.press("up")
        await pilot.press("enter")
        assert app.session_manager.active_session is shell_one

        await pilot.press("ctrl+s")
        await pilot.press("right")
        await pilot.press("enter")
        assert app.session_manager.active_session is first_agent

        sidebar = app.query_one(SessionSidebar)
        assert sidebar.visible_session_ids == (
            first_agent.id,
            second_agent.id,
        )
        assert sidebar.tab_counts == {
            SidebarTab.LOADED: 2,
            SidebarTab.UNLOADED: 0,
            SidebarTab.SHELLS: 2,
        }
        option_prompts = [
            str(option.prompt)
            for option_list in sidebar.query(OptionList)
            for option in option_list.options
        ]
        harness_badge = f"{sleeping_harness.icon} "
        activity_indent = " " * Content(harness_badge).cell_length
        assert option_prompts == [
            f"▌ {harness_badge}New session\n▌ {activity_indent}· Unknown",
            f"  {harness_badge}New session\n  {activity_indent}· Unknown",
        ]

        status = app.query_one(AgentHubStatusBar)
        assert status.query_one("#session-count", Static).content == "Sessions 4"
        assert status.query_one("#running-count", Static).content == "Running 2"


async def test_exited_shell_is_cleaned_up_and_new_shell_can_be_created(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "first-shell-exited"
    reusable_shell = AgentHarness(
        id="test-reusable-shell",
        display_name="Test Shell",
        icon="🧪",
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
        await _create_named_shell(app, pilot)
        for _ in range(20):
            if marker.exists() and not app.session_manager.sessions:
                break
            await pilot.pause(0.05)
        await pilot.pause()

        assert app.is_running
        assert app.session_manager.sessions == ()

        await _create_named_shell(app, pilot)
        recreated = app.session_manager.active_session
        assert recreated is not None
        assert recreated.name == "Shell"
        assert recreated.kind is SessionKind.SHELL
        assert recreated.terminal.is_process_running
        assert len(app.session_manager.sessions) == 1


async def test_mounted_shell_scrollback_renders_without_crashing() -> None:
    shell_harness = AgentHarness(
        id="test-output-shell",
        display_name="Test Shell",
        icon="🧪",
        command=(
            sys.executable,
            "-c",
            "import time; [print(number, flush=True) for number in range(80)]; time.sleep(30)",
        ),
        scroll=None,
    )
    app = AgentHubApp(shell_harness=shell_harness)

    async with app.run_test(size=(100, 24)) as pilot:
        await _create_named_shell(app, pilot)
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


async def test_shell_naming_modal_workflow_rules(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(shell_harness=sleeping_harness)

    async with app.run_test() as pilot:
        # Rule 1: Blank name uses default "Shell"
        app.action_new_shell()
        await pilot.pause()
        assert isinstance(app.screen, ShellSessionNameInputModal)
        await pilot.press("enter")
        await pilot.pause()
        assert len(app.session_manager.sessions) == 1
        assert app.session_manager.sessions[0].name == "Shell"

        # Rule 2: Whitespace trimming on custom name
        app.action_new_shell()
        await pilot.pause()
        app.screen.query_one("#shell-session-name-input", Input).value = "   Server Shell   "
        await pilot.press("enter")
        await pilot.pause()
        assert len(app.session_manager.sessions) == 2
        assert app.session_manager.sessions[1].name == "Server Shell"

        # Rule 3: Duplicate shell names are allowed
        app.action_new_shell()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert len(app.session_manager.sessions) == 3
        assert app.session_manager.sessions[2].name == "Shell"

        # Rule 4: Canceling with Esc creates no shell
        app.action_new_shell()
        await pilot.pause()
        assert isinstance(app.screen, ShellSessionNameInputModal)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ShellSessionNameInputModal)
        assert len(app.session_manager.sessions) == 3


async def test_shell_creation_modal_reentry_guard(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(shell_harness=sleeping_harness)

    async with app.run_test() as pilot:
        app.action_new_shell()
        await pilot.pause()
        assert isinstance(app.screen, ShellSessionNameInputModal)
        first_modal = app.screen

        # Repeated New Shell actions do not push another modal.
        app.action_new_shell()
        await pilot.pause()
        assert app.screen is first_modal

        # Dismiss modal
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ShellSessionNameInputModal)

        # During New Agent flow, New Shell is also ignored.
        app.action_new_session()
        await pilot.pause()
        from agenthub.presentation.modals import HarnessPickerModal

        assert isinstance(app.screen, HarnessPickerModal)
        harness_modal = app.screen

        app.action_new_shell()
        await pilot.pause()
        assert app.screen is harness_modal
