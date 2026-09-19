"""Codex lifecycle normalization and passive hook forwarding."""

from __future__ import annotations

import json
import os
import shlex
import socket
import sys
from collections.abc import Mapping, Sequence
from typing import BinaryIO, TextIO
from urllib.parse import urlsplit

from .model import AgentActivityEvent, AgentActivityEventKind

AGENTHUB_SESSION_ID = "AGENTHUB_SESSION_ID"
AGENTHUB_ACTIVITY_ENDPOINT = "AGENTHUB_ACTIVITY_ENDPOINT"
AGENTHUB_ACTIVITY_TOKEN = "AGENTHUB_ACTIVITY_TOKEN"

_MAX_INPUT_BYTES = 1_000_000
_NEUTRAL_RESPONSE = "{}\n"
_PROTOCOL_VERSION = 1
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
    return AgentActivityEvent(session_id=session_id, kind=kind)


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
            "timeout=1,async=true}]}]"
        )
        overrides.extend(("-c", config))
    return (command[0], *overrides, *command[1:])


def _write_neutral_response(output: TextIO) -> None:
    try:
        output.write(_NEUTRAL_RESPONSE)
        output.flush()
    except Exception:  # noqa: BLE001, S110 - observation must never affect Codex
        pass


def _loopback_address(endpoint: str) -> tuple[str, int] | None:
    """Parse only the loopback TCP endpoint format emitted by AgentHub."""

    try:
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "tcp"
            or parsed.hostname != "127.0.0.1"
            or parsed.port is None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            return None
        return parsed.hostname, parsed.port
    except ValueError:
        return None


def run_codex_activity_hook(
    *,
    input_stream: BinaryIO | None = None,
    output_stream: TextIO | None = None,
    environment: Mapping[str, str] | None = None,
) -> int:
    """Forward one Codex event locally and always return a neutral hook result."""

    source = sys.stdin.buffer if input_stream is None else input_stream
    output = sys.stdout if output_stream is None else output_stream
    env = os.environ if environment is None else environment
    try:
        payload = source.read(_MAX_INPUT_BYTES + 1)
        if len(payload) > _MAX_INPUT_BYTES:
            raise ValueError("hook payload exceeded the local receiver limit")
        decoded = json.loads(payload)
        if not isinstance(decoded, dict):
            raise TypeError("hook payload was not an object")

        session_id = env.get(AGENTHUB_SESSION_ID, "")
        endpoint = _loopback_address(env.get(AGENTHUB_ACTIVITY_ENDPOINT, ""))
        token = env.get(AGENTHUB_ACTIVITY_TOKEN, "")
        if not session_id or endpoint is None or not token:
            raise ValueError("activity forwarding is not configured")

        envelope = json.dumps(
            {
                "version": _PROTOCOL_VERSION,
                "provider": _PROVIDER,
                "session_id": session_id,
                "token": token,
                "event": decoded,
            },
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        with socket.create_connection(endpoint, timeout=0.25) as connection:
            connection.settimeout(0.25)
            connection.sendall(envelope)
    except Exception:  # noqa: BLE001, S110 - activity is strictly best effort
        pass

    _write_neutral_response(output)
    return 0


__all__ = [
    "AGENTHUB_ACTIVITY_ENDPOINT",
    "AGENTHUB_ACTIVITY_TOKEN",
    "AGENTHUB_SESSION_ID",
    "codex_command_with_activity_hooks",
    "normalize_codex_activity",
    "run_codex_activity_hook",
]
