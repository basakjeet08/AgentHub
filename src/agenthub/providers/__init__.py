"""Built-in coding-agent harness definitions and registry."""

from .antigravity import ANTIGRAVITY
from .codex import CODEX
from .devin import DEVIN
from .opencode import OPENCODE
from .registry import ACTIVITY_ADAPTERS, DEFAULT_HARNESS, HARNESSES, NATIVE_SESSION_ADAPTERS

__all__ = [
    "ACTIVITY_ADAPTERS",
    "ANTIGRAVITY",
    "CODEX",
    "DEFAULT_HARNESS",
    "DEVIN",
    "HARNESSES",
    "NATIVE_SESSION_ADAPTERS",
    "OPENCODE",
]
