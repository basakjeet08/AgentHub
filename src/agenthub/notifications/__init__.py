"""Provider-neutral desktop activity notifications."""

from .backend import DesktopNotificationBackend
from .model import DesktopNotification
from .service import DesktopNotificationService

__all__ = [
    "DesktopNotification",
    "DesktopNotificationBackend",
    "DesktopNotificationService",
]
