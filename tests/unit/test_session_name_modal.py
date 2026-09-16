"""Unit coverage for clipboard ownership in the session-name modal."""

from collections.abc import Coroutine
from unittest.mock import Mock

from agenthub.ui.modals.session_name import SessionNameInput


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
