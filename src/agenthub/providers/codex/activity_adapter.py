"""Codex activity integration."""

from __future__ import annotations

import json
import shlex
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import BinaryIO, TextIO

from agenthub.activity import AgentActivity, AgentActivityEvent, AgentActivityEventKind
from agenthub.activity._forwarder import run_activity_hook
from agenthub.activity.adapter import ActivityLaunch, ActivityNormalizer

_PROVIDER = "codex"
_USER_INPUT_TOOL = "request_user_input"
_HOOK_EVENTS = ("UserPromptSubmit", "PreToolUse", "PermissionRequest", "PostToolUse", "Stop", "Interrupt")
_NORMALIZED_EVENTS = {
    "UserPromptSubmit": AgentActivityEventKind.PROMPT_SUBMITTED,
    "PreToolUse": AgentActivityEventKind.TOOL_STARTED,
    "PermissionRequest": AgentActivityEventKind.PERMISSION_REQUESTED,
    "PostToolUse": AgentActivityEventKind.TOOL_FINISHED,
    "Stop": AgentActivityEventKind.TURN_COMPLETED,
    "Interrupt": AgentActivityEventKind.INTERRUPTED,
}


def normalize_codex_activity(session_id: str, payload: object) -> AgentActivityEvent | None:
    if not isinstance(payload, dict):
        return None
    event_name = payload.get("hook_event_name")
    kind = _NORMALIZED_EVENTS.get(event_name) if isinstance(event_name, str) else None
    if kind is None:
        return None
    if event_name == "PreToolUse" and payload.get("tool_name") == _USER_INPUT_TOOL:
        kind = AgentActivityEventKind.INPUT_REQUESTED
    turn_id = payload.get("turn_id")
    if not isinstance(turn_id, str) or not turn_id:
        return None
    return AgentActivityEvent(session_id, kind, turn_id)


class CodexActivityAdapter:
    harness_id = _PROVIDER

    def matches_command(self, command: Sequence[str]) -> bool:
        return bool(command) and Path(command[0]).name == _PROVIDER

    def create_normalizer(self, native_session_id: str | None) -> ActivityNormalizer:
        del native_session_id
        return normalize_codex_activity

    def prepare_launch(self, command: Sequence[str], *, native_session_id: str | None,
                       registration_environment: Mapping[str, str]) -> ActivityLaunch:
        del native_session_id
        if not command:
            raise ValueError("a Codex launch command may not be empty")
        hook_command = shlex.join((sys.executable, "-m", "agenthub.main", "activity-hook", _PROVIDER))
        overrides: list[str] = []
        for event_name in _HOOK_EVENTS:
            config = f"hooks.{event_name}=[{{hooks=[{{type=\"command\",command={json.dumps(hook_command)},timeout=3,async=true}}]}}]"
            overrides.extend(("-c", config))
        return ActivityLaunch((command[0], *overrides, *command[1:]), registration_environment)

    def run_hook(self, event_name: str | None = None, *, input_stream: BinaryIO | None = None,
                 output_stream: TextIO | None = None, environment: Mapping[str, str] | None = None) -> int:
        if event_name is not None:
            raise ValueError("Codex activity hooks do not accept an event argument")
        return run_activity_hook(_PROVIDER, input_stream=input_stream, output_stream=output_stream, environment=environment)

    def terminal_key_event(self, session_id: str, key: str, *, activity: AgentActivity,
                           input_wait_kind: AgentActivityEventKind | None) -> AgentActivityEvent | None:
        if activity is AgentActivity.NEEDS_INPUT and input_wait_kind is AgentActivityEventKind.PERMISSION_REQUESTED and key in {"enter", "ctrl+m", "y", "n"}:
            return AgentActivityEvent(session_id, AgentActivityEventKind.INPUT_RESOLVED)
        return None


def _codex_command_with_activity_hooks(command: Sequence[str]) -> tuple[str, ...]:
    return CODEX_ACTIVITY_ADAPTER.prepare_launch(
        command,
        native_session_id=None,
        registration_environment={},
    ).command


def _run_codex_activity_hook(*, input_stream: BinaryIO | None = None,
                              output_stream: TextIO | None = None,
                              environment: Mapping[str, str] | None = None) -> int:
    return CODEX_ACTIVITY_ADAPTER.run_hook(input_stream=input_stream, output_stream=output_stream, environment=environment)


CODEX_ACTIVITY_ADAPTER = CodexActivityAdapter()
codex_command_with_activity_hooks = _codex_command_with_activity_hooks
run_codex_activity_hook = _run_codex_activity_hook

__all__ = ["CODEX_ACTIVITY_ADAPTER", "CodexActivityAdapter", "codex_command_with_activity_hooks", "normalize_codex_activity", "run_codex_activity_hook"]
