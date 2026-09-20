"""OpenCode activity normalization and version-compatible plugin configuration."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from .model import AgentActivityEvent, AgentActivityEventKind

OPENCODE_CONFIG_CONTENT = "OPENCODE_CONFIG_CONTENT"
AGENTHUB_OPENCODE_SESSION_ID = "AGENTHUB_OPENCODE_SESSION_ID"

_NORMALIZED_EVENTS = {
    "agenthub.plugin.ready": AgentActivityEventKind.SESSION_STARTED,
    "session.execution.started": AgentActivityEventKind.PROMPT_SUBMITTED,
    "permission.asked": AgentActivityEventKind.PERMISSION_REQUESTED,
    "permission.v2.asked": AgentActivityEventKind.PERMISSION_REQUESTED,
    "permission.replied": AgentActivityEventKind.INPUT_RESOLVED,
    "permission.v2.replied": AgentActivityEventKind.INPUT_RESOLVED,
    "form.created": AgentActivityEventKind.INPUT_REQUESTED,
    "form.replied": AgentActivityEventKind.INPUT_RESOLVED,
    "form.cancelled": AgentActivityEventKind.INPUT_RESOLVED,
    "question.asked": AgentActivityEventKind.INPUT_REQUESTED,
    "question.replied": AgentActivityEventKind.INPUT_RESOLVED,
    "question.rejected": AgentActivityEventKind.INPUT_RESOLVED,
    "question.v2.asked": AgentActivityEventKind.INPUT_REQUESTED,
    "question.v2.replied": AgentActivityEventKind.INPUT_RESOLVED,
    "question.v2.rejected": AgentActivityEventKind.INPUT_RESOLVED,
    "session.execution.succeeded": AgentActivityEventKind.TURN_COMPLETED,
    "session.execution.failed": AgentActivityEventKind.TURN_COMPLETED,
    "session.execution.interrupted": AgentActivityEventKind.INTERRUPTED,
}


def normalize_opencode_activity(
    session_id: str,
    payload: object,
) -> AgentActivityEvent | None:
    """Translate one observation from the OpenCode compatibility plugin."""

    if not isinstance(payload, dict):
        return None
    event_type = payload.get("type")
    if not isinstance(event_type, str):
        return None
    kind = _NORMALIZED_EVENTS.get(event_type)
    if kind is None:
        return None
    scope_id = payload.get("activity_scope_id")
    if kind is AgentActivityEventKind.SESSION_STARTED:
        return AgentActivityEvent(session_id=session_id, kind=kind)
    if not isinstance(scope_id, str) or not scope_id:
        return None
    return AgentActivityEvent(session_id=session_id, kind=kind, scope_id=scope_id)


def opencode_activity_environment(
    *,
    native_session_id: str | None = None,
    environment: Mapping[str, str] | None = None,
    plugin_path: Path | None = None,
) -> dict[str, str]:
    """Return child-only V1/V2 plugin configuration without changing user files."""

    env = os.environ if environment is None else environment
    configured = env.get(OPENCODE_CONFIG_CONTENT, "").strip()
    decoded = json.loads(configured) if configured else {}
    if not isinstance(decoded, dict):
        raise TypeError("OpenCode inline config must contain a JSON object")

    resolved_plugin = str(
        (plugin_path or Path(__file__).with_name("_opencode_plugin.js")).resolve()
    )
    for key in ("plugin", "plugins"):
        plugins = decoded.get(key, [])
        if not isinstance(plugins, list):
            raise TypeError(f"OpenCode {key} config must contain a JSON array")
        if resolved_plugin not in plugins:
            plugins = [*plugins, resolved_plugin]
        decoded[key] = plugins

    overrides = {
        OPENCODE_CONFIG_CONTENT: json.dumps(decoded, separators=(",", ":")),
    }
    if native_session_id:
        overrides[AGENTHUB_OPENCODE_SESSION_ID] = native_session_id
    return overrides


__all__ = [
    "AGENTHUB_OPENCODE_SESSION_ID",
    "OPENCODE_CONFIG_CONTENT",
    "normalize_opencode_activity",
    "opencode_activity_environment",
]
