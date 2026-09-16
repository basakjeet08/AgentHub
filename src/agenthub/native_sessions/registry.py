"""Built-in native-session adapter registry."""

from .adapter import NativeSessionAdapter
from .antigravity import AntigravitySessionAdapter
from .codex import CodexSessionAdapter
from .devin import DevinSessionAdapter
from .opencode import OpenCodeSessionAdapter

NATIVE_SESSION_ADAPTERS: dict[str, NativeSessionAdapter] = {
    adapter.harness_id: adapter
    for adapter in (
        AntigravitySessionAdapter(),
        CodexSessionAdapter(),
        DevinSessionAdapter(),
        OpenCodeSessionAdapter(),
    )
}
