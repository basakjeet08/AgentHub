"""Antigravity activity integration."""

from __future__ import annotations

import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import BinaryIO, TextIO

from agenthub.activity import AgentActivity, AgentActivityEvent, AgentActivityEventKind
from agenthub.activity._forwarder import run_activity_hook
from agenthub.activity.adapter import ActivityLaunch, ActivityNormalizer

_PROVIDER = "antigravity"
_HOOK_NAME = "agenthub-activity-observer"
_PASSIVE_EVENTS = ("PreInvocation", "Stop")


def normalize_antigravity_activity(session_id: str, payload: object) -> AgentActivityEvent | None:
    if not isinstance(payload, dict):
        return None
    conversation = payload.get("conversationId")
    name = payload.get("hook_event_name")
    if not isinstance(conversation, str) or not conversation:
        return None
    if name == "PreInvocation":
        kind = AgentActivityEventKind.PROMPT_SUBMITTED
    elif name == "Stop" and isinstance(payload.get("fullyIdle"), bool):
        kind = AgentActivityEventKind.TURN_COMPLETED if payload["fullyIdle"] else AgentActivityEventKind.PROMPT_SUBMITTED
    else:
        return None
    return AgentActivityEvent(session_id, kind)


class AntigravityActivityNormalizer:
    def __init__(self, root_conversation_id: str | None = None) -> None:
        self._root = root_conversation_id or None

    def __call__(self, session_id: str, payload: object) -> AgentActivityEvent | None:
        if not isinstance(payload, dict):
            return None
        conversation = payload.get("conversationId")
        if not isinstance(conversation, str) or not conversation:
            return None
        if self._root is None:
            if payload.get("hook_event_name") != "PreInvocation":
                return None
            self._root = conversation
        elif conversation != self._root:
            return None
        return normalize_antigravity_activity(session_id, payload)


def _hook_command(event_name: str) -> str:
    helper = (sys.executable, "-m", "agenthub.main", "activity-hook", _PROVIDER, event_name)
    response = json.dumps({"decision": "stop"} if event_name == "Stop" else {}, separators=(",", ":"))
    if os.name == "nt":
        return f"if defined AGENTHUB_SESSION_ID ({subprocess.list2cmdline(helper)}) else (echo {response})"
    return f'''if [ -n "${{AGENTHUB_SESSION_ID:-}}" ]; then exec {shlex.join(helper)}; else printf '%s\\n' {shlex.quote(response)}; fi'''


def ensure_antigravity_activity_hooks(*, hooks_path: Path | None = None) -> Path:
    path = hooks_path or Path.home() / ".gemini" / "config" / "hooks.json"
    if path.is_symlink():
        path = path.resolve()
    try:
        decoded = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(decoded, dict):
            raise TypeError("Antigravity hooks config must contain a JSON object")
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        decoded, mode = {}, 0o600
    observer = {"enabled": True, "PreInvocation": [{"type": "command", "command": _hook_command("PreInvocation"), "timeout": 3}], "Stop": [{"type": "command", "command": _hook_command("Stop"), "timeout": 3}]}
    if decoded.get(_HOOK_NAME) == observer:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = {**decoded, _HOOK_NAME: observer}
    descriptor: int | None = None
    raw_path: str | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=".agenthub-hooks-", suffix=".json", dir=path.parent
        )
        os.fchmod(descriptor, mode)
        encoded = (json.dumps(merged, indent=2) + "\n").encode("utf-8")
        offset = 0
        while offset < len(encoded):
            written = os.write(descriptor, encoded[offset:])
            if written == 0:
                raise OSError("could not write the Antigravity hook config")
            offset += written
        os.close(descriptor)
        descriptor = None
        os.replace(raw_path, path)
        raw_path = None
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        if raw_path is not None:
            Path(raw_path).unlink(missing_ok=True)
        raise
    return path


class AntigravityActivityAdapter:
    harness_id = _PROVIDER

    def matches_command(self, command: Sequence[str]) -> bool:
        return bool(command) and Path(command[0]).name == "agy"

    def create_normalizer(self, native_session_id: str | None) -> ActivityNormalizer:
        return AntigravityActivityNormalizer(native_session_id)

    def prepare_launch(self, command: Sequence[str], *, native_session_id: str | None,
                       registration_environment: Mapping[str, str]) -> ActivityLaunch:
        del native_session_id
        ensure_antigravity_activity_hooks()
        return ActivityLaunch(tuple(command), registration_environment)

    def run_hook(self, event_name: str | None = None, *, input_stream: BinaryIO | None = None,
                 output_stream: TextIO | None = None, environment: Mapping[str, str] | None = None) -> int:
        if event_name not in _PASSIVE_EVENTS:
            raise ValueError(f"unsupported Antigravity activity event: {event_name}")
        return run_activity_hook(_PROVIDER, input_stream=input_stream, output_stream=output_stream, environment=environment, payload_updates={"hook_event_name": event_name}, neutral_response={"decision": "stop"} if event_name == "Stop" else {})

    def terminal_key_event(self, session_id: str, key: str, *, activity: AgentActivity,
                           input_wait_kind: AgentActivityEventKind | None) -> AgentActivityEvent | None:
        del session_id, key, activity, input_wait_kind
        return None


def _run_antigravity_activity_hook(event_name: str, *, input_stream: BinaryIO | None = None,
                                   output_stream: TextIO | None = None,
                                   environment: Mapping[str, str] | None = None) -> int:
    return ANTIGRAVITY_ACTIVITY_ADAPTER.run_hook(event_name, input_stream=input_stream, output_stream=output_stream, environment=environment)


ANTIGRAVITY_ACTIVITY_ADAPTER = AntigravityActivityAdapter()
run_antigravity_activity_hook = _run_antigravity_activity_hook

__all__ = ["ANTIGRAVITY_ACTIVITY_ADAPTER", "AntigravityActivityAdapter", "AntigravityActivityNormalizer", "ensure_antigravity_activity_hooks", "normalize_antigravity_activity", "run_antigravity_activity_hook"]
