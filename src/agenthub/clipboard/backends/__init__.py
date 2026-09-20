"""Platform-specific system clipboard backends."""

from .factory import create_clipboard_backend
from .linux import LinuxClipboardBackend
from .macos import MacOSClipboardBackend

__all__ = [
    "LinuxClipboardBackend",
    "MacOSClipboardBackend",
    "create_clipboard_backend",
]
