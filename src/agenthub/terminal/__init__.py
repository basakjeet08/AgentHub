"""Terminal package: the AgentTerminal widget plus harness selection."""

from .harness import DEFAULT_HARNESS, HARNESSES, AgentHarness, OpencodeHarness
from .widget import AgentTerminal, ScrollKeys

__all__ = [
    # Widget
    "AgentTerminal",
    # Harness abstraction + registry
    "AgentHarness",
    "OpencodeHarness",
    "HARNESSES",
    "DEFAULT_HARNESS",
    # Value objects
    "ScrollKeys",
]
