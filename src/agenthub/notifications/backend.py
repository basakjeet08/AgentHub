"""Desktop notification backend abstraction."""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Protocol

from .model import DesktopNotification


class DesktopNotificationBackend(Protocol):
    """Deliver desktop attention without participating in session state."""

    def send(self, notification: DesktopNotification) -> Awaitable[None]:
        """Deliver one notification and its sound."""
