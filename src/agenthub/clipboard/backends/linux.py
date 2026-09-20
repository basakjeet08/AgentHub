"""Linux system clipboard backend."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil

from ..model import ClipboardContent, ClipboardKind

_READ_TIMEOUT_SECONDS = 2.0


class LinuxClipboardBackend:
    """Read Wayland or X11 clipboard content through native commands."""

    async def read(self) -> ClipboardContent:
        """Read and classify the current Linux desktop clipboard content."""

        read_command = _resolve_clipboard_command()
        if read_command is None:
            return ClipboardContent(ClipboardKind.UNAVAILABLE)

        targets_command = _resolve_clipboard_targets_command(read_command)
        if targets_command is not None:
            targets_result = await _run_command(targets_command)

            if targets_result is None:
                return ClipboardContent(ClipboardKind.UNAVAILABLE)

            code, stdout, stderr = targets_result
            if code != 0:
                if b"Nothing is copied" in stderr:
                    return ClipboardContent(ClipboardKind.EMPTY)

                return ClipboardContent(ClipboardKind.UNAVAILABLE)

            targets = stdout.decode("utf-8", errors="ignore").splitlines()
            if not targets or not any(target.strip() for target in targets):
                return ClipboardContent(ClipboardKind.EMPTY)

            if _is_image_or_non_text_targets(targets):
                return ClipboardContent(ClipboardKind.NON_TEXT)

        read_result = await _run_command(read_command)
        if read_result is None:
            return ClipboardContent(ClipboardKind.UNAVAILABLE)

        code, stdout, stderr = read_result
        if code != 0:
            if b"Nothing is copied" in stderr:
                return ClipboardContent(ClipboardKind.EMPTY)

            if (
                b"target STRING not available" in stderr
                or b"target UTF8_STRING not available" in stderr
            ):
                return ClipboardContent(ClipboardKind.NON_TEXT)

            return ClipboardContent(ClipboardKind.UNAVAILABLE)

        return _classify_payload(stdout)


def _resolve_clipboard_command() -> tuple[str, ...] | None:
    """Return the preferred available Linux clipboard read command."""

    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-paste"):
        return ("wl-paste", "--no-newline")

    if os.environ.get("DISPLAY"):
        if shutil.which("xclip"):
            return ("xclip", "-selection", "clipboard", "-o")

        if shutil.which("xsel"):
            return ("xsel", "--clipboard", "--output")

    return None


def _resolve_clipboard_targets_command(
    read_command: tuple[str, ...],
) -> tuple[str, ...] | None:
    """Return the MIME/target inspection command supported by the reader."""

    if read_command[0] == "wl-paste":
        return ("wl-paste", "--list-types")

    if read_command[0] == "xclip":
        return ("xclip", "-selection", "clipboard", "-t", "TARGETS", "-o")

    return None


def _is_image_or_non_text_targets(targets: list[str]) -> bool:
    """Classify offered MIME types or ICCCM targets as non-text content."""

    normalized = [target.strip().lower() for target in targets if target.strip()]
    if not normalized:
        return False

    has_image = any(
        target.startswith("image/")
        or target
        in {
            "png",
            "jpeg",
            "image",
            "image/png",
            "image/jpeg",
            "image/bmp",
            "image/webp",
        }
        for target in normalized
    )

    has_text = any(
        target.startswith("text/")
        or target in {"utf8_string", "string", "text", "compound_text"}
        for target in normalized
    )

    return has_image or not has_text


def _classify_payload(payload: bytes) -> ClipboardContent:
    """Classify one successful clipboard command payload."""

    if not payload:
        return ClipboardContent(ClipboardKind.EMPTY)
    try:
        return ClipboardContent(ClipboardKind.TEXT, text=payload.decode("utf-8"))
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
