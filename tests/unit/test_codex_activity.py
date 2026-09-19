"""Tests for Codex activity normalization, forwarding, and correlation."""

import asyncio
import io
from collections.abc import Mapping

import pytest

from agenthub.activity import (
    AGENTHUB_ACTIVITY_ENDPOINT,
    AGENTHUB_ACTIVITY_TOKEN,
    AGENTHUB_SESSION_ID,
    ActivityReceiver,
    AgentActivity,
    AgentActivityEventKind,
    codex_command_with_activity_hooks,
    normalize_codex_activity,
    run_codex_activity_hook,
)
from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.sessions import SessionKind


@pytest.mark.parametrize(
    ("provider_event", "expected"),
    [
        ("UserPromptSubmit", AgentActivityEventKind.PROMPT_SUBMITTED),
        ("PreToolUse", AgentActivityEventKind.TOOL_STARTED),
        ("PermissionRequest", AgentActivityEventKind.PERMISSION_REQUESTED),
        ("PostToolUse", AgentActivityEventKind.TOOL_FINISHED),
        ("Stop", AgentActivityEventKind.TURN_COMPLETED),
        ("Interrupt", AgentActivityEventKind.INTERRUPTED),
    ],
)
def test_codex_normalizer_maps_observed_events(
    provider_event: str,
    expected: AgentActivityEventKind,
) -> None:
    event = normalize_codex_activity("logical-session", {"hook_event_name": provider_event})

    assert event is not None
    assert event.session_id == "logical-session"
    assert event.kind is expected


@pytest.mark.parametrize(
    "payload",
    [
        {"hook_event_name": "SessionStart"},
        {"hook_event_name": "SessionEnd"},
        {"hook_event_name": "FutureEvent"},
        {},
        [],
    ],
)
def test_codex_normalizer_ignores_non_activity_events(payload: object) -> None:
    assert normalize_codex_activity("logical-session", payload) is None


def test_codex_hook_configuration_is_static_and_precedes_resume() -> None:
    command = codex_command_with_activity_hooks(("codex", "resume", "native-id"))

    assert command[0] == "codex"
    assert command[-2:] == ("resume", "native-id")
    serialized = "\n".join(command)
    for event_name in (
        "UserPromptSubmit",
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "Stop",
        "Interrupt",
    ):
        assert f"hooks.{event_name}=" in serialized
    assert "hooks.SessionStart=" not in serialized
    assert "hooks.SessionEnd=" not in serialized
    assert AGENTHUB_SESSION_ID not in serialized
    assert AGENTHUB_ACTIVITY_ENDPOINT not in serialized
    assert AGENTHUB_ACTIVITY_TOKEN not in serialized


async def _forward_event(environment: Mapping[str, str], event_name: str) -> str:
    output = io.StringIO()
    exit_code = await asyncio.to_thread(
        run_codex_activity_hook,
        input_stream=io.BytesIO(
            f'{{"hook_event_name":"{event_name}"}}'.encode()
        ),
        output_stream=output,
        environment=environment,
    )
    assert exit_code == 0
    return output.getvalue()


async def test_receiver_routes_two_sessions_without_cross_updates() -> None:
    received = []
    receiver = ActivityReceiver(received.append)
    await receiver.start()
    first = receiver.register("first-session", "codex")
    second = receiver.register("second-session", "codex")
    try:
        crossed_environment = {
            **first.environment,
            AGENTHUB_SESSION_ID: second.session_id,
        }
        assert await _forward_event(crossed_environment, "UserPromptSubmit") == "{}\n"
        await asyncio.sleep(0.01)
        assert received == []

        await _forward_event(first.environment, "PreToolUse")
        await _forward_event(second.environment, "PermissionRequest")
        for _ in range(20):
            if len(received) == 2:
                break
            await asyncio.sleep(0.01)

        assert [(event.session_id, event.kind) for event in received] == [
            ("first-session", AgentActivityEventKind.TOOL_STARTED),
            ("second-session", AgentActivityEventKind.PERMISSION_REQUESTED),
        ]
    finally:
        await receiver.close()


async def test_revoked_or_invalid_credentials_are_ignored() -> None:
    received = []
    receiver = ActivityReceiver(received.append)
    await receiver.start()
    registration = receiver.register("session", "codex")
    receiver.revoke(registration)
    try:
        environment = {
            **registration.environment,
            AGENTHUB_ACTIVITY_TOKEN: "invalid-token",
        }
        await _forward_event(environment, "Stop")
        await asyncio.sleep(0.01)
        assert received == []
    finally:
        await receiver.close()


def test_hook_receiver_failure_is_neutral() -> None:
    output = io.StringIO()

    exit_code = run_codex_activity_hook(
        input_stream=io.BytesIO(b'{"hook_event_name":"UserPromptSubmit"}'),
        output_stream=output,
        environment={
            AGENTHUB_SESSION_ID: "session",
            AGENTHUB_ACTIVITY_ENDPOINT: "tcp://127.0.0.1:1",
            AGENTHUB_ACTIVITY_TOKEN: "token",
        },
    )

    assert exit_code == 0
    assert output.getvalue() == "{}\n"


async def test_receiver_start_failure_leaves_codex_launch_unchanged(
    tmp_path,
    monkeypatch,
) -> None:
    harness = AgentHarness(
        id="codex",
        display_name="Codex",
        command=("codex",),
        scroll=None,
    )
    app = AgentHubApp(agent_harnesses={harness.id: harness})
    session = app.session_manager.create(
        name="Codex",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=harness,
    )
    terminal = session.terminal
    assert terminal is not None

    async def fail_start(_receiver) -> None:
        raise OSError("loopback unavailable")

    monkeypatch.setattr(ActivityReceiver, "start", fail_start)

    tracking_ready = await app._prepare_activity_tracking(session, terminal)

    assert tracking_ready is False
    assert terminal.child_command == harness.command
    assert app._activity_receiver is None


async def test_codex_hook_updates_its_agenthub_session_end_to_end(
    tmp_path,
    monkeypatch,
) -> None:
    harness = AgentHarness(
        id="codex",
        display_name="Codex",
        command=("codex",),
        scroll=None,
    )
    app = AgentHubApp(agent_harnesses={harness.id: harness})
    session = app.session_manager.create(
        name="Codex",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=harness,
    )
    monkeypatch.setattr(app, "_refresh_sidebar", lambda: None)
    terminal = session.terminal
    assert terminal is not None

    tracking_ready = await app._prepare_activity_tracking(session, terminal)
    assert tracking_ready is True
    app._initialize_mounted_activity(session)
    assert session.activity is AgentActivity.IDLE
    registration = app._activity_registrations[session.id]
    try:
        await _forward_event(registration.environment, "UserPromptSubmit")
        for _ in range(20):
            if session.activity is AgentActivity.WORKING:
                break
            await asyncio.sleep(0.01)

        assert session.activity is AgentActivity.WORKING
    finally:
        receiver = app._activity_receiver
        assert receiver is not None
        await receiver.close()
