"""OpenCode activity integration."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import BinaryIO, TextIO

from agenthub.activity import AgentActivity, AgentActivityEvent, AgentActivityEventKind
from agenthub.activity.adapter import ActivityLaunch, ActivityNormalizer

OPENCODE_CONFIG_CONTENT = "OPENCODE_CONFIG_CONTENT"
AGENTHUB_OPENCODE_SESSION_ID = "AGENTHUB_OPENCODE_SESSION_ID"
_PROVIDER = "opencode"
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


def normalize_opencode_activity(session_id: str, payload: object) -> AgentActivityEvent | None:
    if not isinstance(payload, dict):
        return None
    event_type = payload.get("type")
    kind = _NORMALIZED_EVENTS.get(event_type) if isinstance(event_type, str) else None
    if kind is None:
        return None
    if kind is AgentActivityEventKind.SESSION_STARTED:
        return AgentActivityEvent(session_id, kind)
    scope_id = payload.get("activity_scope_id")
    if not isinstance(scope_id, str) or not scope_id:
        return None
    return AgentActivityEvent(session_id, kind, scope_id)


class OpenCodeActivityAdapter:
    harness_id = _PROVIDER

    def matches_command(self, command: Sequence[str]) -> bool:
        return bool(command) and Path(command[0]).name == _PROVIDER

    def create_normalizer(self, native_session_id: str | None) -> ActivityNormalizer:
        del native_session_id
        return normalize_opencode_activity

    def prepare_launch(self, command: Sequence[str], *, native_session_id: str | None,
                       registration_environment: Mapping[str, str]) -> ActivityLaunch:
        env = os.environ
        configured = env.get(OPENCODE_CONFIG_CONTENT, "").strip()
        decoded = json.loads(configured) if configured else {}
        if not isinstance(decoded, dict):
            raise TypeError("OpenCode inline config must contain a JSON object")
        plugin = str((Path(__file__).with_name("activity_plugin.js")).resolve())
        for key in ("plugin", "plugins"):
            plugins = decoded.get(key, [])
            if not isinstance(plugins, list):
                raise TypeError(f"OpenCode {key} config must contain a JSON array")
            if plugin not in plugins:
                plugins = [*plugins, plugin]
            decoded[key] = plugins
        overrides = dict(registration_environment)
        overrides[OPENCODE_CONFIG_CONTENT] = json.dumps(decoded, separators=(",", ":"))
        if native_session_id:
            overrides[AGENTHUB_OPENCODE_SESSION_ID] = native_session_id
        return ActivityLaunch(tuple(command), overrides, reports_session_started=True)

    def run_hook(self, event_name: str | None = None, *, input_stream: BinaryIO | None = None,
                 output_stream: TextIO | None = None, environment: Mapping[str, str] | None = None) -> int:
        del input_stream, output_stream, environment
        raise ValueError("OpenCode activity hooks are delivered by the plugin")

    def terminal_key_event(self, session_id: str, key: str, *, activity: AgentActivity,
                           input_wait_kind: AgentActivityEventKind | None) -> AgentActivityEvent | None:
        del session_id, key, activity, input_wait_kind
        return None


def _opencode_activity_environment(*, native_session_id: str | None = None,
                                    environment: Mapping[str, str] | None = None,
                                    plugin_path: Path | None = None) -> dict[str, str]:
    env = os.environ if environment is None else environment
    configured = env.get(OPENCODE_CONFIG_CONTENT, "").strip()
    decoded = json.loads(configured) if configured else {}
    if not isinstance(decoded, dict):
        raise TypeError("OpenCode inline config must contain a JSON object")
    plugin = str((plugin_path or Path(__file__).with_name("activity_plugin.js")).resolve())
    for key in ("plugin", "plugins"):
        plugins = decoded.get(key, [])
        if not isinstance(plugins, list):
            raise TypeError(f"OpenCode {key} config must contain a JSON array")
        if plugin not in plugins:
            plugins = [*plugins, plugin]
        decoded[key] = plugins
    result = {OPENCODE_CONFIG_CONTENT: json.dumps(decoded, separators=(",", ":"))}
    if native_session_id:
        result[AGENTHUB_OPENCODE_SESSION_ID] = native_session_id
    return result


OPENCODE_ACTIVITY_ADAPTER = OpenCodeActivityAdapter()
opencode_activity_environment = _opencode_activity_environment

__all__ = ["AGENTHUB_OPENCODE_SESSION_ID", "OPENCODE_ACTIVITY_ADAPTER", "OPENCODE_CONFIG_CONTENT", "OpenCodeActivityAdapter", "normalize_opencode_activity", "opencode_activity_environment"]
