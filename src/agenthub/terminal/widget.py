"""Terminal widget adapter: the textual-tty and Bitty integration boundary."""

import asyncio
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from bittty import constants as _bittty_constants
from bittty.video import Cell
from rich.segment import Segment
from rich.style import Style as RichStyle
from textual import events
from textual.strip import Strip
from textual_tty import Terminal as TtyTerminal

from agenthub._terminal_launcher import build_launch_command
from agenthub.harnesses import AgentHarness, KeyStroke
from agenthub.terminal.scrollback import ScrollbackVideo

_SCROLLBACK_LINES = 10_000
_WHEEL_SCROLL_LINES = 3

_BITTTY_MODIFIERS = {
    (False, False, False): _bittty_constants.KEY_MOD_NONE,
    (True, False, False): _bittty_constants.KEY_MOD_SHIFT,
    (False, True, False): _bittty_constants.KEY_MOD_ALT,
    (True, True, False): _bittty_constants.KEY_MOD_SHIFT_ALT,
    (False, False, True): _bittty_constants.KEY_MOD_CTRL,
    (True, False, True): _bittty_constants.KEY_MOD_SHIFT_CTRL,
    (False, True, True): _bittty_constants.KEY_MOD_ALT_CTRL,
    (True, True, True): _bittty_constants.KEY_MOD_SHIFT_ALT_CTRL,
}


def _bittty_modifier(key_stroke: KeyStroke) -> int:
    """Translate a semantic key description into Bitty's modifier encoding."""

    return _BITTTY_MODIFIERS[(key_stroke.shift, key_stroke.alt, key_stroke.ctrl)]


class AgentTerminal(TtyTerminal):
    """textual-tty (bittty) terminal hosting the coding agent."""

    class ProcessExited(TtyTerminal.ProcessExited):
        """Process-exit message associated with its terminal adapter."""

        @property
        def control(self) -> "AgentTerminal":
            """Return the terminal that emitted this message."""

            return cast("AgentTerminal", self._sender)

    def __init__(
        self,
        harness: AgentHarness,
        *,
        working_directory: Path | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Build a live terminal adapter from semantic harness configuration."""

        launch_directory = (working_directory or Path.cwd()).expanduser().resolve()
        self._validate_working_directory(launch_directory)

        self.harness = harness
        self.working_directory = launch_directory
        self._scrollback_offset = 0
        self._scrollback_video: ScrollbackVideo | None = None
        super().__init__(
            command=list(build_launch_command(launch_directory, harness.command)),
            name=name,
            id=id,
            classes=classes,
        )
        if harness.scroll is None:
            blitter = self.board.blitter
            scrollback_video = ScrollbackVideo(
                self.board.width,
                self.board.height,
                self.board.width_policy,
                history_limit=_SCROLLBACK_LINES,
                on_history_added=self._on_history_added,
            )
            blitter.primary_buffer = scrollback_video
            blitter.current_buffer = scrollback_video
            self._scrollback_video = scrollback_video

    @staticmethod
    def _validate_working_directory(working_directory: Path) -> None:
        """Require an existing directory before constructing or mounting."""

        if not working_directory.exists():
            raise FileNotFoundError(working_directory)
        if not working_directory.is_dir():
            raise NotADirectoryError(working_directory)

    @property
    def is_process_running(self) -> bool:
        """Report child liveness without exposing terminal-library internals."""

        return self._process is not None and self._process.poll() is None

    @property
    def scrollback_line_count(self) -> int:
        """Return the number of primary-screen rows retained in memory."""

        video = self._scrollback_video
        return 0 if video is None else video.history_line_count

    @property
    def scrollback_offset(self) -> int:
        """Return how many rows above the live primary viewport are displayed."""

        return self._scrollback_offset

    async def on_mount(self, event: events.Mount) -> None:
        """Start the child only if it will inherit the recorded directory."""

        # Textual dispatches named handlers across the class MRO. Suppress that
        # automatic parent call because this adapter invokes it explicitly.
        event.prevent_default()
        self._validate_working_directory(self.working_directory)
        await super().on_mount()

    async def on_unmount(self, event: events.Unmount) -> None:
        """Stop the terminal and await Bitty's asynchronous cleanup."""

        # Own the complete parent cleanup sequence so its cancelled reader task
        # and child process can be awaited before Textual finishes unmounting.
        event.prevent_default()
        reader_task = self.board.host._reader_task
        process = self._process
        super().on_unmount()

        if reader_task is not None:
            await reader_task

        if process is not None:
            await self._wait_for_process_exit(process)

    @staticmethod
    async def _wait_for_process_exit(process: subprocess.Popen) -> None:
        """Reap a child after Bitty closes its PTY, escalating if necessary."""

        if await AgentTerminal._poll_for_process_exit(process):
            return

        process.terminate()
        if await AgentTerminal._poll_for_process_exit(process):
            return

        process.kill()
        await AgentTerminal._poll_for_process_exit(process)

    @staticmethod
    async def _poll_for_process_exit(
        process: subprocess.Popen,
        wait_seconds: float = 1.0,
    ) -> bool:
        """Poll without blocking Textual's event loop until a child exits."""

        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_seconds
        while process.poll() is None:
            if loop.time() >= deadline:
                return False
            await asyncio.sleep(0.01)

        return True

    def on_key(self, event: events.Key) -> None:
        """Use page keys for retained primary-screen history when available."""

        if (
            self.harness.scroll is None
            and not self.board.blitter.in_alt_screen
            and event.key in {"pageup", "pagedown"}
        ):
            arrow = "up" if event.key == "pageup" else "down"
            self._scroll_normal_history(arrow, max(self.board.height - 1, 1))
            event.stop()
            event.prevent_default()
            return

        event.prevent_default()
        super().on_key(event)

    def _wheel(self, event: events.MouseEvent, button: int, arrow: str) -> None:
        """Scroll the transcript when the child ignores the wheel; defer otherwise."""

        # When the child tracks the mouse it owns the wheel — defer to base.
        # Otherwise send the harness's transcript-scroll keys. Plain method
        # override (not a message handler), so super() here is a single call.
        scroll = self.harness.scroll
        if self.mouse_mode != "off":
            super()._wheel(event, button, arrow)
            return

        if scroll is None:
            if self.board.blitter.in_alt_screen:
                super()._wheel(event, button, arrow)
                return
            self._scroll_normal_history(arrow)
            event.stop()
            return

        key_stroke = scroll.down if arrow == "down" else scroll.up

        for _ in range(scroll.steps):
            self.board.display.input_key(
                key_stroke.key,
                _bittty_modifier(key_stroke),
            )

        event.stop()

    def _on_history_added(self, count: int) -> None:
        """Keep a scrolled-back viewport stable while new output arrives."""

        if self._scrollback_offset:
            self._scrollback_offset = min(
                self._scrollback_offset + count,
                self.scrollback_line_count,
            )
            self.refresh()

    def _scroll_normal_history(
        self,
        arrow: str,
        lines: int = _WHEEL_SCROLL_LINES,
    ) -> None:
        """Move through primary-screen history without sending keys to the child."""

        if arrow == "up":
            next_offset = min(
                self._scrollback_offset + lines,
                self.scrollback_line_count,
            )
        else:
            next_offset = max(self._scrollback_offset - lines, 0)

        if next_offset != self._scrollback_offset:
            self._scrollback_offset = next_offset
            self.refresh()

    def render_line(self, y: int) -> Strip:
        """Render retained rows when viewing above the live primary page."""

        video = self._scrollback_video
        if video is None or self._scrollback_offset == 0 or self.board.blitter.in_alt_screen:
            return super().render_line(y)

        history_lines = video.history_line_count
        viewport_start = history_lines - self._scrollback_offset
        row_index = viewport_start + y
        if row_index < history_lines:
            row = video.history_row(row_index)
        else:
            live_row = row_index - history_lines
            if live_row >= video.height:
                return Strip.blank(self.size.width, RichStyle())
            row = video.grid[live_row]

        return self._render_scrollback_row(row)

    def _render_scrollback_row(self, row: Sequence[Cell]) -> Strip:
        """Convert one retained Bitty row to a Textual strip with original styles."""

        width = self.size.width
        segments: list[Segment] = []
        run: list[str] = []
        run_style = None
        for style, character in row[:width]:
            if style is not run_style and style != run_style:
                if run:
                    segments.append(Segment("".join(run), self._to_rich(run_style)))
                    run = []
                run_style = style
            run.append(character)
        if run:
            segments.append(Segment("".join(run), self._to_rich(run_style)))
        padding_style = self._to_rich(row[-1][0]) if row else RichStyle()
        return Strip(segments).adjust_cell_length(width, padding_style)
