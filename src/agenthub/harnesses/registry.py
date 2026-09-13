"""Registry of built-in coding-agent harnesses."""

from .model import AgentHarness
from .opencode import OPENCODE

HARNESSES: dict[str, AgentHarness] = {
    OPENCODE.id: OPENCODE,
}

DEFAULT_HARNESS = OPENCODE.id
