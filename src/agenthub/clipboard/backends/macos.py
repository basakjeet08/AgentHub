"""macOS system clipboard backend."""

from __future__ import annotations

import asyncio
import contextlib
import shutil

from ..model import ClipboardContent, ClipboardKind

_READ_TIMEOUT_SECONDS = 2.0


class MacOSClipboardBackend:
    """Read macOS clipboard content through ``pbpaste``."""

    async def read(self) -> ClipboardContent:
        """Read and classify the current macOS clipboard content."""

        if shutil.which("pbpaste") is None:
            return ClipboardContent(ClipboardKind.UNAVAILABLE)

        result = await _run_command(("pbpaste",))
        if result is None:
            return ClipboardContent(ClipboardKind.UNAVAILABLE)

        code, stdout, _stderr = result
        if code != 0:
            return ClipboardContent(ClipboardKind.UNAVAILABLE)

        if not stdout:
            return ClipboardContent(ClipboardKind.EMPTY)

        try:
            return ClipboardContent(ClipboardKind.TEXT, text=stdout.decode("utf-8"))
        except UnicodeDecodeError:
            return ClipboardContent(ClipboardKind.NON_TEXT)


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    """Kill and reap an interrupted clipboard reader."""

    with contextlib.suppress(ProcessLookupError):
        process.kill()

    with contextlib.suppress(OSError):
        await process.wait()


async def _run_command(command: tuple[str, ...]) -> tuple[int, bytes, bytes] | None:
    """Run one clipboard command with bounded, cancellation-safe cleanup."""

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (OSError, ValueError):
        return None

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=_READ_TIMEOUT_SECONDS,
        )
    except asyncio.CancelledError:
        await asyncio.shield(_terminate_process(process))
        raise
    except (TimeoutError, OSError):
        await _terminate_process(process)
        return None

    return process.returncode, stdout, stderr
