"""Generic harness models and built-in shell definitions."""

from .fish import FISH
from .model import AgentHarness, KeyStroke, ScrollKeys

__all__ = ["FISH", "AgentHarness", "KeyStroke", "ScrollKeys"]
