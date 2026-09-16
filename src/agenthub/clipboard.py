"""System-clipboard boundary: inspect and read desktop clipboard content."""

import asyncio
import contextlib
import os
import shutil
import sys
from dataclasses import dataclass
from enum import StrEnum

_READ_TIMEOUT_SECONDS = 2.0


class ClipboardKind(StrEnum):
    """Semantic category of inspected clipboard content."""

    TEXT = "text"
    EMPTY = "empty"
    NON_TEXT = "non_text"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ClipboardContent:
    """Inspected OS clipboard payload with its semantic kind."""

    kind: ClipboardKind
    text: str | None = None


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


def resolve_clipboard_targets_command(
    command: tuple[str, ...] | None = None,
) -> tuple[str, ...] | None:
    """Return native command for querying offered clipboard MIME types or targets."""

    active_command = command or resolve_clipboard_command()
    if active_command is None:
        return None

    if active_command[0] == "wl-paste":
        return ("wl-paste", "--list-types")
    if active_command[0] == "xclip":
        return ("xclip", "-selection", "clipboard", "-t", "TARGETS", "-o")
    return None


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    """Terminate and reap an interrupted clipboard reader."""

    with contextlib.suppress(ProcessLookupError):
        process.kill()
    with contextlib.suppress(OSError):
        await process.wait()


async def _run_command(command: tuple[str, ...]) -> tuple[int, bytes, bytes] | None:
    """Run a clipboard subprocess with timeout and error handling."""

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

    return (process.returncode, stdout, stderr)


def _is_image_or_non_text_targets(targets: list[str]) -> bool:
    """Classify offered MIME types / ICCCM targets into non-text/image content."""

    normalized = [t.strip().lower() for t in targets if t.strip()]
    if not normalized:
        return False

    has_image = any(
        t.startswith("image/")
        or t in {"png", "jpeg", "image", "image/png", "image/jpeg", "image/bmp", "image/webp"}
        for t in normalized
    )
    has_plain_text = any(
        t == "text/plain"
        or t.startswith("text/plain;")
        or t in {"utf8_string", "string", "text"}
        for t in normalized
    )
    has_any_text = any(
        t.startswith("text/")
        or t in {"utf8_string", "string", "text", "compound_text"}
        for t in normalized
    )

    if has_image and not has_plain_text:
        return True
    if not has_any_text:
        return True
    return False


async def read_clipboard() -> ClipboardContent:
    """Inspect desktop clipboard content without blocking the event loop."""

    read_command = resolve_clipboard_command()
    if read_command is None:
        return ClipboardContent(ClipboardKind.UNAVAILABLE)

    targets_command = resolve_clipboard_targets_command(read_command)
    if targets_command is not None:
        targets_result = await _run_command(targets_command)
        if targets_result is None:
            return ClipboardContent(ClipboardKind.UNAVAILABLE)

        code, stdout, stderr = targets_result
        if code != 0:
            if b"Nothing is copied" in stderr:
                return ClipboardContent(ClipboardKind.EMPTY)
            return ClipboardContent(ClipboardKind.UNAVAILABLE)

        target_lines = stdout.decode("utf-8", errors="ignore").splitlines()
        if not target_lines or not any(line.strip() for line in target_lines):
            return ClipboardContent(ClipboardKind.EMPTY)

        if _is_image_or_non_text_targets(target_lines):
            return ClipboardContent(ClipboardKind.NON_TEXT)

    read_result = await _run_command(read_command)
    if read_result is None:
        return ClipboardContent(ClipboardKind.UNAVAILABLE)

    code, stdout, stderr = read_result
    if code != 0:
        if b"Nothing is copied" in stderr:
            return ClipboardContent(ClipboardKind.EMPTY)
        if b"target STRING not available" in stderr or b"target UTF8_STRING not available" in stderr:
            return ClipboardContent(ClipboardKind.NON_TEXT)
        return ClipboardContent(ClipboardKind.UNAVAILABLE)

    if not stdout:
        return ClipboardContent(ClipboardKind.EMPTY)

    try:
        text = stdout.decode("utf-8")
        return ClipboardContent(ClipboardKind.TEXT, text=text)
    except UnicodeDecodeError:
        return ClipboardContent(ClipboardKind.NON_TEXT)


async def read_clipboard_text() -> str | None:
    """Read desktop clipboard text without blocking the event loop.

    Returns ``None`` when no supported backend is available, the read fails,
    or the clipboard contains non-text data, and ``""`` for an available but empty clipboard.
    """

    content = await read_clipboard()
    if content.kind == ClipboardKind.TEXT:
        return content.text
    if content.kind == ClipboardKind.EMPTY:
        return ""
    return None
