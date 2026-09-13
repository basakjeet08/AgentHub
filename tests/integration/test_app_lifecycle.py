"""Integration tests for application and terminal lifecycle behavior."""

from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness


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
