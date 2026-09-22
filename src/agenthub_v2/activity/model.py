"""Provider-neutral activity state."""

from enum import StrEnum, auto


class Activity(StrEnum):
    """Current activity status of the session."""

    UNKNOWN = auto()
    IDLE = auto()
    WORKING = auto()
    NEEDS_INPUT = auto()
    DONE = auto()
