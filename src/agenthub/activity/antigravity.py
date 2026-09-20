"""Antigravity activity normalization and passive hook registration."""

from __future__ import annotations

import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import BinaryIO, TextIO

from ._forwarder import run_activity_hook
from .model import AgentActivityEvent, AgentActivityEventKind

_PROVIDER = "antigravity"
_HOOK_NAME = "agenthub-activity-observer"
_HOOK_TIMEOUT_SECONDS = 3
_PASSIVE_EVENTS = ("PreInvocation", "Stop")


def normalize_antigravity_activity(
    session_id: str,
    payload: object,
) -> AgentActivityEvent | None:
    """Translate one Antigravity hook object into a provider-neutral event."""

    if not isinstance(payload, dict):
        return None
    conversation_id = payload.get("conversationId")
    if not isinstance(conversation_id, str) or not conversation_id:
        return None
    event_name = payload.get("hook_event_name")
    if event_name == "PreInvocation":
        kind = AgentActivityEventKind.PROMPT_SUBMITTED
    elif event_name == "Stop":
        fully_idle = payload.get("fullyIdle")
        if not isinstance(fully_idle, bool):
            return None
        kind = (
            AgentActivityEventKind.TURN_COMPLETED
            if fully_idle
            else AgentActivityEventKind.PROMPT_SUBMITTED
        )
    else:
        return None
    return AgentActivityEvent(session_id=session_id, kind=kind)


class AntigravityActivityNormalizer:
    """Normalize activity only for one runtime's root conversation."""

    def __init__(self, root_conversation_id: str | None = None) -> None:
        self._root_conversation_id = root_conversation_id or None

    def __call__(
        self,
        session_id: str,
        payload: object,
    ) -> AgentActivityEvent | None:
        """Bind a fresh root or reject activity from another conversation."""

        if not isinstance(payload, dict):
            return None
        conversation_id = payload.get("conversationId")
        if not isinstance(conversation_id, str) or not conversation_id:
            return None

        event_name = payload.get("hook_event_name")
        if self._root_conversation_id is None:
            if event_name != "PreInvocation":
                return None
            self._root_conversation_id = conversation_id
        elif conversation_id != self._root_conversation_id:
            return None

        return normalize_antigravity_activity(session_id, payload)


def _default_hooks_path() -> Path:
    """Return Antigravity's documented shared hook configuration path."""

    return Path.home() / ".gemini" / "config" / "hooks.json"


def _hook_command(event_name: str) -> str:
    """Build a guarded helper command; correlation remains in child env."""

    helper = (
        sys.executable,
        "-m",
        "agenthub.main",
        "activity-hook",
        _PROVIDER,
        event_name,
    )
    response = json.dumps(_neutral_response(event_name), separators=(",", ":"))
    if os.name == "nt":
        command = subprocess.list2cmdline(helper)
        return (
            f"if defined AGENTHUB_SESSION_ID ({command}) "
            f"else (echo {response})"
        )
    command = shlex.join(helper)
    return (
        'if [ -n "${AGENTHUB_SESSION_ID:-}" ]; then '
        f"exec {command}; else printf '%s\\n' {shlex.quote(response)}; fi"
    )


def _neutral_response(event_name: str) -> dict[str, object]:
    """Return the event-specific response that leaves Antigravity unchanged."""

    return {"decision": "stop"} if event_name == "Stop" else {}


def _activity_hook_config() -> dict[str, object]:
    """Return only passive hooks that cannot gate tools or change model flow."""

    def handler(event_name: str) -> dict[str, object]:
        return {
            "type": "command",
            "command": _hook_command(event_name),
            "timeout": _HOOK_TIMEOUT_SECONDS,
        }

    return {
        "enabled": True,
        "PreInvocation": [handler("PreInvocation")],
        "Stop": [handler("Stop")],
    }


def ensure_antigravity_activity_hooks(*, hooks_path: Path | None = None) -> Path:
    """Install AgentHub's named observer while preserving existing hook entries."""

    path = hooks_path or _default_hooks_path()
    if path.is_symlink():
        path = path.resolve()
    try:
        source = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        hooks: dict[str, object] = {}
        existing_mode = 0o600
    else:
        decoded = json.loads(source)
        if not isinstance(decoded, dict):
            raise TypeError("Antigravity hooks config must contain a JSON object")
        hooks = decoded
        existing_mode = stat.S_IMODE(path.stat().st_mode)

    observer = _activity_hook_config()
    if hooks.get(_HOOK_NAME) == observer:
        return path

    merged = {**hooks, _HOOK_NAME: observer}
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    raw_path: str | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(
            prefix=".agenthub-hooks-",
            suffix=".json",
            dir=path.parent,
        )
        os.fchmod(descriptor, existing_mode)
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
        return path
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        if raw_path is not None:
            try:
                Path(raw_path).unlink(missing_ok=True)
            except OSError:
                pass
        raise


def run_antigravity_activity_hook(
    event_name: str,
    *,
    input_stream: BinaryIO | None = None,
    output_stream: TextIO | None = None,
    environment: Mapping[str, str] | None = None,
) -> int:
    """Forward one passive Antigravity event and return its neutral response."""

    if event_name not in _PASSIVE_EVENTS:
        raise ValueError(f"unsupported Antigravity activity event: {event_name}")
    return run_activity_hook(
        _PROVIDER,
        input_stream=input_stream,
        output_stream=output_stream,
        environment=environment,
        payload_updates={"hook_event_name": event_name},
        neutral_response=_neutral_response(event_name),
    )


__all__ = [
    "AntigravityActivityNormalizer",
    "ensure_antigravity_activity_hooks",
    "normalize_antigravity_activity",
    "run_antigravity_activity_hook",
]
