"""Integration tests for manager-backed session navigation."""

import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

from textual.widgets import ContentSwitcher, OptionList, Static

from agenthub.app import AgentHubApp
from agenthub.harnesses import (
    ANTIGRAVITY,
    CODEX,
    DEVIN,
    OPENCODE,
    AgentHarness,
    KeyStroke,
    ScrollKeys,
)
from agenthub.sessions import AgentSession, SessionKind, SessionState
from agenthub.ui import HomeScreen, SessionSidebar, SidebarTab


def _exiting_harness(exit_code: int) -> AgentHarness:
    return AgentHarness(
        id="test-exit",
        display_name="Test Exit",
        command=(sys.executable, "-c", f"raise SystemExit({exit_code})"),
        scroll=ScrollKeys(
            down=KeyStroke("e", ctrl=True, alt=True),
            up=KeyStroke("y", ctrl=True, alt=True),
        ),
    )


def _script_harness(harness_id: str, script: str, *args: str) -> AgentHarness:
    return AgentHarness(
        id=harness_id,
        display_name=harness_id,
        command=(sys.executable, "-c", script, *args),
        scroll=ScrollKeys(
            down=KeyStroke("e", ctrl=True, alt=True),
            up=KeyStroke("y", ctrl=True, alt=True),
        ),
    )


def _app_with_session(
    harness: AgentHarness,
    *,
    cwd: Path | None = None,
) -> tuple[AgentHubApp, AgentSession]:
    app = AgentHubApp()
    session = app.session_manager.create(
        name=harness.display_name,
        kind=SessionKind.AGENT,
        cwd=cwd or Path.cwd(),
        harness=harness,
    )
    return app, session


async def test_sidebar_switches_managed_sessions(
    sleeping_harness: AgentHarness,
) -> None:
    app, first = _app_with_session(sleeping_harness)
    second = app.session_manager.create(
        name="Second",
        kind=SessionKind.AGENT,
        cwd=first.cwd,
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        switcher = app.query_one("#session-content", ContentSwitcher)
        sidebar = app.query_one(SessionSidebar)
        first_process = first.terminal.board.process
        second_process = second.terminal.board.process

        assert first_process is not None
        assert second_process is not None
        assert first.terminal.is_mounted
        assert second.terminal.is_mounted
        assert not first.terminal.display
        assert second.terminal.display
        assert second.terminal.has_focus
        assert app.session_manager.active_session is second
        assert switcher.current == app._terminal_dom_id(second.id)

        sidebar.move_cursor_to_session(first.id)
        sidebar.focus_sidebar()
        await pilot.press("enter")

        assert app.session_manager.active_session is first
        assert first.terminal.display
        assert not second.terminal.display
        assert first.terminal.has_focus
        assert not second.terminal.has_focus
        assert first_process.poll() is None
        assert second_process.poll() is None

        sidebar.move_cursor_to_session(second.id)
        sidebar.focus_sidebar()
        await pilot.press("enter")

        assert app.session_manager.active_session is second
        assert not first.terminal.display
        assert second.terminal.display
        assert second.terminal.has_focus

        sidebar.move_cursor_to_session(first.id)
        sidebar.focus_sidebar()
        await pilot.press("enter")

        assert app.session_manager.active_session is first
        assert first.terminal.display
        assert first.terminal.has_focus

        sidebar.move_cursor_to_session(second.id)
        sidebar.focus_sidebar()
        await pilot.press("enter")

        assert app.session_manager.active_session is second
        assert not first.terminal.display
        assert second.terminal.display
        assert not first.terminal.has_focus
        assert second.terminal.has_focus
        assert switcher.current == app._terminal_dom_id(second.id)
        assert first_process.poll() is None
        assert second_process.poll() is None

    assert first_process.wait(timeout=1) is not None
    assert second_process.wait(timeout=1) is not None


async def test_all_registered_agent_types_coexist_and_survive_switching(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    harnesses = tuple(
        replace(harness, command=sleeping_harness.command)
        for harness in (ANTIGRAVITY, CODEX, DEVIN, OPENCODE)
    )
    directories = tuple(tmp_path / harness.id for harness in harnesses)
    for directory in directories:
        directory.mkdir()
    app = AgentHubApp(
        agent_harnesses={harness.id: harness for harness in harnesses},
        working_directory_root=tmp_path,
    )
    agenthub_directory = Path.cwd()

    async with app.run_test() as pilot:
        sessions = tuple(
            [
                await app._create_agent_session(
                    harness=harness,
                    cwd=directory,
                )
                for harness, directory in zip(harnesses, directories, strict=True)
            ]
        )
        await pilot.pause()
        processes = tuple(session.terminal.board.process for session in sessions)

        assert app.session_manager.sessions == sessions
        assert tuple(session.harness for session in sessions) == harnesses
        assert tuple(session.cwd for session in sessions) == tuple(
            directory.resolve() for directory in directories
        )
        assert all(session.terminal.is_mounted for session in sessions)
        assert all(session.terminal.is_process_running for session in sessions)
        assert all(process is not None for process in processes)
        assert app.session_manager.active_session is sessions[-1]
        assert sessions[-1].terminal.has_focus

        for selected in sessions:
            app.show_session(selected.id)
            await pilot.pause()

            assert app.session_manager.active_session is selected
            assert selected.terminal.has_focus
            assert all(session.terminal.is_process_running for session in sessions)
            assert tuple(session.terminal.board.process for session in sessions) == processes

        assert Path.cwd() == agenthub_directory

    assert Path.cwd() == agenthub_directory


async def test_process_exit_is_resolved_to_owning_session(
    sleeping_harness: AgentHarness,
) -> None:
    app, first = _app_with_session(sleeping_harness)
    second = app.session_manager.create(
        name="Exits",
        kind=SessionKind.AGENT,
        cwd=first.cwd,
        harness=_exiting_harness(7),
    )
    exit_handler = AsyncMock()
    app._handle_session_process_exited = exit_handler  # type: ignore[method-assign]

    async with app.run_test() as pilot:
        for _ in range(20):
            await pilot.pause(0.05)
            if exit_handler.called:
                break

        exit_handler.assert_awaited_once_with(second, 7)


async def test_active_exit_returns_home_while_other_session_keeps_running(
    sleeping_harness: AgentHarness,
) -> None:
    app, first = _app_with_session(sleeping_harness)
    second = app.session_manager.create(
        name="Exits",
        kind=SessionKind.AGENT,
        cwd=first.cwd,
        harness=_exiting_harness(7),
    )

    async with app.run_test() as pilot:
        for _ in range(20):
            if second not in app.session_manager.sessions:
                break
            await pilot.pause(0.05)
        await pilot.pause()

        assert app.is_running
        assert app.session_manager.sessions == (first,)
        assert app.session_manager.active_session is None
        assert first.terminal.is_process_running
        assert not first.terminal.display
        home = app.query_one(HomeScreen)
        assert home.display
        assert home.has_focus
        assert home.query_one("#home-empty-copy", Static).content == (
            "Select a session from the sidebar\nor start a new coding-agent session."
        )
        assert app.query_one("#session-content", ContentSwitcher).current == "home-screen"
        assert all(
            session_list.highlighted is None for session_list in app.query(OptionList)
        )

        await pilot.press("ctrl+s")
        await pilot.press("enter")
        await pilot.pause()
        assert app.session_manager.active_session is first
        assert first.terminal.display
        assert first.terminal.has_focus


async def test_hidden_exit_is_removed_without_interrupting_active_session(
    sleeping_harness: AgentHarness,
) -> None:
    delayed_exit = _script_harness(
        "delayed-exit",
        "import time; time.sleep(0.2)",
    )
    app, first = _app_with_session(delayed_exit)
    second = app.session_manager.create(
        name="Active",
        kind=SessionKind.AGENT,
        cwd=first.cwd,
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        for _ in range(20):
            if first not in app.session_manager.sessions:
                break
            await pilot.pause(0.05)
        await pilot.pause()

        assert app.session_manager.sessions == (second,)
        assert app.session_manager.active_session is second
        assert second.terminal.display
        assert second.terminal.has_focus
        assert app.query_one("#session-content", ContentSwitcher).current == (
            app._terminal_dom_id(second.id)
        )
        assert app.query_one(SessionSidebar).visible_session_ids == (second.id,)


async def test_active_native_backed_exit_retains_unloaded_resumable_row(
    tmp_path: Path,
) -> None:
    app, session = _app_with_session(_exiting_harness(7), cwd=tmp_path)
    session.native_session_id = "native-exit"

    async with app.run_test() as pilot:
        for _ in range(20):
            if session.terminal is None:
                break
            await pilot.pause(0.05)
        await pilot.pause()

        assert app.session_manager.sessions == (session,)
        assert app.session_manager.active_session is None
        assert session.native_session_id == "native-exit"
        assert session.terminal is None
        assert session.state is SessionState.UNLOADED
        assert app.query_one(HomeScreen).display
        assert app.query_one(HomeScreen).has_focus
        sidebar = app.query_one(SessionSidebar)
        assert sidebar.visible_session_ids == ()
        assert sidebar.tab_counts[SidebarTab.UNLOADED] == 1


async def test_hidden_native_backed_exit_does_not_interrupt_active_sibling(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    delayed_exit = _script_harness(
        "linked-delayed-exit",
        "import time; time.sleep(0.2)",
    )
    app, linked = _app_with_session(delayed_exit, cwd=tmp_path)
    linked.native_session_id = "native-linked"
    active = app.session_manager.create(
        name="Active",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        for _ in range(20):
            if linked.terminal is None:
                break
            await pilot.pause(0.05)
        await pilot.pause()

        assert app.session_manager.sessions == (linked, active)
        assert linked.state is SessionState.UNLOADED
        assert linked.terminal is None
        assert app.session_manager.active_session is active
        assert active.terminal is not None
        assert active.terminal.is_process_running
        assert active.terminal.display
        assert active.terminal.has_focus
        sidebar = app.query_one(SessionSidebar)
        assert sidebar.visible_session_ids == (active.id,)
        assert sidebar.tab_counts[SidebarTab.UNLOADED] == 1


async def test_hidden_output_and_screen_state_survive_switching(
    sleeping_harness: AgentHarness,
) -> None:
    output_harness = _script_harness(
        "test-output",
        "import time; "
        "print('before-hide', flush=True); "
        "time.sleep(0.15); "
        "print('while-hidden', flush=True); "
        "time.sleep(30)",
    )
    app, first = _app_with_session(output_harness)
    second = app.session_manager.create(
        name="Second",
        kind=SessionKind.AGENT,
        cwd=first.cwd,
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        await pilot.pause(0.3)

        assert app.session_manager.active_session is second
        assert not first.terminal.display
        hidden_screen = first.terminal.board.capture_pane()
        assert "before-hide" in hidden_screen
        assert "while-hidden" in hidden_screen

        sidebar = app.query_one(SessionSidebar)
        sidebar.move_cursor_to_session(first.id)
        sidebar.focus_sidebar()
        await pilot.press("enter")

        assert first.terminal.display
        assert first.terminal.has_focus
        restored_screen = first.terminal.board.capture_pane()
        assert "before-hide" in restored_screen
        assert "while-hidden" in restored_screen


async def test_keyboard_input_reaches_only_active_terminal(tmp_path: Path) -> None:
    script = (
        "import pathlib, sys, time, tty; "
        "tty.setcbreak(sys.stdin.fileno()); "
        "value = sys.stdin.read(1); "
        "pathlib.Path(sys.argv[1]).write_text(value); "
        "time.sleep(30)"
    )
    first_output = tmp_path / "first-input.txt"
    second_output = tmp_path / "second-input.txt"
    first_harness = _script_harness("test-input-a", script, str(first_output))
    second_harness = _script_harness("test-input-b", script, str(second_output))
    app, first = _app_with_session(first_harness)
    second = app.session_manager.create(
        name="Second",
        kind=SessionKind.AGENT,
        cwd=first.cwd,
        harness=second_harness,
    )

    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        assert app.session_manager.active_session is second
        assert second.terminal.has_focus

        await pilot.press("x")
        for _ in range(20):
            if second_output.exists():
                break
            await pilot.pause(0.05)

        assert second_output.read_text() == "x"
        assert not first_output.exists()


async def test_concurrent_children_inherit_distinct_session_directories(
    tmp_path: Path,
) -> None:
    first_directory = tmp_path / "first-project"
    second_directory = tmp_path / "second-project"
    first_directory.mkdir()
    second_directory.mkdir()
    first_output = tmp_path / "first-cwd.txt"
    second_output = tmp_path / "second-cwd.txt"
    script = (
        "import pathlib, sys, time; "
        "pathlib.Path(sys.argv[1]).write_text(str(pathlib.Path.cwd())); "
        "time.sleep(30)"
    )
    first_harness = _script_harness("test-cwd-a", script, str(first_output))
    second_harness = _script_harness("test-cwd-b", script, str(second_output))
    agenthub_directory = Path.cwd()
    app, _first = _app_with_session(first_harness, cwd=first_directory)
    second = app.session_manager.create(
        name="Second",
        kind=SessionKind.AGENT,
        cwd=second_directory,
        harness=second_harness,
    )

    async with app.run_test() as pilot:
        for _ in range(20):
            if first_output.exists() and second_output.exists():
                break
            await pilot.pause(0.05)

        assert first_output.read_text() == str(first_directory)
        assert second_output.read_text() == str(second_directory)
        assert Path.cwd() == agenthub_directory
        assert second.terminal.board.process is not None
        assert second.terminal.board.process.poll() is None

    assert Path.cwd() == agenthub_directory
