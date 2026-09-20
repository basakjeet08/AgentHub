"""Desktop notification backend selection."""

from __future__ import annotations

import sys

from ..backend import DesktopNotificationBackend
from .linux import LinuxDesktopNotificationBackend


def create_desktop_notification_backend() -> DesktopNotificationBackend | None:
    """Return the supported backend for the current desktop platform."""

    if sys.platform.startswith("linux"):
        return LinuxDesktopNotificationBackend.from_system()

    return None
