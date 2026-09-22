"""Devin activity integration."""

from __future__ import annotations

import copy
import json
import os
import shlex
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, TextIO

from agenthub.activity import AgentActivity, AgentActivityEvent, AgentActivityEventKind
from agenthub.activity._forwarder import run_activity_hook
from agenthub.activity.adapter import ActivityLaunch, ActivityNormalizer

_PROVIDER = "devin"
_USER_INPUT_TOOL = "ask_user_question"
_NORMALIZED_EVENTS = {"SessionStart": AgentActivityEventKind.SESSION_STARTED, "UserPromptSubmit": AgentActivityEventKind.PROMPT_SUBMITTED, "PreToolUse": AgentActivityEventKind.TOOL_STARTED, "PermissionRequest": AgentActivityEventKind.PERMISSION_REQUESTED, "PostToolUse": AgentActivityEventKind.TOOL_FINISHED, "Stop": AgentActivityEventKind.TURN_STOP_REQUESTED}


@dataclass(frozen=True)
class DevinActivityLaunch:
    command: tuple[str, ...]
    config_path: Path


def normalize_devin_activity(session_id: str, payload: object) -> AgentActivityEvent | None:
    if not isinstance(payload, dict):
        return None
    name = payload.get("hook_event_name")
    kind = _NORMALIZED_EVENTS.get(name) if isinstance(name, str) else None
    if kind is None:
        return None
    if name == "PreToolUse" and payload.get("tool_name") == _USER_INPUT_TOOL:
        kind = AgentActivityEventKind.INPUT_REQUESTED
    if kind is AgentActivityEventKind.SESSION_STARTED:
        return AgentActivityEvent(session_id, kind)
    prompt_id = payload.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id:
        return None
    return AgentActivityEvent(session_id, kind, prompt_id)


def _strip_comments(source: str) -> str:
    """Remove JSON comments while preserving quoted and escaped content."""

    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(source):
        character = source[index]
        next_character = source[index + 1] if index + 1 < len(source) else ""
        if in_string:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue
        if character == '"':
            in_string = True
            output.append(character)
            index += 1
            continue
        if character == "/" and next_character == "/":
            output.extend((" ", " "))
            index += 2
            while index < len(source) and source[index] not in "\r\n":
                output.append(" ")
                index += 1
            continue
        if character == "/" and next_character == "*":
            output.extend((" ", " "))
            index += 2
            while index < len(source):
                if (
                    source[index] == "*"
                    and index + 1 < len(source)
                    and source[index + 1] == "/"
                ):
                    output.extend((" ", " "))
                    index += 2
                    break
                output.append("\n" if source[index] == "\n" else " ")
                index += 1
            continue
        output.append(character)
        index += 1
    return "".join(output)


def _config_path(command: Sequence[str], environment: Mapping[str, str]) -> Path:
    for i, arg in enumerate(command[1:], 1):
        if arg == "--config":
            if i + 1 >= len(command):
                raise ValueError("Devin --config requires a path")
            return Path(command[i + 1]).expanduser()
        if arg.startswith("--config="):
            value = arg.partition("=")[2]
            if not value:
                raise ValueError("Devin --config requires a path")
            return Path(value).expanduser()
    if sys.platform == "win32" and environment.get("APPDATA"):
        return Path(environment["APPDATA"]) / "devin" / "config.json"
    return Path(environment.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "devin" / "config.json"


def _without_config(command: Sequence[str]) -> tuple[str, ...]:
    result = [command[0]]
    i = 1
    while i < len(command):
        if command[i] == "--config":
            i += 2
        elif command[i].startswith("--config="):
            i += 1
        else:
            result.append(command[i])
            i += 1
    return tuple(result)


def prepare_devin_activity_launch(command: Sequence[str], *, environment: Mapping[str, str] | None = None) -> DevinActivityLaunch:
    if not command:
        raise ValueError("a Devin launch command may not be empty")
    source_path = _config_path(command, os.environ if environment is None else environment)
    try:
        source = source_path.read_text(encoding="utf-8-sig")
        decoded = json.loads(_strip_comments(source))
    except FileNotFoundError:
        decoded = {}
    if not isinstance(decoded, dict):
        raise TypeError("Devin user config must contain a JSON object")
    merged = copy.deepcopy(decoded)
    hooks = merged.get("hooks", {})
    if not isinstance(hooks, dict):
        raise TypeError("Devin hooks config must contain a JSON object")
    observer = {"matcher": "", "hooks": [{"type": "command", "command": shlex.join((sys.executable, "-m", "agenthub.main", "activity-hook", _PROVIDER)), "timeout": 1}]}
    for name in _NORMALIZED_EVENTS:
        configured = hooks.get(name, [])
        if not isinstance(configured, list):
            raise TypeError(f"Devin {name} hooks must contain a JSON array")
        hooks[name] = [*configured, copy.deepcopy(observer)]
    merged["hooks"] = hooks
    descriptor: int | None = None
    raw_path: str | None = None
    try:
        descriptor, raw_path = tempfile.mkstemp(prefix="agenthub-devin-", suffix=".json")
        encoded = json.dumps(merged, separators=(",", ":")).encode("utf-8")
        offset = 0
        while offset < len(encoded):
            written = os.write(descriptor, encoded[offset:])
            if written == 0:
                raise OSError("could not write the Devin activity config")
            offset += written
        os.close(descriptor)
        descriptor = None
        config_path = Path(raw_path)
        base = _without_config(command)
        return DevinActivityLaunch((base[0], "--config", str(config_path), *base[1:]), config_path)
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        if raw_path is not None:
            Path(raw_path).unlink(missing_ok=True)
        raise


class DevinActivityAdapter:
    harness_id = _PROVIDER

    def matches_command(self, command: Sequence[str]) -> bool:
        return bool(command) and Path(command[0]).name == _PROVIDER

    def create_normalizer(self, native_session_id: str | None) -> ActivityNormalizer:
        del native_session_id
        return normalize_devin_activity

    def prepare_launch(self, command: Sequence[str], *, native_session_id: str | None,
                       registration_environment: Mapping[str, str]) -> ActivityLaunch:
        del native_session_id
        launch = prepare_devin_activity_launch(command)
        return ActivityLaunch(launch.command, registration_environment, (launch.config_path,))

    def run_hook(self, event_name: str | None = None, *, input_stream: BinaryIO | None = None,
                 output_stream: TextIO | None = None, environment: Mapping[str, str] | None = None) -> int:
        if event_name is not None:
            raise ValueError("Devin activity hooks do not accept an event argument")
        return run_activity_hook(_PROVIDER, input_stream=input_stream, output_stream=output_stream, environment=environment)

    def terminal_key_event(self, session_id: str, key: str, *, activity: AgentActivity,
                           input_wait_kind: AgentActivityEventKind | None) -> AgentActivityEvent | None:
        del input_wait_kind
        if activity in {AgentActivity.WORKING, AgentActivity.NEEDS_INPUT} and key in {"ctrl+c", "escape"}:
            return AgentActivityEvent(session_id, AgentActivityEventKind.INTERRUPTED)
        return None


def _run_devin_activity_hook(*, input_stream: BinaryIO | None = None,
                              output_stream: TextIO | None = None,
                              environment: Mapping[str, str] | None = None) -> int:
    return DEVIN_ACTIVITY_ADAPTER.run_hook(input_stream=input_stream, output_stream=output_stream, environment=environment)


DEVIN_ACTIVITY_ADAPTER = DevinActivityAdapter()
run_devin_activity_hook = _run_devin_activity_hook

__all__ = ["DEVIN_ACTIVITY_ADAPTER", "DevinActivityAdapter", "DevinActivityLaunch", "normalize_devin_activity", "prepare_devin_activity_launch", "run_devin_activity_hook"]
