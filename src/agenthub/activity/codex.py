"""Codex lifecycle normalization and passive hook forwarding."""

from __future__ import annotations

import json
import shlex
import sys
from collections.abc import Mapping, Sequence
from typing import BinaryIO, TextIO

from ._forwarder import run_activity_hook
from .model import AgentActivityEvent, AgentActivityEventKind

_PROVIDER = "codex"
_HOOK_EVENTS = (
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "Stop",
    "Interrupt",
)
_NORMALIZED_EVENTS = {
    "UserPromptSubmit": AgentActivityEventKind.PROMPT_SUBMITTED,
    "PreToolUse": AgentActivityEventKind.TOOL_STARTED,
    "PermissionRequest": AgentActivityEventKind.PERMISSION_REQUESTED,
    "PostToolUse": AgentActivityEventKind.TOOL_FINISHED,
    "Stop": AgentActivityEventKind.TURN_COMPLETED,
    "Interrupt": AgentActivityEventKind.INTERRUPTED,
}


def normalize_codex_activity(
    session_id: str,
    payload: object,
) -> AgentActivityEvent | None:
    """Translate one Codex hook object into a provider-neutral event."""

    if not isinstance(payload, dict):
        return None
    event_name = payload.get("hook_event_name")
    if not isinstance(event_name, str):
        return None
    kind = _NORMALIZED_EVENTS.get(event_name)
    if kind is None:
        return None
    turn_id = payload.get("turn_id")
    if not isinstance(turn_id, str) or not turn_id:
        return None
    return AgentActivityEvent(session_id=session_id, kind=kind, scope_id=turn_id)


def codex_command_with_activity_hooks(command: Sequence[str]) -> tuple[str, ...]:
    """Add one static passive hook definition for each supported Codex event."""

    if not command:
        raise ValueError("a Codex launch command may not be empty")
    hook_command = shlex.join(
        (sys.executable, "-m", "agenthub.main", "activity-hook", _PROVIDER)
    )
    encoded_command = json.dumps(hook_command)
    overrides: list[str] = []
    for event_name in _HOOK_EVENTS:
        config = (
            f"hooks.{event_name}="
            f"[{{hooks=[{{type=\"command\",command={encoded_command},"
            "timeout=3,async=true}]}]"
        )
        overrides.extend(("-c", config))
    return (command[0], *overrides, *command[1:])


def run_codex_activity_hook(
    *,
    input_stream: BinaryIO | None = None,
    output_stream: TextIO | None = None,
    environment: Mapping[str, str] | None = None,
) -> int:
    """Forward one Codex event locally and always return a neutral hook result."""
    return run_activity_hook(
        _PROVIDER,
        input_stream=input_stream,
        output_stream=output_stream,
        environment=environment,
    )


__all__ = [
    "codex_command_with_activity_hooks",
    "normalize_codex_activity",
    "run_codex_activity_hook",
]
