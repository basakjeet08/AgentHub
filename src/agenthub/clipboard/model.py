"""Platform-neutral clipboard values."""

from dataclasses import dataclass
from enum import StrEnum


class ClipboardKind(StrEnum):
    """Semantic category of inspected clipboard content."""

    TEXT = "text"
    EMPTY = "empty"
    NON_TEXT = "non_text"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ClipboardContent:
    """Inspected system clipboard payload with its semantic kind."""

    kind: ClipboardKind
    text: str | None = None
