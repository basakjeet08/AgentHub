"""Provider-neutral desktop activity notifications."""

from .backend import (
    DesktopNotificationBackend,
    LinuxDesktopNotificationBackend,
    NullDesktopNotificationBackend,
    create_desktop_notification_backend,
)
from .model import DesktopNotification
from .policy import notification_for_activity_transition

__all__ = [
    "DesktopNotification",
    "DesktopNotificationBackend",
    "LinuxDesktopNotificationBackend",
    "NullDesktopNotificationBackend",
    "create_desktop_notification_backend",
    "notification_for_activity_transition",
]
