"""Unit tests for the AgentTerminal-to-Bitty translation boundary."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from bittty import constants
from textual import events

from agenthub._terminal_launcher import build_launch_command
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
