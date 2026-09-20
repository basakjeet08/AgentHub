"""Platform-neutral system clipboard API."""

from .backend import ClipboardBackend
from .model import ClipboardContent, ClipboardKind
from .service import ClipboardService

__all__ = [
    "ClipboardBackend",
    "ClipboardContent",
    "ClipboardKind",
    "ClipboardService",
]
