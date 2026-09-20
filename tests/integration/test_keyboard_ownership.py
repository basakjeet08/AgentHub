"""Integration coverage for terminal-first keyboard ownership."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from textual.command import CommandPalette
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.presentation import AgentHubStatusBar, SessionSidebar, SidebarTab
from agenthub.presentation.modals import (
    HarnessSelectionModal,
    NativeSessionLinkModal,
    SessionNameModal,
    WorkingDirectoryModal,
)
from agenthub.presentation.modals.working_directory import FolderTree
from agenthub.presentation.panels.status_bar import LOCKED_ICON, UNLOCKED_ICON
from agenthub.sessions import AgentSession, SessionKind


def _app_with_sessions(
    harness: AgentHarness,
    count: int = 1,
    working_directory_root: Path | None = None,
) -> tuple[AgentHubApp, tuple[AgentSession, ...]]:
    app = AgentHubApp(
        agent_harnesses={harness.id: harness},
        shell_harness=harness,
        working_directory_root=working_directory_root,
    )
    sessions = tuple(
        app.session_manager.create(
            name=f"Session {index}",
            kind=SessionKind.AGENT,
            cwd=Path.cwd(),
            harness=harness,
        )
        for index in range(1, count + 1)
    )
    return app, sessions


@pytest.mark.parametrize(
    ("key", "expected_input"),
    [
        ("ctrl+a", "\x01"),
        ("ctrl+s", "\x13"),
        ("ctrl+n", "\x0e"),
        ("ctrl+p", "\x10"),
        ("ctrl+q", "\x11"),
        ("ctrl+backspace", "\x17"),
        ("ctrl+0", "0"),
        ("ctrl+1", "1"),
        ("tab", "\t"),
        ("alt+m", "m"),
    ],
)
async def test_locked_hub_binding_reaches_pty(
    sleeping_harness: AgentHarness,
    key: str,
    expected_input: str,
) -> None:
    app, (session,) = _app_with_sessions(sleeping_harness)

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+g")
        assert app.hub_locked
        pty = session.terminal.board.pty
        assert pty is not None

        with patch.object(pty, "write", wraps=pty.write) as write_spy:
            await pilot.press(key)
            await pilot.pause()

        write_spy.assert_called_once_with(expected_input)
        assert app.hub_locked
        assert app.is_running
        assert not isinstance(app.screen, CommandPalette)
        assert not isinstance(
            app.screen,
            (
                HarnessSelectionModal,
                NativeSessionLinkModal,
                SessionNameModal,
                WorkingDirectoryModal,
            ),
        )
        assert app.session_manager.sessions == (session,)


@pytest.mark.parametrize("locked", [False, True])
@pytest.mark.parametrize(
    ("key", "expected_input"),
    [
        ("left", "\x1b[D"),
        ("right", "\x1b[C"),
    ],
)
async def test_sidebar_tab_arrows_reach_active_terminal(
    sleeping_harness: AgentHarness,
    locked: bool,
    key: str,
    expected_input: str,
) -> None:
    app, (session,) = _app_with_sessions(sleeping_harness)

    async with app.run_test() as pilot:
        await pilot.pause()
        if locked:
            await pilot.press("ctrl+g")
            assert app.hub_locked

        assert session.terminal.has_focus
        pty = session.terminal.board.pty
        assert pty is not None

        with patch.object(pty, "write", wraps=pty.write) as write_spy:
            await pilot.press(key)
            await pilot.pause()

        write_spy.assert_called_once_with(expected_input)
        assert session.terminal.has_focus
        assert app.session_manager.active_session is session


async def test_super_a_is_consumed_without_crashing_or_reaching_pty(
    sleeping_harness: AgentHarness,
) -> None:
    app, (session,) = _app_with_sessions(sleeping_harness)

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+g")
        assert app.hub_locked
        assert session.terminal.has_focus
        pty = session.terminal.board.pty
        assert pty is not None

        with patch.object(pty, "write", wraps=pty.write) as write_spy:
            await pilot.press("super+a")
            await pilot.pause()

        assert app.is_running
        assert session.terminal.has_focus
        write_spy.assert_not_called()

        with patch.object(pty, "write", wraps=pty.write) as write_spy:
            await pilot.press("a")
            await pilot.pause()

        write_spy.assert_called_once_with("a")
        assert session.terminal.has_focus


async def test_shell_name_input_owns_ctrl_v_over_a_mounted_terminal(
    sleeping_harness: AgentHarness,
) -> None:
    app, (session,) = _app_with_sessions(sleeping_harness)

    async with app.run_test() as pilot:
        app.action_new_shell()
        await pilot.pause()
        assert isinstance(app.screen, SessionNameModal)
        name_input = app.screen.query_one("#session-name-input", Input)
        pty = session.terminal.board.pty
        assert pty is not None

        with (
            patch(
                "agenthub.presentation.modals.session_name._CLIPBOARD_SERVICE.read_text",
                AsyncMock(return_value="Clipboard Session"),
            ),
            patch(
                "agenthub.terminal.widget._CLIPBOARD_SERVICE.read",
                AsyncMock(return_value="must not reach terminal"),
            ) as terminal_clipboard,
            patch.object(pty, "write", wraps=pty.write) as write_spy,
        ):
            await pilot.press("ctrl+v")
            await app.workers.wait_for_complete()
            await pilot.pause()

        assert name_input.value == "Clipboard Session"
        assert name_input.has_focus
        terminal_clipboard.assert_not_awaited()
        write_spy.assert_not_called()


async def test_ctrl_g_toggles_mode_without_reaching_pty(
    sleeping_harness: AgentHarness,
) -> None:
    app, (session,) = _app_with_sessions(sleeping_harness)

    async with app.run_test() as pilot:
        await pilot.pause()
        pty = session.terminal.board.pty
        assert pty is not None
        status = app.query_one(AgentHubStatusBar)

        assert status.query_one("#mode-indicator", Static).content == UNLOCKED_ICON
        assert status.query_one("#mode-label", Static).content == "Unlocked"
        assert status.query_one("#mode-action", Static).content == "Ctrl+G Lock"

        with patch.object(pty, "write", wraps=pty.write) as write_spy:
            await pilot.press("ctrl+g")
            await pilot.pause()

            assert app.hub_locked
            assert status.query_one("#mode-indicator", Static).content == LOCKED_ICON
            assert status.query_one("#mode-label", Static).content == "Locked"
            assert status.query_one("#mode-action", Static).content == "Ctrl+G Unlock"

            await pilot.press("ctrl+g")
            await pilot.pause()

        assert not app.hub_locked
        assert status.query_one("#mode-indicator", Static).content == UNLOCKED_ICON
        assert status.query_one("#mode-label", Static).content == "Unlocked"
        write_spy.assert_not_called()


async def test_locking_preserves_agent_cursor_while_restoring_terminal_focus(
    sleeping_harness: AgentHarness,
) -> None:
    app, sessions = _app_with_sessions(sleeping_harness, count=2)

    async with app.run_test() as pilot:
        await pilot.pause()
        session_list = app.query_one("#sidebar-session-list", OptionList)
        await pilot.press("ctrl+s")
        assert session_list.highlighted == session_list.get_option_index(sessions[1].id)
        await pilot.press("up")
        assert session_list.highlighted == session_list.get_option_index(sessions[0].id)

        await pilot.press("ctrl+g")
        await pilot.pause()

        assert sessions[1].terminal.has_focus
        assert session_list.highlighted == session_list.get_option_index(sessions[0].id)


async def test_locking_preserves_shell_cursor_while_restoring_terminal_focus(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(shell_harness=sleeping_harness)

    async with app.run_test() as pilot:
        app.action_new_shell()
        await pilot.press("enter")
        await pilot.pause()
        app.action_new_shell()
        await pilot.press("enter")
        await pilot.pause()
        session_list = app.query_one("#sidebar-session-list", OptionList)
        await pilot.press("ctrl+s")
        assert session_list.highlighted == 1
        await pilot.press("up")
        assert session_list.highlighted == 0

        active_shell = app.session_manager.active_session
        assert active_shell is not None
        await pilot.press("ctrl+g")
        await pilot.pause()

        assert active_shell.terminal.has_focus
        assert session_list.highlighted == 0


async def test_unlocked_navigation_actions_fire(
    sleeping_harness: AgentHarness,
) -> None:
    app, sessions = _app_with_sessions(sleeping_harness, count=2)
    async with app.run_test() as pilot:
        assert not app.hub_locked

        app.action_new_shell()
        await pilot.press("enter")
        await pilot.pause()
        app.action_new_shell()
        await pilot.press("enter")
        await pilot.pause()

        sidebar = app.query_one(SessionSidebar)
        session_list = app.query_one("#sidebar-session-list", OptionList)
        assert sidebar.selected_tab is SidebarTab.SHELLS
        assert session_list.highlighted == 1

        await pilot.press("ctrl+s")
        assert session_list.has_focus
        assert sidebar.selected_tab is SidebarTab.SHELLS
        assert session_list.highlighted == 1

        await pilot.press("right")
        assert sidebar.selected_tab is SidebarTab.LOADED
        assert session_list.has_focus
        assert session_list.highlighted == session_list.get_option_index(sessions[1].id)


async def test_command_palette_quit_action_exits(
    sleeping_harness: AgentHarness,
) -> None:
    app, _sessions = _app_with_sessions(sleeping_harness)

    async with app.run_test() as pilot:
        await pilot.press("ctrl+p")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette)

        app.screen.query_one(Input).value = "Quit AgentHub"
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("enter")

    assert not app.is_running


async def test_locking_from_command_palette_closes_it_and_refocuses_terminal(
    sleeping_harness: AgentHarness,
) -> None:
    app, (session,) = _app_with_sessions(sleeping_harness)

    async with app.run_test() as pilot:
        await pilot.press("ctrl+p")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette)

        await pilot.press("ctrl+g")
        await pilot.pause()

        assert app.hub_locked
        assert not isinstance(app.screen, CommandPalette)
        assert session.terminal.has_focus


@pytest.mark.parametrize(
    ("stage", "expected_modal"),
    [
        ("harness", HarnessSelectionModal),
        ("cwd", WorkingDirectoryModal),
    ],
)
async def test_locking_cancels_new_session_modal_with_active_terminal(
    sleeping_harness: AgentHarness,
    stage: str,
    expected_modal: type[ModalScreen],
    tmp_path: Path,
) -> None:
    app, (session,) = _app_with_sessions(
        sleeping_harness,
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_new_session()
        await pilot.pause()
        if stage == "cwd":
            await pilot.press("enter")
            await pilot.pause()
        assert isinstance(app.screen, expected_modal)

        await pilot.press("ctrl+g")
        await pilot.pause()

        assert app.hub_locked
        assert not isinstance(
            app.screen,
            (HarnessSelectionModal, SessionNameModal, WorkingDirectoryModal),
        )
        assert app.session_manager.sessions == (session,)
        assert app.session_manager.active_session is session
        assert session.terminal.is_mounted
        assert session.terminal.is_process_running
        assert session.terminal.has_focus


@pytest.mark.parametrize(
    ("stage", "expected_modal", "focus_selector", "focus_type"),
    [
        ("harness", HarnessSelectionModal, "#harness-selection-list", OptionList),
        ("cwd", WorkingDirectoryModal, "#working-directory-tree", FolderTree),
    ],
)
async def test_locking_on_home_keeps_new_session_modal_open(
    sleeping_harness: AgentHarness,
    stage: str,
    expected_modal: type[ModalScreen],
    focus_selector: str,
    focus_type: type[OptionList] | type[Input] | type[FolderTree],
    tmp_path: Path,
) -> None:
    app = AgentHubApp(
        agent_harnesses={sleeping_harness.id: sleeping_harness},
        working_directory_root=tmp_path,
    )

    async with app.run_test() as pilot:
        app.action_new_session()
        await pilot.pause()
        if stage == "cwd":
            await pilot.press("enter")
            await pilot.pause()
        assert isinstance(app.screen, expected_modal)

        await pilot.press("ctrl+g")
        await pilot.pause()

        assert app.hub_locked
        assert isinstance(app.screen, expected_modal)
        assert app.screen.query_one(focus_selector, focus_type).has_focus
        assert app.session_manager.sessions == ()


async def test_ctrl_0_passes_through_to_active_terminal_without_opening_shell(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(shell_harness=sleeping_harness)

    async with app.run_test() as pilot:
        app.action_new_shell()
        await pilot.press("enter")
        await pilot.pause()
        session = app.session_manager.active_session
        assert session is not None
        assert not app.hub_locked
        pty = session.terminal.board.pty
        assert pty is not None

        with patch.object(pty, "write", wraps=pty.write) as write_spy:
            await pilot.press("ctrl+0")
            await pilot.pause()

        write_spy.assert_called_once_with("0")


async def test_ctrl_digit_no_longer_opens_shell_while_unlocked(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(shell_harness=sleeping_harness)

    async with app.run_test() as pilot:
        app.action_new_shell()
        await pilot.press("enter")
        await pilot.pause()
        session = app.session_manager.active_session
        assert session is not None
        pty = session.terminal.board.pty
        assert pty is not None

        with patch.object(pty, "write", wraps=pty.write) as write_spy:
            await pilot.press("ctrl+2")
            await pilot.pause()

        write_spy.assert_called_once_with("2")
        assert len(app.session_manager.sessions) == 1


@pytest.mark.parametrize("key", [str(number) for number in range(1, 10)])
async def test_plain_digits_reach_active_terminal_while_unlocked(
    sleeping_harness: AgentHarness,
    key: str,
) -> None:
    app, (session,) = _app_with_sessions(sleeping_harness)

    async with app.run_test() as pilot:
        await pilot.pause()
        assert session.terminal.has_focus
        pty = session.terminal.board.pty
        assert pty is not None

        with patch.object(pty, "write", wraps=pty.write) as write_spy:
            await pilot.press(key)
            await pilot.pause()

        write_spy.assert_called_once_with(key)
        assert app.session_manager.active_session is session


async def test_ctrl_m_remains_terminal_enter_while_unlocked(
    sleeping_harness: AgentHarness,
) -> None:
    app, (session,) = _app_with_sessions(sleeping_harness)

    async with app.run_test() as pilot:
        await pilot.pause()
        pty = session.terminal.board.pty
        assert pty is not None

        with patch.object(pty, "write", wraps=pty.write) as write_spy:
            await pilot.press("ctrl+m")
            await pilot.pause()

        write_spy.assert_called_once_with("\r")
        assert not isinstance(app.screen, NativeSessionLinkModal)


async def test_home_uses_retained_shortcuts_and_ignores_removed_creation_key() -> None:
    app = AgentHubApp()
    new_session_calls = 0

    def record_new_session() -> None:
        nonlocal new_session_calls
        new_session_calls += 1

    app.action_new_session = record_new_session  # type: ignore[method-assign]

    async with app.run_test(size=(100, 36)) as pilot:
        assert not app.hub_locked

        await pilot.press("ctrl+a")
        assert not app.query_one(SessionSidebar).has_focus

        await pilot.press("ctrl+s")
        assert app.query_one(SessionSidebar).has_focus
        await pilot.press("ctrl+n")
        assert new_session_calls == 0

        await pilot.press("ctrl+p")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, CommandPalette)


@pytest.mark.parametrize(
    ("key", "expected_input"),
    [
        ("ctrl+n", "\x0e"),
        ("ctrl+a", "\x01"),
        ("ctrl+shift+s", "\x13"),
        ("tab", "\t"),
        ("alt+m", "m"),
        ("ctrl+d", "\x04"),
        ("ctrl+q", "\x11"),
    ],
)
async def test_removed_shortcuts_reach_unlocked_terminal(
    sleeping_harness: AgentHarness,
    key: str,
    expected_input: str,
) -> None:
    app, (session,) = _app_with_sessions(sleeping_harness)

    async with app.run_test() as pilot:
        await pilot.pause()
        pty = session.terminal.board.pty
        assert pty is not None

        with patch.object(pty, "write", wraps=pty.write) as write_spy:
            await pilot.press(key)
            await pilot.pause()

        write_spy.assert_called_once_with(expected_input)
        assert app.is_running
        assert app.session_manager.sessions == (session,)
        assert not isinstance(
            app.screen,
            (
                HarnessSelectionModal,
                NativeSessionLinkModal,
                SessionNameModal,
                WorkingDirectoryModal,
            ),
        )
