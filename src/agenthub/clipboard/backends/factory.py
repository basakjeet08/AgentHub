"""System clipboard backend selection."""

from __future__ import annotations

import sys

from ..backend import ClipboardBackend
from .linux import LinuxClipboardBackend
from .macos import MacOSClipboardBackend


def create_clipboard_backend() -> ClipboardBackend | None:
    """Return the clipboard backend for the current platform."""

    if sys.platform.startswith("linux"):
        return LinuxClipboardBackend()

    if sys.platform == "darwin":
        return MacOSClipboardBackend()

    return None
