"""System clipboard backend abstraction."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Protocol

from .model import ClipboardContent


class ClipboardBackend(Protocol):
    """Read and classify content from one platform clipboard."""

    def read(self) -> Awaitable[ClipboardContent]:
        """Return the currently available clipboard content."""
