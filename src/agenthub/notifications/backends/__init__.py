"""Platform-specific desktop notification backends."""

from .factory import create_desktop_notification_backend
from .linux import LinuxDesktopNotificationBackend

__all__ = [
    "LinuxDesktopNotificationBackend",
    "create_desktop_notification_backend",
]
