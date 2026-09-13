"""Integration tests for Textual widget and child-process lifetime."""

from textual.app import App, ComposeResult
from textual.containers import Container

from agenthub.harnesses import AgentHarness
from agenthub.terminal import AgentTerminal


class TwoTerminalApp(App[None]):
    """A test-only DOM with two simultaneously mounted terminal widgets."""

    def __init__(self, harness: AgentHarness) -> None:
        super().__init__()
        self.first = AgentTerminal(harness)
        self.second = AgentTerminal(harness)

    def compose(self) -> ComposeResult:
        yield Container(self.first, self.second)


async def test_hidden_terminal_remains_mounted_and_running(
    sleeping_harness: AgentHarness,
) -> None:
    app = TwoTerminalApp(sleeping_harness)

    async with app.run_test() as pilot:
        await pilot.pause()
        first_process = app.first.board.process
        second_process = app.second.board.process

        assert first_process is not None
        assert second_process is not None
        assert first_process.poll() is None
        assert second_process.poll() is None

        app.set_focus(app.first)
        app.first.display = False
        app.second.display = True
        app.set_focus(app.second)
        await pilot.pause()

        assert app.first.is_mounted
        assert app.second.is_mounted
        assert not app.first.has_focus
        assert app.second.has_focus
        assert first_process.poll() is None
        assert second_process.poll() is None

    assert first_process.wait(timeout=1) is not None
    assert second_process.wait(timeout=1) is not None
