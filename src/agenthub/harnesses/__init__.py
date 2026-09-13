"""Supported coding-agent harness models and built-in definitions."""

from .fish import FISH
from .model import AgentHarness, KeyStroke, ScrollKeys
from .opencode import OPENCODE
from .registry import DEFAULT_HARNESS, HARNESSES

__all__ = [
    "DEFAULT_HARNESS",
    "FISH",
    "HARNESSES",
    "OPENCODE",
    "AgentHarness",
    "KeyStroke",
    "ScrollKeys",
]
