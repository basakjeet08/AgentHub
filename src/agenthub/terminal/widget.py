"""Terminal widget adapter: the textual-tty and Bitty integration boundary."""

import asyncio
import subprocess
from pathlib import Path
from typing import cast

from bittty import constants as _bittty_constants
from textual import events
from textual_tty import Terminal as TtyTerminal

from agenthub.harnesses import AgentHarness, KeyStroke

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
        self._ensure_supported_working_directory(launch_directory)

        self.harness = harness
        self.working_directory = launch_directory
        super().__init__(
            command=list(harness.command),
            name=name,
            id=id,
            classes=classes,
        )

    @staticmethod
    def _ensure_supported_working_directory(working_directory: Path) -> None:
        """Reject a launch directory the current terminal stack cannot honor."""

        if working_directory != Path.cwd().resolve():
            raise NotImplementedError(
                "textual-tty does not currently support launching a process "
                "in a different working directory"
            )

    async def on_mount(self, event: events.Mount) -> None:
        """Start the child only if it will inherit the recorded directory."""

        # Textual dispatches named handlers across the class MRO. Suppress that
        # automatic parent call because this adapter invokes it explicitly.
        event.prevent_default()
        self._ensure_supported_working_directory(self.working_directory)
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

    def _wheel(self, event: events.MouseEvent, button: int, arrow: str) -> None:
        """Scroll the transcript when the child ignores the wheel; defer otherwise."""

        # When the child tracks the mouse it owns the wheel — defer to base.
        # Otherwise send the harness's transcript-scroll keys. Plain method
        # override (not a message handler), so super() here is a single call.
        if self.mouse_mode != "off":
            super()._wheel(event, button, arrow)
            return

        key_stroke = self.harness.scroll.down if arrow == "down" else self.harness.scroll.up

        for _ in range(self.harness.scroll.steps):
            self.board.display.input_key(
                key_stroke.key,
                _bittty_modifier(key_stroke),
            )

        event.stop()
