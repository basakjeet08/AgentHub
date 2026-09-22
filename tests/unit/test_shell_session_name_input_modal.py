"""Unit coverage for the shell-session name modal."""

from textual.app import App, ComposeResult
from textual.widgets import Input

from agenthub.presentation.modals.shell_session_name_input import (
    ShellSessionNameInputModal,
)


async def test_shell_session_name_input_modal_uses_default_name_when_submitted_blank() -> None:
    result: list[str | None] = []

    class ModalTestApp(App):
        def compose(self) -> ComposeResult:
            yield from ()

    app = ModalTestApp()
    async with app.run_test() as pilot:
        modal = ShellSessionNameInputModal()
        app.push_screen(modal, callback=result.append)
        await pilot.pause()

        # Submit with empty value
        await pilot.press("enter")
        await pilot.pause()
        assert result == ["Shell"]


async def test_shell_session_name_input_modal_trims_whitespace() -> None:
    result: list[str | None] = []

    class ModalTestApp(App):
        def compose(self) -> ComposeResult:
            yield from ()

    app = ModalTestApp()
    async with app.run_test() as pilot:
        modal = ShellSessionNameInputModal()
        app.push_screen(modal, callback=result.append)
        await pilot.pause()

        input_widget = modal.query_one("#shell-session-name-input", Input)
        input_widget.value = "   Custom Shell   "
        await pilot.press("enter")
        await pilot.pause()

        assert result == ["Custom Shell"]
