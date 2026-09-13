"""Tests for application orchestration and ownership."""

from pathlib import Path

import pytest

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness


def test_app_creates_one_initial_session(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(sleeping_harness)

    assert len(app.session_manager.sessions) == 1
    session = app.session_manager.active_session
    assert session is not None
    assert session.name == sleeping_harness.display_name
    assert session.cwd == Path.cwd()
    assert session.harness is sleeping_harness
    assert session.terminal.harness is sleeping_harness


def test_app_rejects_an_unsupported_launch_directory(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    with pytest.raises(NotImplementedError, match="different working directory"):
        AgentHubApp(sleeping_harness, cwd=tmp_path)


def test_quit_binding_has_priority_over_terminal_input() -> None:
    binding = AgentHubApp.BINDINGS[0]

    assert binding.key == "ctrl+q"
    assert binding.action == "quit"
    assert binding.priority is True


async def test_ctrl_q_exits_while_terminal_has_focus(
    sleeping_harness: AgentHarness,
) -> None:
    app = AgentHubApp(sleeping_harness)

    async with app.run_test() as pilot:
        await pilot.pause()
        session = app.session_manager.active_session
        assert session is not None
        process = session.terminal.board.process
        assert process is not None
        assert session.terminal.has_focus

        await pilot.press("ctrl+q")

    assert not app.is_running
    assert process.wait(timeout=1) is not None
