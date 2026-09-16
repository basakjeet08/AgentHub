"""Terminal widget adapter: the textual-tty and Bitty integration boundary."""

import asyncio
import subprocess
from collections.abc import Sequence
from pathlib import Path
from time import monotonic
from typing import cast

from bittty import constants as _bittty_constants
from bittty.video import Cell
from rich.cells import cell_len
from rich.segment import Segment
from rich.style import Style as RichStyle
from textual import events
from textual.geometry import Offset
from textual.selection import Selection
from textual.strip import Strip
from textual_tty import Terminal as TtyTerminal

from agenthub._terminal_launcher import build_launch_command
from agenthub.clipboard import read_clipboard_text
from agenthub.harnesses import AgentHarness, KeyStroke
from agenthub.terminal.scrollback import ScrollbackVideo

_SCROLLBACK_LINES = 10_000
_WHEEL_SCROLL_LINES = 3
_WORD_ERASE = "\x17"  # Ctrl+W, the conventional terminal erase-word character.
_PASTE_REPEAT_GAP_SECONDS = 1.0
_UNSUPPORTED_TERMINAL_MODIFIERS = frozenset({"super", "hyper"})

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


class _BufferedPasteConnection:
    """Buffer one logical paste while draining every byte to a non-blocking PTY."""

    def __init__(self, connection) -> None:
        self._connection = connection
        self._buffer = bytearray()

    def __getattr__(self, name: str):
        return getattr(self._connection, name)

    def write(self, data: str) -> int:
        encoded = data.encode("utf-8")
        self._buffer.extend(encoded)
        return len(encoded)

    def write_bytes(self, data: bytes) -> int:
        self._buffer.extend(data)
        return len(data)

    async def drain(self) -> None:
        writer = self._connection.write_bytes
        while self._buffer:
            try:
                written = writer(bytes(self._buffer))
            except BlockingIOError:
                written = 0
            if written:
                del self._buffer[:written]
                continue
            await self._wait_until_writable()

    async def _wait_until_writable(self) -> None:
        file_descriptor = getattr(self._connection, "master_fd", None)
        if not isinstance(file_descriptor, int):
            await asyncio.sleep(0.01)
            return

        loop = asyncio.get_running_loop()
        writable = loop.create_future()

        def mark_writable() -> None:
            if not writable.done():
                writable.set_result(None)

        try:
            loop.add_writer(file_descriptor, mark_writable)
        except (NotImplementedError, OSError):
            await asyncio.sleep(0.01)
            return
        try:
            await writable
        finally:
            loop.remove_writer(file_descriptor)


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
        command: Sequence[str] | None = None,
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
        self._suppress_upstream_selection_style = False
        self._paste_in_progress = False
        self._last_paste_key_at = 0.0
        self._paste_lock = asyncio.Lock()
        self._selection_anchor_cell: Offset | None = None
        launch_command = harness.command if command is None else tuple(command)
        super().__init__(
            command=list(build_launch_command(launch_directory, launch_command)),
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
    def text_selection(self) -> Selection | None:
        """Hide selection only while the upstream renderer paints terminal cells."""

        if self._suppress_upstream_selection_style:
            return None
        return super().text_selection

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
            event.key in {"ctrl+c", "ctrl+shift+c", "super+c"}
            and self.screen.get_selected_text() is not None
        ):
            self.screen.action_copy_text()
            event.stop()
            event.prevent_default()
            return

        if event.key == "ctrl+v":
            now = monotonic()
            repeated = now - self._last_paste_key_at < _PASTE_REPEAT_GAP_SECONDS
            self._last_paste_key_at = now
            if not repeated and not self._paste_in_progress:
                self._paste_in_progress = True
                self.run_worker(
                    self._paste_system_clipboard(),
                    group="clipboard-paste",
                    exclusive=False,
                    exit_on_error=False,
                )
            event.stop()
            event.prevent_default()
            return

        if event.key == "ctrl+backspace":
            self.board.display.input(_WORD_ERASE)
            event.stop()
            event.prevent_default()
            return

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

        modifiers = event.key.split("+")[:-1]
        if _UNSUPPORTED_TERMINAL_MODIFIERS.intersection(modifiers):
            event.stop()
            event.prevent_default()
            return

        event.prevent_default()
        super().on_key(event)

    def on_paste(self, event: events.Paste) -> None:
        """Deliver outer-terminal paste through the reliable PTY writer."""

        event.stop()
        event.prevent_default()
        self.run_worker(
            self.paste_text(event.text),
            group="terminal-paste",
            exclusive=False,
            exit_on_error=False,
        )

    async def _paste_system_clipboard(self) -> None:
        """Read the desktop clipboard and paste it through the terminal's port."""

        try:
            text = await read_clipboard_text()
            if not self.is_mounted or not self.is_process_running:
                return

            if text is None:
                text = self.app.clipboard
                if not text:
                    self.notify(
                        "No system clipboard is available to paste from.",
                        title="Paste unavailable",
                        severity="warning",
                    )
                    return

            if text:
                await self.paste_text(text)
        finally:
            self._paste_in_progress = False

    async def paste_text(self, text: str) -> None:
        """Deliver every byte through one native terminal paste operation."""

        async with self._paste_lock:
            host = self.board.host
            connection = host.connection
            if connection is None:
                return

            buffered_connection = _BufferedPasteConnection(connection)
            host.connection = buffered_connection
            try:
                self.board.display.input_paste(text)
                await buffered_connection.drain()
            finally:
                if host.connection is buffered_connection:
                    host.connection = connection

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Record a terminal-cell selection anchor before Textual loses cell width."""

        event.prevent_default()
        super().on_mouse_down(event)
        if event.button == 1 and self.allow_select:
            self._selection_anchor_cell = event.get_content_offset(self)
            if self._selection_anchor_cell is not None:
                self.capture_mouse()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Keep drag selection aligned with wide terminal cells."""

        event.prevent_default()
        super().on_mouse_move(event)
        self._update_cell_selection(event)

    def on_mouse_up(self, event: events.MouseUp) -> None:
        """Complete terminal-cell selection at the released cell."""

        event.prevent_default()
        super().on_mouse_up(event)
        self._update_cell_selection(event)
        if self._selection_anchor_cell is not None:
            self.release_mouse()
        self._selection_anchor_cell = None

    def _update_cell_selection(self, event: events.MouseEvent) -> None:
        anchor = self._selection_anchor_cell
        offset = event.get_content_offset(self)
        if anchor is None or offset is None:
            return

        anchor_span = self._cell_text_span(anchor)
        offset_span = self._cell_text_span(offset)
        if anchor_span is None or offset_span is None:
            return

        if (anchor.y, anchor.x) <= (offset.y, offset.x):
            start = Offset(anchor_span[0], anchor.y)
            end = Offset(offset_span[1], offset.y)
        else:
            start = Offset(offset_span[0], offset.y)
            end = Offset(anchor_span[1], anchor.y)
        self.screen.selections = {self: Selection(start, end)}

    def _cell_text_span(self, offset: Offset) -> tuple[int, int] | None:
        row = self._visible_row(offset.y)
        if row is None or offset.x < 0 or offset.x >= len(row):
            return None

        start_cell = offset.x
        while start_cell > 0 and row[start_cell][1] == "":
            start_cell -= 1
        character = row[start_cell][1]
        if not character:
            return None
        start = sum(len(cell_character) for _style, cell_character in row[:start_cell])
        return start, start + len(character)

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
            self._suppress_upstream_selection_style = True
            try:
                strip = self._with_explicit_styles(super().render_line(y))
            finally:
                self._suppress_upstream_selection_style = False
            strip = self._apply_selection_style(strip, y)
            return strip.apply_offsets(0, y)

        history_lines = video.history_line_count
        viewport_start = history_lines - self._scrollback_offset
        row_index = viewport_start + y
        if row_index < history_lines:
            row = video.history_row(row_index)
        else:
            live_row = row_index - history_lines
            if live_row >= video.height:
                strip = Strip.blank(self.size.width, RichStyle())
                return strip.apply_offsets(0, y)
            row = video.grid[live_row]

        strip = self._with_explicit_styles(self._render_scrollback_row(row))
        strip = self._apply_selection_style(strip, y)
        return strip.apply_offsets(0, y)

    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        """Extract selected text from the rows currently visible to the user."""

        if not self._is_showing_scrollback:
            return super().get_selection(selection)

        text = "\n".join(
            self._visible_line_text(y).rstrip() for y in range(self.board.height)
        )
        return selection.extract(text), "\n"

    async def _on_click(self, event: events.Click) -> None:
        """Replace Textual's completed double-click select-all with a word."""

        # Textual also dispatches private handlers through the MRO. Own that
        # sequence so Widget._on_click cannot run a second time after this
        # override has narrowed its select-all result to a terminal word.
        event.prevent_default()
        await super()._on_click(event)
        super().on_click(event)

        if event.button != 1 or event.chain != 2 or not self.allow_select:
            return

        widget, offset = self.screen.get_widget_and_offset_at(
            event.screen_x,
            event.screen_y,
        )
        if widget is not self or offset is None:
            self.screen.clear_selection()
            return

        line = self._visible_line_text(offset.y).rstrip()
        if offset.x >= len(line) or line[offset.x].isspace():
            self.screen.clear_selection()
            return

        group = self._word_group(line[offset.x])
        start = offset.x
        while start > 0 and self._word_group(line[start - 1]) == group:
            start -= 1

        end = offset.x + 1
        while end < len(line) and self._word_group(line[end]) == group:
            end += 1

        self.screen.selections = {
            self: Selection(Offset(start, offset.y), Offset(end, offset.y))
        }

    @property
    def _is_showing_scrollback(self) -> bool:
        """Return whether retained primary-screen history is visible."""

        return (
            self._scrollback_video is not None
            and self._scrollback_offset > 0
            and not self.board.blitter.in_alt_screen
        )

    def _visible_row(self, y: int) -> Sequence[Cell] | None:
        """Return terminal cells displayed at viewport row ``y``."""

        video = self._scrollback_video
        if not self._is_showing_scrollback or video is None:
            page = self.board.blitter.current_buffer
            return None if y >= page.height else page.grid[y]

        history_lines = video.history_line_count
        row_index = history_lines - self._scrollback_offset + y
        if row_index < history_lines:
            return video.history_row(row_index)

        live_row = row_index - history_lines
        return None if live_row >= video.height else video.grid[live_row]

    def _visible_line_text(self, y: int) -> str:
        """Return text from the row currently displayed at viewport coordinate ``y``."""

        row = self._visible_row(y)
        return "" if row is None else "".join(character for _style, character in row)

    def _apply_selection_style(self, strip: Strip, y: int) -> Strip:
        """Apply Textual's selection highlight to a custom scrollback row."""

        if not self.is_mounted:
            return strip
        selection = self.text_selection
        if selection is None or (span := selection.get_span(y)) is None:
            return strip

        start, end = span
        line = self._visible_line_text(y)
        start = min(cell_len(line[:start]), self.size.width)
        end = self.size.width if end == -1 else min(cell_len(line[:end]), self.size.width)
        component_style = self.screen.get_component_rich_style("screen--selection")
        style = RichStyle(bgcolor=component_style.bgcolor)
        before, selected, after = strip.divide([start, end, self.size.width])
        return Strip.join([before, selected.apply_style(style), after])

    @staticmethod
    def _word_group(character: str) -> str:
        """Group word characters separately from terminal punctuation."""

        return "word" if character.isalnum() or character == "_" else "punctuation"

    @staticmethod
    def _with_explicit_styles(strip: Strip) -> Strip:
        """Make terminal rows safe for Textual filters that require a style."""

        if all(segment.style is not None for segment in strip):
            return strip
        return Strip(
            (
                Segment(
                    segment.text,
                    segment.style if segment.style is not None else RichStyle(),
                    segment.control,
                )
                for segment in strip
            ),
            strip.cell_length,
        )

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
