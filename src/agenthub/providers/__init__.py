"""Built-in coding-agent harness definitions and registry."""

from .antigravity import ANTIGRAVITY
from .codex import CODEX
from .devin import DEVIN
from .opencode import OPENCODE
from .registry import DEFAULT_HARNESS, HARNESSES

__all__ = [
    "ANTIGRAVITY",
    "CODEX",
    "DEFAULT_HARNESS",
    "DEVIN",
    "HARNESSES",
    "OPENCODE",
]
