"""Devin lifecycle normalization and passive hook configuration."""

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

from ._forwarder import run_activity_hook
from .model import AgentActivityEvent, AgentActivityEventKind

_PROVIDER = "devin"
_HOOK_TIMEOUT_SECONDS = 1
_USER_INPUT_TOOL = "ask_user_question"
_NORMALIZED_EVENTS = {
    "SessionStart": AgentActivityEventKind.SESSION_STARTED,
    "UserPromptSubmit": AgentActivityEventKind.PROMPT_SUBMITTED,
    "PreToolUse": AgentActivityEventKind.TOOL_STARTED,
    "PermissionRequest": AgentActivityEventKind.PERMISSION_REQUESTED,
    "PostToolUse": AgentActivityEventKind.TOOL_FINISHED,
    "Stop": AgentActivityEventKind.TURN_STOP_REQUESTED,
}


@dataclass(frozen=True)
class DevinActivityLaunch:
    """A Devin command plus the temporary merged config it consumes."""

    command: tuple[str, ...]
    config_path: Path


def normalize_devin_activity(
    session_id: str,
    payload: object,
) -> AgentActivityEvent | None:
    """Translate one Devin hook object into a provider-neutral event."""

    if not isinstance(payload, dict):
        return None
    event_name = payload.get("hook_event_name")
    if not isinstance(event_name, str):
        return None
    kind = _NORMALIZED_EVENTS.get(event_name)
    if kind is None:
        return None
    if event_name == "PreToolUse" and payload.get("tool_name") == _USER_INPUT_TOOL:
        kind = AgentActivityEventKind.INPUT_REQUESTED
    if kind is AgentActivityEventKind.SESSION_STARTED:
        return AgentActivityEvent(session_id=session_id, kind=kind)
    prompt_id = payload.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id:
        return None
    return AgentActivityEvent(session_id=session_id, kind=kind, scope_id=prompt_id)


def _strip_json_comments(source: str) -> str:
    """Remove JSON line/block comments while preserving quoted content."""

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
                if source[index] == "*" and index + 1 < len(source) and source[index + 1] == "/":
                    output.extend((" ", " "))
                    index += 2
                    break
                output.append("\n" if source[index] == "\n" else " ")
                index += 1
            continue
        output.append(character)
        index += 1
    return "".join(output)


def _default_devin_config_path(environment: Mapping[str, str]) -> Path:
    """Resolve Devin's documented per-user configuration location."""

    if sys.platform == "win32":
        app_data = environment.get("APPDATA")
        if app_data:
            return Path(app_data) / "devin" / "config.json"
    config_home = environment.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / "devin" / "config.json"
    return Path.home() / ".config" / "devin" / "config.json"


def _configured_devin_path(command: Sequence[str]) -> Path | None:
    """Return an existing explicit --config value, rejecting incomplete flags."""

    for index, argument in enumerate(command[1:], start=1):
        if argument == "--config":
            if index + 1 >= len(command):
                raise ValueError("Devin --config requires a path")
            return Path(command[index + 1]).expanduser()
        if argument.startswith("--config="):
            value = argument.partition("=")[2]
            if not value:
                raise ValueError("Devin --config requires a path")
            return Path(value).expanduser()
    return None


def _without_devin_config(command: Sequence[str]) -> tuple[str, ...]:
    """Remove an explicit --config option before adding the merged overlay."""

    result = [command[0]]
    index = 1
    while index < len(command):
        argument = command[index]
        if argument == "--config":
            index += 2
            continue
        if argument.startswith("--config="):
            index += 1
            continue
        result.append(argument)
        index += 1
    return tuple(result)


def _read_devin_config(path: Path) -> dict[str, object]:
    """Read Devin's comment-tolerant JSON without changing the source file."""

    try:
        source = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}
    decoded = json.loads(_strip_json_comments(source))
    if not isinstance(decoded, dict):
        raise TypeError("Devin user config must contain a JSON object")
    return decoded


def _config_with_activity_hooks(config: Mapping[str, object]) -> dict[str, object]:
    """Append AgentHub observers while preserving every existing Devin setting."""

    merged = copy.deepcopy(dict(config))
    existing_hooks = merged.get("hooks", {})
    if not isinstance(existing_hooks, dict):
        raise TypeError("Devin hooks config must contain a JSON object")
    hooks = copy.deepcopy(existing_hooks)
    hook_command = shlex.join(
        (sys.executable, "-m", "agenthub.main", "activity-hook", _PROVIDER)
    )
    observer = {
        "matcher": "",
        "hooks": [
            {
                "type": "command",
                "command": hook_command,
                "timeout": _HOOK_TIMEOUT_SECONDS,
            }
        ],
    }
    for event_name in _NORMALIZED_EVENTS:
        configured = hooks.get(event_name, [])
        if not isinstance(configured, list):
            raise TypeError(f"Devin {event_name} hooks must contain a JSON array")
        hooks[event_name] = [*configured, copy.deepcopy(observer)]
    merged["hooks"] = hooks
    return merged


def prepare_devin_activity_launch(
    command: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
) -> DevinActivityLaunch:
    """Create a secure per-process config overlay containing passive hooks."""

    if not command:
        raise ValueError("a Devin launch command may not be empty")
    env = os.environ if environment is None else environment
    source_path = _configured_devin_path(command) or _default_devin_config_path(env)
    merged = _config_with_activity_hooks(_read_devin_config(source_path))

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
        base_command = _without_devin_config(command)
        return DevinActivityLaunch(
            command=(base_command[0], "--config", str(config_path), *base_command[1:]),
            config_path=config_path,
        )
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        if raw_path is not None:
            try:
                Path(raw_path).unlink(missing_ok=True)
            except OSError:
                pass
        raise


def run_devin_activity_hook(
    *,
    input_stream: BinaryIO | None = None,
    output_stream: TextIO | None = None,
    environment: Mapping[str, str] | None = None,
) -> int:
    """Forward one Devin event locally and always return a neutral hook result."""

    return run_activity_hook(
        _PROVIDER,
        input_stream=input_stream,
        output_stream=output_stream,
        environment=environment,
    )


__all__ = [
    "DevinActivityLaunch",
    "normalize_devin_activity",
    "prepare_devin_activity_launch",
    "run_devin_activity_hook",
]
