"""Unit tests for the AgentTerminal-to-Bitty translation boundary."""

import os
from collections.abc import Coroutine
from pathlib import Path
from unittest.mock import Mock

import pytest
from bittty import constants
from rich.segment import Segment
from rich.style import Style as RichStyle
from textual import events
from textual.strip import Strip
from textual_tty import Terminal as TtyTerminal

from agenthub._terminal_launcher import build_launch_command, launch
from agenthub.harnesses import AgentHarness, KeyStroke
from agenthub.terminal import AgentTerminal
from agenthub.terminal.widget import _bittty_modifier


@pytest.mark.parametrize(
    ("key_stroke", "expected"),
    [
        (KeyStroke("x"), constants.KEY_MOD_NONE),
        (KeyStroke("x", shift=True), constants.KEY_MOD_SHIFT),
        (KeyStroke("x", alt=True), constants.KEY_MOD_ALT),
        (KeyStroke("x", shift=True, alt=True), constants.KEY_MOD_SHIFT_ALT),
        (KeyStroke("x", ctrl=True), constants.KEY_MOD_CTRL),
        (KeyStroke("x", shift=True, ctrl=True), constants.KEY_MOD_SHIFT_CTRL),
        (KeyStroke("x", alt=True, ctrl=True), constants.KEY_MOD_ALT_CTRL),
        (
            KeyStroke("x", shift=True, alt=True, ctrl=True),
            constants.KEY_MOD_SHIFT_ALT_CTRL,
        ),
    ],
)
def test_semantic_modifiers_are_translated_at_terminal_boundary(
    key_stroke: KeyStroke,
    expected: int,
) -> None:
    assert _bittty_modifier(key_stroke) == expected


def test_wheel_uses_harness_scroll_policy(
    sleeping_harness: AgentHarness,
    monkeypatch,
) -> None:
    terminal = AgentTerminal(sleeping_harness)
    input_key = Mock()
    event = Mock()
    monkeypatch.setattr(terminal.board.display, "input_key", input_key)

    terminal._wheel(event, constants.MOUSE_BUTTON_WHEEL_DOWN, "down")

    assert input_key.call_count == sleeping_harness.scroll.steps
    input_key.assert_called_with("e", constants.KEY_MOD_ALT_CTRL)
    event.stop.assert_called_once_with()


def test_ctrl_backspace_sends_terminal_word_erase(
    sleeping_harness: AgentHarness,
    monkeypatch,
) -> None:
    terminal = AgentTerminal(sleeping_harness)
    input_data = Mock()
    monkeypatch.setattr(terminal.board.display, "input", input_data)

    terminal.on_key(events.Key("ctrl+backspace", None))

    input_data.assert_called_once_with("\x17")


def test_ctrl_v_schedules_a_system_clipboard_worker(
    sleeping_harness: AgentHarness,
    monkeypatch,
) -> None:
    terminal = AgentTerminal(sleeping_harness)
    run_worker = Mock()
    monkeypatch.setattr(terminal, "run_worker", run_worker)

    terminal.on_key(events.Key("ctrl+v", None))

    assert run_worker.call_count == 1
    scheduled_paste = run_worker.call_args.args[0]
    assert isinstance(scheduled_paste, Coroutine)
    assert run_worker.call_args.kwargs["group"] == "clipboard-paste"
    scheduled_paste.close()


async def test_paste_text_uses_the_native_paste_port(
    sleeping_harness: AgentHarness,
    monkeypatch,
) -> None:
    terminal = AgentTerminal(sleeping_harness)
    terminal.board.host.connection = Mock()
    input_paste = Mock()
    monkeypatch.setattr(terminal.board.display, "input_paste", input_paste)

    await terminal.paste_text("one\ntwo\t🚀")

    input_paste.assert_called_once_with("one\ntwo\t🚀")


async def test_paste_text_retries_partial_writes_inside_one_bracketed_paste(
    sleeping_harness: AgentHarness,
) -> None:
    terminal = AgentTerminal(sleeping_harness)
    written_chunks: list[bytes] = []
    connection = Mock()

    def write_partial(data: bytes) -> int:
        chunk = data[:7]
        written_chunks.append(chunk)
        return len(chunk)

    connection.write_bytes = write_partial
    terminal.board.host.connection = connection
    terminal.board.modes.bracketed_paste = True

    await terminal.paste_text("one\ntwo")

    assert b"".join(written_chunks) == b"\x1b[200~one\ntwo\x1b[201~"


@pytest.mark.parametrize(
    "key",
    [
        "super+a",
        "super+v",
        "hyper+a",
        "ctrl+super+a",
        "shift+hyper+x",
        "super+enter",
    ],
)
def test_unsupported_modifier_keys_are_consumed_without_raising(
    sleeping_harness: AgentHarness,
    monkeypatch,
    key: str,
) -> None:
    terminal = AgentTerminal(sleeping_harness)
    parent_on_key = Mock()
    input_key = Mock()
    input_data = Mock()
    input_paste = Mock()
    monkeypatch.setattr(TtyTerminal, "on_key", parent_on_key)
    monkeypatch.setattr(terminal.board.display, "input_key", input_key)
    monkeypatch.setattr(terminal.board.display, "input", input_data)
    monkeypatch.setattr(terminal.board.display, "input_paste", input_paste)

    terminal.on_key(events.Key(key, None))

    parent_on_key.assert_not_called()
    input_key.assert_not_called()
    input_data.assert_not_called()
    input_paste.assert_not_called()


@pytest.mark.parametrize("key", ["ctrl+a", "alt+a", "meta+a", "shift+a", "a"])
def test_supported_modifier_keys_still_delegate_to_textual_tty(
    sleeping_harness: AgentHarness,
    monkeypatch,
    key: str,
) -> None:
    terminal = AgentTerminal(sleeping_harness)
    parent_on_key = Mock()
    monkeypatch.setattr(TtyTerminal, "on_key", parent_on_key)
    event = events.Key(key, None)

    terminal.on_key(event)

    parent_on_key.assert_called_once_with(event)


def test_forwarded_key_observer_does_not_change_terminal_passthrough(
    sleeping_harness: AgentHarness,
    monkeypatch,
) -> None:
    terminal = AgentTerminal(sleeping_harness)
    parent_on_key = Mock()
    observer = Mock()
    monkeypatch.setattr(TtyTerminal, "on_key", parent_on_key)
    terminal.set_forwarded_key_observer(observer)
    event = events.Key("escape", None)

    terminal.on_key(event)

    parent_on_key.assert_called_once_with(event)
    observer.assert_called_once_with("escape")


def test_copy_shortcut_is_not_reported_as_forwarded_interrupt(
    sleeping_harness: AgentHarness,
    monkeypatch,
) -> None:
    terminal = AgentTerminal(sleeping_harness)
    screen = Mock()
    screen.get_selected_text.return_value = "selected text"
    observer = Mock()
    monkeypatch.setattr(AgentTerminal, "screen", property(lambda _self: screen))
    terminal.set_forwarded_key_observer(observer)

    terminal.on_key(events.Key("ctrl+c", None))

    observer.assert_not_called()


def test_forwarded_key_observer_failure_does_not_break_passthrough(
    sleeping_harness: AgentHarness,
    monkeypatch,
) -> None:
    terminal = AgentTerminal(sleeping_harness)
    parent_on_key = Mock()
    observer = Mock(side_effect=RuntimeError("observer failed"))
    monkeypatch.setattr(TtyTerminal, "on_key", parent_on_key)
    terminal.set_forwarded_key_observer(observer)
    event = events.Key("escape", None)

    terminal.on_key(event)

    parent_on_key.assert_called_once_with(event)
    observer.assert_called_once_with("escape")


def test_super_c_still_copies_when_text_is_selected(
    sleeping_harness: AgentHarness,
    monkeypatch,
) -> None:
    terminal = AgentTerminal(sleeping_harness)
    screen = Mock()
    screen.get_selected_text.return_value = "selected text"
    monkeypatch.setattr(AgentTerminal, "screen", property(lambda _self: screen))
    parent_on_key = Mock()
    monkeypatch.setattr(TtyTerminal, "on_key", parent_on_key)

    terminal.on_key(events.Key("super+c", None))

    screen.action_copy_text.assert_called_once_with()
    parent_on_key.assert_not_called()


def test_super_c_without_selection_is_consumed_without_terminal_input(
    sleeping_harness: AgentHarness,
    monkeypatch,
) -> None:
    terminal = AgentTerminal(sleeping_harness)
    screen = Mock()
    screen.get_selected_text.return_value = None
    monkeypatch.setattr(AgentTerminal, "screen", property(lambda _self: screen))
    parent_on_key = Mock()
    input_key = Mock()
    monkeypatch.setattr(TtyTerminal, "on_key", parent_on_key)
    monkeypatch.setattr(terminal.board.display, "input_key", input_key)

    terminal.on_key(events.Key("super+c", None))

    screen.action_copy_text.assert_not_called()
    parent_on_key.assert_not_called()
    input_key.assert_not_called()


def test_top_anchored_partial_scroll_region_is_retained(tmp_path: Path) -> None:
    shell_harness = AgentHarness(
        id="test-shell",
        display_name="Test Shell",
        command=("fish",),
        scroll=None,
    )
    terminal = AgentTerminal(shell_harness, working_directory=tmp_path)
    terminal.board.resize(20, 6)
    terminal.feed("oldest")
    video = terminal._scrollback_video
    assert video is not None

    video.scroll_region_up(0, 3, 1)

    assert terminal.scrollback_line_count == 1
    assert "".join(cell[1] for cell in video.history_row(0)).startswith("oldest")


def test_repeated_partial_scroll_regions_accumulate(tmp_path: Path) -> None:
    """Codex-style many small top-anchored scrolls must accumulate, not just once."""

    shell_harness = AgentHarness(
        id="test-shell",
        display_name="Test Shell",
        command=("fish",),
        scroll=None,
    )
    terminal = AgentTerminal(shell_harness, working_directory=tmp_path)
    terminal.board.resize(20, 6)
    video = terminal._scrollback_video
    assert video is not None

    # Repeatedly scroll a top-anchored partial region (rows 0-4), as Codex does
    # when it keeps the composer fixed and scrolls only the transcript. Each
    # scroll must retain the top row; the count must grow rather than stall.
    for _ in range(5):
        video.scroll_region_up(0, 4, 1)

    assert terminal.scrollback_line_count == 5


def test_page_keys_scroll_native_history_for_plain_shell(tmp_path: Path) -> None:
    shell_harness = AgentHarness(
        id="test-shell",
        display_name="Test Shell",
        command=("fish",),
        scroll=None,
    )
    terminal = AgentTerminal(shell_harness, working_directory=tmp_path)
    terminal.board.resize(20, 4)
    terminal.feed("one\r\ntwo\r\nthree\r\nfour\r\nfive\r\nsix\r\n")

    terminal.on_key(events.Key("pageup", None))

    assert terminal.scrollback_offset > 0

    terminal.on_key(events.Key("pagedown", None))

    assert terminal.scrollback_offset == 0


def test_wheel_scrolls_native_history_for_plain_shell(tmp_path: Path) -> None:
    shell_harness = AgentHarness(
        id="test-shell",
        display_name="Test Shell",
        command=("fish",),
        scroll=None,
    )
    terminal = AgentTerminal(shell_harness, working_directory=tmp_path)
    terminal.board.resize(20, 4)
    terminal.feed("one\r\ntwo\r\nthree\r\nfour\r\nfive\r\nsix\r\n")
    event = Mock()

    assert terminal.scrollback_line_count > 0
    assert terminal.scrollback_offset == 0

    terminal._wheel(event, constants.MOUSE_BUTTON_WHEEL_UP, "up")

    assert terminal.scrollback_offset > 0
    event.stop.assert_called_once_with()

    terminal._wheel(Mock(), constants.MOUSE_BUTTON_WHEEL_DOWN, "down")

    assert terminal.scrollback_offset == 0


async def test_mount_revalidates_the_recorded_working_directory(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    working_directory = tmp_path / "project"
    working_directory.mkdir()
    terminal = AgentTerminal(sleeping_harness, working_directory=working_directory)
    working_directory.rmdir()

    with pytest.raises(FileNotFoundError):
        await terminal.on_mount(events.Mount())


def test_terminal_rejects_a_non_directory(
    sleeping_harness: AgentHarness,
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "not-a-directory"
    file_path.touch()

    with pytest.raises(NotADirectoryError):
        AgentTerminal(sleeping_harness, working_directory=file_path)


def test_launch_command_uses_python_module_without_a_shell(tmp_path: Path) -> None:
    command = build_launch_command(tmp_path, ("agent", "--flag", "value with spaces"))

    assert command[1:4] == ("-m", "agenthub._terminal_launcher", str(tmp_path))
    assert command[4:] == ("agent", "--flag", "value with spaces")


def test_terminal_launcher_applies_child_only_environment_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    environment_file = tmp_path / "environment.json"
    environment_file.write_text('{"AGENTHUB_SESSION_ID":"logical-session"}')
    executed: dict[str, object] = {}

    def fake_execvpe(program, command, environment) -> None:
        executed.update(program=program, command=command, environment=environment)
        raise SystemExit(0)

    monkeypatch.setattr("agenthub._terminal_launcher.os.chdir", lambda _path: None)
    monkeypatch.setattr("agenthub._terminal_launcher.os.execvpe", fake_execvpe)
    monkeypatch.delenv("AGENTHUB_SESSION_ID", raising=False)

    with pytest.raises(SystemExit, match="0"):
        launch(
            (
                "--environment-file",
                str(environment_file),
                str(tmp_path),
                "agent",
                "--flag",
            )
        )

    assert executed["program"] == "agent"
    assert executed["command"] == ["agent", "--flag"]
    assert executed["environment"]["AGENTHUB_SESSION_ID"] == "logical-session"
    assert "AGENTHUB_SESSION_ID" not in os.environ
    assert not environment_file.exists()


def test_live_terminal_rows_replace_unstyled_padding_before_textual_filters(
    sleeping_harness: AgentHarness,
    monkeypatch,
) -> None:
    terminal = AgentTerminal(sleeping_harness)
    unstyled_padding = Strip([Segment("output", RichStyle()), Segment("   ")], 9)
    monkeypatch.setattr(TtyTerminal, "render_line", lambda _terminal, _y: unstyled_padding)

    rendered = terminal.render_line(0)

    assert rendered.text == "output   "
    assert rendered.cell_length == 9
    assert all(segment.style is not None for segment in rendered)
