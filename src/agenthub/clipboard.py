"""System-clipboard boundary: read desktop clipboard text."""

import asyncio
import contextlib
import os
import shutil
import sys

_READ_TIMEOUT_SECONDS = 2.0


def resolve_clipboard_command() -> tuple[str, ...] | None:
    """Return the first available native command for reading clipboard text."""

    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-paste"):
        return ("wl-paste", "--no-newline")
    if os.environ.get("DISPLAY"):
        if shutil.which("xclip"):
            return ("xclip", "-selection", "clipboard", "-o")
        if shutil.which("xsel"):
            return ("xsel", "--clipboard", "--output")
    if sys.platform == "darwin" and shutil.which("pbpaste"):
        return ("pbpaste",)
    return None


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    """Terminate and reap an interrupted clipboard reader."""

    with contextlib.suppress(ProcessLookupError):
        process.kill()
    with contextlib.suppress(OSError):
        await process.wait()


async def read_clipboard_text() -> str | None:
    """Read desktop clipboard text without blocking the event loop.

    Returns ``None`` when no supported backend is available or the read fails,
    and ``""`` for an available but empty clipboard.
    """

    command = resolve_clipboard_command()
    if command is None:
        return None

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except (OSError, ValueError):
        return None

    try:
        stdout, _ = await asyncio.wait_for(
            process.communicate(),
            timeout=_READ_TIMEOUT_SECONDS,
        )
    except asyncio.CancelledError:
        await asyncio.shield(_terminate_process(process))
        raise
    except (TimeoutError, OSError):
        await _terminate_process(process)
        return None

    if process.returncode != 0:
        return None

    try:
        return stdout.decode("utf-8")
    except UnicodeDecodeError:
        return None
