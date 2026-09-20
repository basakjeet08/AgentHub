"""Platform-neutral clipboard behavior."""

from __future__ import annotations

from .backend import ClipboardBackend
from .backends import create_clipboard_backend
from .model import ClipboardContent, ClipboardKind


class ClipboardService:
    """Expose clipboard reads without leaking platform implementations."""

    def __init__(self, backend: ClipboardBackend | None = None) -> None:
        self._backend = create_clipboard_backend() if backend is None else backend

    async def read(self) -> ClipboardContent:
        """Read and classify the current system clipboard content."""

        if self._backend is None:
            return ClipboardContent(ClipboardKind.UNAVAILABLE)

        return await self._backend.read()

    async def read_text(self) -> str | None:
        """Return clipboard text, an empty string, or no usable text."""

        content = await self.read()

        if content.kind is ClipboardKind.TEXT:
            return content.text

        if content.kind is ClipboardKind.EMPTY:
            return ""

        return None
