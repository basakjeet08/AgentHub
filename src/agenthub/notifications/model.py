"""Provider-neutral desktop notification values."""

from dataclasses import dataclass


@dataclass(frozen=True)
class DesktopNotification:
    """One system notification to deliver outside the TUI."""

    title: str
    message: str
