"""Integration tests for manager-backed session navigation."""

import sys
from pathlib import Path
from unittest.mock import Mock

from textual.widgets import ContentSwitcher

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness, KeyStroke, ScrollKeys
from agenthub.ui import SessionSidebar


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


async def test_keyboard_and_sidebar_switch_managed_sessions(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(sleeping_harness)
    first = app.session_manager.active_session
    assert first is not None
    second = app.session_manager.create(
        name="Second",
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

        await pilot.press("ctrl+1")

        assert app.session_manager.active_session is first
        assert first.terminal.display
        assert not second.terminal.display
        assert first.terminal.has_focus
        assert not second.terminal.has_focus
        assert first_process.poll() is None
        assert second_process.poll() is None

        await pilot.press("ctrl+2")

        assert app.session_manager.active_session is second
        assert not first.terminal.display
        assert second.terminal.display
        assert second.terminal.has_focus

        await pilot.press("ctrl+1")

        assert app.session_manager.active_session is first
        assert first.terminal.display
        assert first.terminal.has_focus

        app.set_focus(sidebar)
        sidebar.set_active(second.id)
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


async def test_process_exit_is_resolved_to_owning_session(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(sleeping_harness)
    first = app.session_manager.active_session
    assert first is not None
    second = app.session_manager.create(
        name="Exits",
        cwd=first.cwd,
        harness=_exiting_harness(7),
    )
    exit_handler = Mock()
    app._handle_session_process_exited = exit_handler  # type: ignore[method-assign]

    async with app.run_test() as pilot:
        for _ in range(20):
            await pilot.pause(0.05)
            if exit_handler.called:
                break

        exit_handler.assert_called_once_with(second, 7)


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
    app = AgentHubApp(output_harness)
    first = app.session_manager.active_session
    assert first is not None
    second = app.session_manager.create(
        name="Second",
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

        await pilot.press("ctrl+1")

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
    app = AgentHubApp(first_harness)
    first = app.session_manager.active_session
    assert first is not None
    second = app.session_manager.create(
        name="Second",
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
    app = AgentHubApp(first_harness, cwd=first_directory)
    second = app.session_manager.create(
        name="Second",
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
