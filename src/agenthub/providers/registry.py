"""Registry of built-in coding-agent harnesses and native-session adapters."""

from agenthub.harnesses import AgentHarness
from agenthub.native_sessions import NativeSessionAdapter

from .antigravity import ANTIGRAVITY
from .antigravity.session_adapter import AntigravitySessionAdapter
from .codex import CODEX
from .codex.session_adapter import CodexSessionAdapter
from .devin import DEVIN
from .devin.session_adapter import DevinSessionAdapter
from .opencode import OPENCODE
from .opencode.session_adapter import OpenCodeSessionAdapter

HARNESSES: dict[str, AgentHarness] = {
    OPENCODE.id: OPENCODE,
    CODEX.id: CODEX,
    ANTIGRAVITY.id: ANTIGRAVITY,
    DEVIN.id: DEVIN,
}

DEFAULT_HARNESS = OPENCODE.id

NATIVE_SESSION_ADAPTERS: dict[str, NativeSessionAdapter] = {
    adapter.harness_id: adapter
    for adapter in (
        AntigravitySessionAdapter(),
        CodexSessionAdapter(),
        DevinSessionAdapter(),
        OpenCodeSessionAdapter(),
    )
}
