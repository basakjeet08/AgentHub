"""Unit tests for the AgentTerminal-to-Bitty translation boundary."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from bittty import constants
from textual import events

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


async def test_mount_revalidates_the_recorded_working_directory(
    sleeping_harness: AgentHarness,
    monkeypatch,
    tmp_path: Path,
) -> None:
    terminal = AgentTerminal(sleeping_harness)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(NotImplementedError, match="different working directory"):
        await terminal.on_mount(events.Mount())
