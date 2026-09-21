"""Registry of built-in harness, session, and activity adapters."""

from agenthub.activity.adapter import ActivityAdapter
from agenthub.harnesses import AgentHarness
from agenthub.native_sessions import NativeSessionAdapter

from .antigravity import ANTIGRAVITY
from .antigravity.activity_adapter import ANTIGRAVITY_ACTIVITY_ADAPTER
from .antigravity.session_adapter import AntigravitySessionAdapter
from .codex import CODEX
from .codex.activity_adapter import CODEX_ACTIVITY_ADAPTER
from .codex.session_adapter import CodexSessionAdapter
from .devin import DEVIN
from .devin.activity_adapter import DEVIN_ACTIVITY_ADAPTER
from .devin.session_adapter import DevinSessionAdapter
from .opencode import OPENCODE
from .opencode.activity_adapter import OPENCODE_ACTIVITY_ADAPTER
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

ACTIVITY_ADAPTERS: dict[str, ActivityAdapter] = {
    adapter.harness_id: adapter
    for adapter in (
        OPENCODE_ACTIVITY_ADAPTER,
        CODEX_ACTIVITY_ADAPTER,
        ANTIGRAVITY_ACTIVITY_ADAPTER,
        DEVIN_ACTIVITY_ADAPTER,
    )
}
