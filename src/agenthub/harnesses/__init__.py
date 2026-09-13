"""Supported coding-agent harness models and built-in definitions."""

from .model import AgentHarness, KeyStroke, ScrollKeys
from .opencode import OPENCODE
from .registry import DEFAULT_HARNESS, HARNESSES

__all__ = [
    "DEFAULT_HARNESS",
    "HARNESSES",
    "OPENCODE",
    "AgentHarness",
    "KeyStroke",
    "ScrollKeys",
]
