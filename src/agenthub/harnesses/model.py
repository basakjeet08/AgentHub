"""Terminal-independent harness configuration models."""

from dataclasses import dataclass


@dataclass(frozen=True)
class KeyStroke:
    """A terminal-independent key and modifier combination."""

    key: str
    ctrl: bool = False
    alt: bool = False
    shift: bool = False


@dataclass(frozen=True)
class ScrollKeys:
    """Transcript-scroll shortcuts and repeats for one wheel event."""

    down: KeyStroke
    up: KeyStroke
    steps: int = 3


@dataclass(frozen=True)
class AgentHarness:
    """Immutable launch and terminal-behavior configuration for a hosted CLI."""

    id: str
    display_name: str
    command: tuple[str, ...]
    scroll: ScrollKeys | None
