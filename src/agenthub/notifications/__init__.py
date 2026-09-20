"""Provider-neutral desktop activity notifications."""

from .backend import DesktopNotificationBackend
from .backends import create_desktop_notification_backend
from .backends.linux import LinuxDesktopNotificationBackend
from .model import DesktopNotification
from .service import DesktopNotificationService

__all__ = [
    "DesktopNotification",
    "DesktopNotificationBackend",
    "DesktopNotificationService",
    "LinuxDesktopNotificationBackend",
    "create_desktop_notification_backend",
]
