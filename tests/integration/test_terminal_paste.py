"""Integration coverage for system-clipboard paste into the terminal PTY."""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from textual import events
from textual.app import App, ComposeResult

from agenthub.clipboard import ClipboardContent, ClipboardKind
from agenthub.harnesses import AgentHarness
from agenthub.terminal import AgentTerminal


class TerminalPasteApp(App[None]):
    """A fixed-size terminal host for paste tests."""

    def __init__(self, harness: AgentHarness) -> None:
        super().__init__()
        self.terminal = AgentTerminal(harness)

    def compose(self) -> ComposeResult:
        yield self.terminal


def _written_calls(write_spy) -> list[tuple]:
    return [call.args for call in write_spy.call_args_list]


async def _wait_for_pty_write(pilot, write_spy, expected: str) -> None:
    """Pause until the paste reaches the PTY or a safety bound expires."""

    expected_bytes = expected.encode("utf-8")
    for _ in range(100):
        await pilot.pause()
        if any(call.args == (expected_bytes,) for call in write_spy.call_args_list):
            return
    raise AssertionError(f"PTY never received {expected!r}: {write_spy.call_args_list}")


async def _settle(pilot) -> None:
    """Let any scheduled clipboard worker finish before asserting no writes."""

    for _ in range(10):
        await pilot.pause()


def _patch_clipboard(value: str | ClipboardContent | None):
    if isinstance(value, ClipboardContent):
        content = value
    elif value is None:
        content = ClipboardContent(ClipboardKind.UNAVAILABLE)
    elif value == "":
        content = ClipboardContent(ClipboardKind.EMPTY)
    else:
        content = ClipboardContent(ClipboardKind.TEXT, value)

    return patch(
        "agenthub.terminal.widget._CLIPBOARD_SERVICE.read",
        AsyncMock(return_value=content),
    )


async def test_ctrl_v_pastes_system_clipboard_text_into_the_pty(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalPasteApp(sleeping_harness)

    async with app.run_test(size=(80, 24)) as pilot:
        terminal = app.terminal
        pty = terminal.board.pty
        assert pty is not None

        with (
            _patch_clipboard("hello from clipboard"),
            patch.object(pty, "write_bytes", wraps=pty.write_bytes) as write_spy,
        ):
            await pilot.press("ctrl+v")
            await _wait_for_pty_write(pilot, write_spy, "hello from clipboard")

        assert _written_calls(write_spy) == [(b"hello from clipboard",)]


async def test_ctrl_v_does_not_forward_a_literal_control_character(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalPasteApp(sleeping_harness)

    async with app.run_test(size=(80, 24)) as pilot:
        terminal = app.terminal
        pty = terminal.board.pty
        assert pty is not None

        with (
            _patch_clipboard("hello from clipboard"),
            patch.object(pty, "write_bytes", wraps=pty.write_bytes) as write_spy,
        ):
            await pilot.press("ctrl+v")
            await _wait_for_pty_write(pilot, write_spy, "hello from clipboard")

        assert (b"\x16",) not in _written_calls(write_spy)


async def test_ctrl_v_multiline_clipboard_is_one_paste_operation(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalPasteApp(sleeping_harness)

    async with app.run_test(size=(80, 24)) as pilot:
        terminal = app.terminal
        pty = terminal.board.pty
        assert pty is not None
        multiline = "first line\nsecond line\n"

        with (
            _patch_clipboard(multiline),
            patch.object(pty, "write_bytes", wraps=pty.write_bytes) as write_spy,
        ):
            await pilot.press("ctrl+v")
            await _wait_for_pty_write(pilot, write_spy, multiline)

        assert _written_calls(write_spy) == [(multiline.encode("utf-8"),)]


async def test_repeated_ctrl_v_events_submit_one_paste(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalPasteApp(sleeping_harness)
    text = "one clipboard paste"
    clipboard_reader = AsyncMock(return_value=ClipboardContent(ClipboardKind.TEXT, text))

    async with app.run_test(size=(80, 24)) as pilot:
        terminal = app.terminal
        pty = terminal.board.pty
        assert pty is not None

        with (
            patch("agenthub.terminal.widget._CLIPBOARD_SERVICE.read", clipboard_reader),
            patch.object(pty, "write_bytes", wraps=pty.write_bytes) as write_spy,
        ):
            for _ in range(20):
                await pilot.press("ctrl+v")
            await _wait_for_pty_write(pilot, write_spy, text)
            await _settle(pilot)

        clipboard_reader.assert_awaited_once_with()
        assert _written_calls(write_spy) == [(text.encode("utf-8"),)]


async def test_ctrl_v_falls_back_to_agenthub_clipboard_without_a_backend(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalPasteApp(sleeping_harness)

    async with app.run_test(size=(80, 24)) as pilot:
        app.copy_to_clipboard("internal clipboard text")
        terminal = app.terminal
        pty = terminal.board.pty
        assert pty is not None

        with (
            _patch_clipboard(None),
            patch.object(pty, "write_bytes", wraps=pty.write_bytes) as write_spy,
        ):
            await pilot.press("ctrl+v")
            await _wait_for_pty_write(pilot, write_spy, "internal clipboard text")


async def test_empty_clipboard_generates_no_pty_input(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalPasteApp(sleeping_harness)

    async with app.run_test(size=(80, 24)) as pilot:
        terminal = app.terminal
        pty = terminal.board.pty
        assert pty is not None

        with (
            _patch_clipboard(""),
            patch.object(pty, "write_bytes", wraps=pty.write_bytes) as write_spy,
        ):
            await pilot.press("ctrl+v")
            await _settle(pilot)

        assert write_spy.call_args_list == []


async def test_unavailable_clipboard_warns_and_sends_nothing(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalPasteApp(sleeping_harness)

    async with app.run_test(size=(80, 24)) as pilot:
        terminal = app.terminal
        pty = terminal.board.pty
        assert pty is not None

        with (
            _patch_clipboard(None),
            patch.object(pty, "write_bytes", wraps=pty.write_bytes) as write_spy,
            patch.object(app, "notify", wraps=app.notify) as notify_spy,
        ):
            await pilot.press("ctrl+v")
            await _settle(pilot)

        assert write_spy.call_args_list == []
        assert notify_spy.call_count == 1
        assert notify_spy.call_args.kwargs.get("severity") == "warning"


async def test_ctrl_v_forwards_control_character_for_non_text_clipboard(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalPasteApp(sleeping_harness)

    async with app.run_test(size=(80, 24)) as pilot:
        terminal = app.terminal
        pty = terminal.board.pty
        assert pty is not None

        with (
            _patch_clipboard(ClipboardContent(ClipboardKind.NON_TEXT)),
            patch.object(pty, "write_bytes", wraps=pty.write_bytes) as write_spy,
            patch.object(app, "notify", wraps=app.notify) as notify_spy,
        ):
            await pilot.press("ctrl+v")
            await _settle(pilot)

        assert (b"\x16",) in _written_calls(write_spy)
        assert notify_spy.call_count == 0


async def test_textual_paste_event_still_reaches_the_paste_port(
    sleeping_harness: AgentHarness,
) -> None:
    app = TerminalPasteApp(sleeping_harness)

    async with app.run_test(size=(80, 24)) as pilot:
        terminal = app.terminal
        pty = terminal.board.pty
        assert pty is not None

        with patch.object(pty, "write_bytes", wraps=pty.write_bytes) as write_spy:
            terminal.post_message(events.Paste("bracketed paste text"))
            await _wait_for_pty_write(pilot, write_spy, "bracketed paste text")

        assert _written_calls(write_spy) == [(b"bracketed paste text",)]


@pytest.mark.parametrize("paste_source", ["ctrl+v", "event"])
@pytest.mark.parametrize(
    "text",
    [
        "hello from clipboard",
        "first line\n\tsecond line\n",
        "Unicode: café 🚀 你好\n",
        pytest.param(
            "".join(f"line {line:04d} " + "x" * 75 + "\n" for line in range(1000)),
            id="large-1000-lines",
        ),
    ],
)
async def test_paste_reaches_a_real_child_exactly(
    tmp_path: Path,
    text: str,
    paste_source: str,
) -> None:
    output_path = tmp_path / "received"
    ready_path = tmp_path / "ready"
    script = """
import os
import sys
import time
import tty
from pathlib import Path

tty.setraw(sys.stdin.fileno())
size = int(sys.argv[3])
Path(sys.argv[2]).touch()
data = b""
while len(data) < size:
    data += os.read(sys.stdin.fileno(), size - len(data))
Path(sys.argv[1]).write_bytes(data)
time.sleep(30)
"""
    harness = AgentHarness(
        id="paste-child",
        display_name="Paste Child",
        command=(
            sys.executable,
            "-c",
            script,
            str(output_path),
            str(ready_path),
            str(len(text.encode("utf-8"))),
        ),
        scroll=None,
    )
    app = TerminalPasteApp(harness)

    async with app.run_test(size=(80, 24)) as pilot:
        for _ in range(100):
            await pilot.pause()
            if ready_path.exists():
                break
        assert ready_path.exists()

        if paste_source == "ctrl+v":
            with _patch_clipboard(text):
                await pilot.press("ctrl+v")
        else:
            app.terminal.post_message(events.Paste(text))
        for _ in range(100):
            await pilot.pause()
            if output_path.exists():
                break

        assert output_path.read_bytes() == text.encode("utf-8")
