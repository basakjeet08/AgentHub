"""Registry of built-in coding-agent harnesses."""

from agenthub.harnesses import AgentHarness

from .antigravity import ANTIGRAVITY
from .codex import CODEX
from .devin import DEVIN
from .opencode import OPENCODE

HARNESSES: dict[str, AgentHarness] = {
    OPENCODE.id: OPENCODE,
    CODEX.id: CODEX,
    ANTIGRAVITY.id: ANTIGRAVITY,
    DEVIN.id: DEVIN,
}

DEFAULT_HARNESS = OPENCODE.id
