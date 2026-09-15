"""Registry of built-in coding-agent harnesses."""

from .codex import CODEX
from .model import AgentHarness
from .opencode import OPENCODE

HARNESSES: dict[str, AgentHarness] = {
    OPENCODE.id: OPENCODE,
    CODEX.id: CODEX,
}

DEFAULT_HARNESS = OPENCODE.id
