"""Integration tests for application and terminal lifecycle behavior."""

import sys
from pathlib import Path

from textual.widgets import Static

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness, KeyStroke, ScrollKeys
from agenthub.sessions import AgentSession
from agenthub.ui import AgentHubStatusBar


def _app_with_session(harness: AgentHarness) -> tuple[AgentHubApp, AgentSession]:
    app = AgentHubApp()
    session = app.session_manager.create(
        name=harness.display_name,
        cwd=Path.cwd(),
        harness=harness,
    )
    return app, session


async def test_ctrl_q_exits_while_terminal_has_focus(
    sleeping_harness: AgentHarness,
) -> None:
    app, created_session = _app_with_session(sleeping_harness)

    async with app.run_test() as pilot:
        await pilot.pause()
        session = app.session_manager.active_session
        assert session is created_session
        process = session.terminal.board.process
        assert process is not None
        assert session.terminal.has_focus

        status = app.query_one(AgentHubStatusBar)
        assert status.query_one("#status-label", Static).content == "Running"
        assert status.query_one("#session-count", Static).content == "Sessions 1"
        assert status.query_one("#agent-count", Static).content == "Agents 1"

        await pilot.press("ctrl+q")

    assert not app.is_running
    assert process.wait(timeout=1) is not None


async def test_only_child_exiting_closes_the_application() -> None:
    harness = AgentHarness(
        id="test-exit",
        display_name="Test Exit",
        command=(sys.executable, "-c", "raise SystemExit(9)"),
        scroll=ScrollKeys(
            down=KeyStroke("e", ctrl=True, alt=True),
            up=KeyStroke("y", ctrl=True, alt=True),
        ),
    )
    app, _session = _app_with_session(harness)

    async with app.run_test() as pilot:
        for _ in range(20):
            if not app.is_running:
                break
            await pilot.pause(0.05)

    assert not app.is_running
