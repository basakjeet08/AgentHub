"""Unit coverage for clipboard ownership in the session-name modal."""

from collections.abc import Coroutine
from unittest.mock import Mock

from textual.app import App, ComposeResult
from textual.widgets import Input

from agenthub.presentation.modals.shell_session_name import (
    SessionNameInput,
    ShellSessionNameModal,
)


def test_ctrl_v_schedules_a_widget_owned_clipboard_worker(monkeypatch) -> None:
    name_input = SessionNameInput()
    run_worker = Mock()
    monkeypatch.setattr(name_input, "run_worker", run_worker)

    name_input.action_paste()

    assert run_worker.call_count == 1
    scheduled_paste = run_worker.call_args.args[0]
    assert isinstance(scheduled_paste, Coroutine)
    assert run_worker.call_args.kwargs == {
        "group": "clipboard-paste",
        "exclusive": True,
        "exit_on_error": False,
    }
    scheduled_paste.close()


async def test_shell_session_name_modal_uses_default_name_when_submitted_blank() -> None:
    result: list[str | None] = []

    class ModalTestApp(App):
        def compose(self) -> ComposeResult:
            yield from ()

    app = ModalTestApp()
    async with app.run_test() as pilot:
        modal = ShellSessionNameModal()
        app.push_screen(modal, callback=result.append)
        await pilot.pause()

        # Submit with empty value
        await pilot.press("enter")
        await pilot.pause()
        assert result == ["Shell"]


async def test_shell_session_name_modal_trims_whitespace() -> None:
    result: list[str | None] = []

    class ModalTestApp(App):
        def compose(self) -> ComposeResult:
            yield from ()

    app = ModalTestApp()
    async with app.run_test() as pilot:
        modal = ShellSessionNameModal()
        app.push_screen(modal, callback=result.append)
        await pilot.pause()

        input_widget = modal.query_one("#session-name-input", Input)
        input_widget.value = "   Custom Shell   "
        await pilot.press("enter")
        await pilot.pause()

        assert result == ["Custom Shell"]
