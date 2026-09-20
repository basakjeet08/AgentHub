"""Tests for Antigravity activity normalization, hooks, and correlation."""

import asyncio
import io
import json
import stat
import subprocess
from collections.abc import Mapping
from pathlib import Path

import pytest

from agenthub.activity import (
    AGENTHUB_SESSION_ID,
    ActivityReceiver,
    AgentActivity,
    AgentActivityEventKind,
    ensure_antigravity_activity_hooks,
    normalize_antigravity_activity,
    run_antigravity_activity_hook,
)
from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.sessions import SessionKind


def test_antigravity_pre_invocation_maps_to_working() -> None:
    event = normalize_antigravity_activity(
        "logical-session",
        {"hook_event_name": "PreInvocation", "conversationId": "native-session"},
    )

    assert event is not None
    assert event.session_id == "logical-session"
    assert event.kind is AgentActivityEventKind.PROMPT_SUBMITTED
    assert event.scope_id is None


@pytest.mark.parametrize(
    ("fully_idle", "expected"),
    [
        (True, AgentActivityEventKind.TURN_COMPLETED),
        (False, AgentActivityEventKind.PROMPT_SUBMITTED),
    ],
)
def test_antigravity_stop_respects_fully_idle(
    fully_idle: bool,
    expected: AgentActivityEventKind,
) -> None:
    event = normalize_antigravity_activity(
        "logical-session",
        {"hook_event_name": "Stop", "fullyIdle": fully_idle},
    )

    assert event is not None
    assert event.kind is expected


@pytest.mark.parametrize(
    "payload",
    [
        {"hook_event_name": "Stop"},
        {"hook_event_name": "Stop", "fullyIdle": "true"},
        {"hook_event_name": "PostInvocation"},
        {"hook_event_name": "PreToolUse", "toolCall": {"name": "ask_question"}},
        {"hook_event_name": "PermissionRequest"},
        {"hook_event_name": "FutureEvent"},
        {},
        [],
    ],
)
def test_antigravity_ignores_unsupported_or_invalid_events(payload: object) -> None:
    assert normalize_antigravity_activity("logical-session", payload) is None


def test_antigravity_hook_install_preserves_existing_named_hooks(tmp_path: Path) -> None:
    hooks_path = tmp_path / "config" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        json.dumps(
            {
                "user-linter": {
                    "PostToolUse": [
                        {
                            "matcher": "run_command",
                            "hooks": [{"command": "lint", "timeout": 10}],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    hooks_path.chmod(0o640)

    result = ensure_antigravity_activity_hooks(hooks_path=hooks_path)

    assert result == hooks_path
    merged = json.loads(hooks_path.read_text(encoding="utf-8"))
    assert merged["user-linter"]["PostToolUse"][0]["hooks"][0]["command"] == "lint"
    observer = merged["agenthub-activity-observer"]
    assert observer["enabled"] is True
    assert set(observer) == {"enabled", "PreInvocation", "Stop"}
    assert "PreToolUse" not in observer
    assert "PostToolUse" not in observer
    for event_name in ("PreInvocation", "Stop"):
        handler = observer[event_name][0]
        assert handler["type"] == "command"
        assert handler["timeout"] == 3
        assert f"-m agenthub.main activity-hook antigravity {event_name}" in handler[
            "command"
        ]
        assert "AGENTHUB_SESSION_ID" in handler["command"]
    assert stat.S_IMODE(hooks_path.stat().st_mode) == 0o640


def test_antigravity_hook_install_is_idempotent_and_private_by_default(
    tmp_path: Path,
) -> None:
    hooks_path = tmp_path / "config" / "hooks.json"

    ensure_antigravity_activity_hooks(hooks_path=hooks_path)
    first = hooks_path.read_bytes()
    ensure_antigravity_activity_hooks(hooks_path=hooks_path)

    assert hooks_path.read_bytes() == first
    assert stat.S_IMODE(hooks_path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    ("event_name", "expected_response"),
    [("PreInvocation", "{}\n"), ("Stop", '{"decision":"stop"}\n')],
)
def test_installed_hook_is_inert_outside_agenthub(
    tmp_path: Path,
    event_name: str,
    expected_response: str,
) -> None:
    hooks_path = tmp_path / "hooks.json"
    ensure_antigravity_activity_hooks(hooks_path=hooks_path)
    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
    command = hooks["agenthub-activity-observer"][event_name][0]["command"]

    completed = subprocess.run(
        command,
        shell=True,
        input="{}",
        text=True,
        capture_output=True,
        env={},
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == expected_response
    assert completed.stderr == ""


def test_antigravity_hook_install_rejects_invalid_existing_config(tmp_path: Path) -> None:
    hooks_path = tmp_path / "hooks.json"
    hooks_path.write_text("[]", encoding="utf-8")

    with pytest.raises(TypeError, match="JSON object"):
        ensure_antigravity_activity_hooks(hooks_path=hooks_path)

    assert hooks_path.read_text(encoding="utf-8") == "[]"


async def _forward_event(
    environment: Mapping[str, str],
    event_name: str,
    **payload: object,
) -> str:
    output = io.StringIO()
    exit_code = await asyncio.to_thread(
        run_antigravity_activity_hook,
        event_name,
        input_stream=io.BytesIO(json.dumps(payload).encode("utf-8")),
        output_stream=output,
        environment=environment,
    )
    assert exit_code == 0
    return output.getvalue()


async def test_antigravity_receiver_routes_two_sessions_without_cross_updates() -> None:
    received = []
    receiver = ActivityReceiver(received.append)
    await receiver.start()
    first = receiver.register("first-session", "antigravity")
    second = receiver.register("second-session", "antigravity")
    try:
        crossed_environment = {
            **first.environment,
            AGENTHUB_SESSION_ID: second.session_id,
        }
        assert await _forward_event(crossed_environment, "PreInvocation") == "{}\n"
        await asyncio.sleep(0.01)
        assert received == []

        await _forward_event(first.environment, "PreInvocation")
        assert await _forward_event(second.environment, "Stop", fullyIdle=True) == (
            '{"decision":"stop"}\n'
        )
        for _ in range(20):
            if len(received) == 2:
                break
            await asyncio.sleep(0.01)

        assert [(event.session_id, event.kind) for event in received] == [
            ("first-session", AgentActivityEventKind.PROMPT_SUBMITTED),
            ("second-session", AgentActivityEventKind.TURN_COMPLETED),
        ]
    finally:
        await receiver.close()


@pytest.mark.parametrize(
    ("event_name", "expected_response"),
    [
        ("PreInvocation", "{}\n"),
        ("Stop", '{"decision":"stop"}\n'),
    ],
)
def test_antigravity_receiver_failure_returns_neutral_provider_response(
    event_name: str,
    expected_response: str,
) -> None:
    output = io.StringIO()

    exit_code = run_antigravity_activity_hook(
        event_name,
        input_stream=io.BytesIO(b'{"fullyIdle":true}'),
        output_stream=output,
        environment={},
    )

    assert exit_code == 0
    assert output.getvalue() == expected_response


async def test_antigravity_hooks_update_sidebar_activity_end_to_end(
    tmp_path: Path,
    monkeypatch,
) -> None:
    hooks_path = tmp_path / "hooks.json"
    monkeypatch.setattr(
        "agenthub.app.ensure_antigravity_activity_hooks",
        lambda: ensure_antigravity_activity_hooks(hooks_path=hooks_path),
    )
    harness = AgentHarness(
        id="antigravity",
        display_name="Antigravity",
        command=("agy",),
        scroll=None,
    )
    app = AgentHubApp(agent_harnesses={harness.id: harness})
    session = app.session_manager.create(
        name="Antigravity",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=harness,
    )
    monkeypatch.setattr(app, "_refresh_sidebar", lambda: None)
    terminal = session.terminal
    assert terminal is not None

    tracking_ready = await app._prepare_activity_tracking(session, terminal)
    assert tracking_ready is True
    assert terminal.child_command == ("agy",)
    assert hooks_path.exists()
    app._initialize_mounted_activity(session)
    assert session.activity is AgentActivity.IDLE
    registration = app._activity_registrations[session.id]
    try:
        await _forward_event(registration.environment, "PreInvocation")
        for _ in range(20):
            if session.activity is AgentActivity.WORKING:
                break
            await asyncio.sleep(0.01)
        assert session.activity is AgentActivity.WORKING

        await _forward_event(registration.environment, "Stop", fullyIdle=False)
        await asyncio.sleep(0.02)
        assert session.activity is AgentActivity.WORKING

        await _forward_event(registration.environment, "Stop", fullyIdle=True)
        for _ in range(20):
            if session.activity is AgentActivity.DONE:
                break
            await asyncio.sleep(0.01)
        assert session.activity is AgentActivity.DONE
        assert session.activity is not AgentActivity.NEEDS_INPUT
    finally:
        receiver = app._activity_receiver
        assert receiver is not None
        await receiver.close()


async def test_antigravity_hook_install_failure_does_not_change_launch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def fail_install() -> None:
        raise OSError("hooks config is unavailable")

    monkeypatch.setattr("agenthub.app.ensure_antigravity_activity_hooks", fail_install)
    harness = AgentHarness(
        id="antigravity",
        display_name="Antigravity",
        command=("agy",),
        scroll=None,
    )
    app = AgentHubApp(agent_harnesses={harness.id: harness})
    session = app.session_manager.create(
        name="Antigravity",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=harness,
    )
    terminal = session.terminal
    assert terminal is not None

    tracking_ready = await app._prepare_activity_tracking(session, terminal)

    assert tracking_ready is False
    assert terminal.child_command == harness.command
    assert session.id not in app._activity_registrations
    receiver = app._activity_receiver
    assert receiver is not None
    await receiver.close()
