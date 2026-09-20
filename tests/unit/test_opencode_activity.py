"""Tests for OpenCode V2 activity normalization and plugin integration."""

import asyncio
import json
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from agenthub.activity import (
    AGENTHUB_ACTIVITY_ENDPOINT,
    AGENTHUB_ACTIVITY_TOKEN,
    AGENTHUB_OPENCODE_SESSION_ID,
    AGENTHUB_SESSION_ID,
    OPENCODE_CONFIG_CONTENT,
    AgentActivity,
    AgentActivityEventKind,
    normalize_opencode_activity,
    opencode_activity_environment,
)
from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.sessions import SessionKind


@pytest.mark.parametrize(
    ("provider_event", "expected"),
    [
        ("session.execution.started", AgentActivityEventKind.PROMPT_SUBMITTED),
        ("permission.asked", AgentActivityEventKind.PERMISSION_REQUESTED),
        ("permission.replied", AgentActivityEventKind.INPUT_RESOLVED),
        ("form.created", AgentActivityEventKind.INPUT_REQUESTED),
        ("form.replied", AgentActivityEventKind.INPUT_RESOLVED),
        ("form.cancelled", AgentActivityEventKind.INPUT_RESOLVED),
        ("session.execution.succeeded", AgentActivityEventKind.TURN_COMPLETED),
        ("session.execution.failed", AgentActivityEventKind.TURN_COMPLETED),
        ("session.execution.interrupted", AgentActivityEventKind.INTERRUPTED),
    ],
)
def test_opencode_normalizer_maps_v2_events(
    provider_event: str,
    expected: AgentActivityEventKind,
) -> None:
    event = normalize_opencode_activity(
        "logical-session",
        {
            "type": provider_event,
            "data": {"sessionID": "native-session"},
            "activity_scope_id": "native-session:1",
        },
    )

    assert event is not None
    assert event.session_id == "logical-session"
    assert event.kind is expected
    assert event.scope_id == "native-session:1"


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "session.execution.started"},
        {"type": "session.execution.started", "activity_scope_id": ""},
        {"type": "session.idle", "activity_scope_id": "native-session:1"},
        {"type": "future.event", "activity_scope_id": "native-session:1"},
        {},
        [],
    ],
)
def test_opencode_normalizer_ignores_invalid_or_unknown_events(payload: object) -> None:
    assert normalize_opencode_activity("logical-session", payload) is None


def test_opencode_environment_preserves_inline_config_and_plugins(tmp_path: Path) -> None:
    plugin = tmp_path / "activity.js"
    original = json.dumps(
        {
            "model": "test/model",
            "plugins": ["existing-plugin", {"package": "configured-plugin"}],
        }
    )

    overrides = opencode_activity_environment(
        native_session_id="native-session",
        environment={OPENCODE_CONFIG_CONTENT: original},
        plugin_path=plugin,
    )

    merged = json.loads(overrides[OPENCODE_CONFIG_CONTENT])
    assert merged["model"] == "test/model"
    assert merged["plugins"] == [
        "existing-plugin",
        {"package": "configured-plugin"},
        str(plugin.resolve()),
    ]
    assert overrides[AGENTHUB_OPENCODE_SESSION_ID] == "native-session"
    assert json.loads(original)["plugins"] == [
        "existing-plugin",
        {"package": "configured-plugin"},
    ]


def test_opencode_environment_uses_the_packaged_v2_plugin() -> None:
    overrides = opencode_activity_environment(environment={})
    config = json.loads(overrides[OPENCODE_CONFIG_CONTENT])
    plugin_path = Path(config["plugins"][-1])
    source = plugin_path.read_text(encoding="utf-8")

    assert plugin_path.name == "_opencode_plugin.js"
    assert 'from "@opencode/plugin"' in source
    assert "ctx.event.subscribe" in source
    assert "session.execution.started" in source
    assert "@opencode-ai/plugin" not in source
    assert "tool.execute.before" not in source


async def _send_event(
    environment: Mapping[str, str],
    event_type: str,
    scope_id: str,
) -> None:
    endpoint = urlsplit(environment[AGENTHUB_ACTIVITY_ENDPOINT])
    assert endpoint.hostname == "127.0.0.1"
    assert endpoint.port is not None
    _reader, writer = await asyncio.open_connection(endpoint.hostname, endpoint.port)
    writer.write(
        json.dumps(
            {
                "version": 1,
                "provider": "opencode",
                "session_id": environment[AGENTHUB_SESSION_ID],
                "token": environment[AGENTHUB_ACTIVITY_TOKEN],
                "event": {
                    "type": event_type,
                    "data": {"sessionID": "native-session"},
                    "activity_scope_id": scope_id,
                },
            },
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def _wait_for_activity(session, expected: AgentActivity) -> None:
    for _ in range(20):
        if session.activity is expected:
            return
        await asyncio.sleep(0.01)
    assert session.activity is expected


async def test_opencode_v2_events_update_sidebar_activity_end_to_end(
    tmp_path: Path,
    monkeypatch,
) -> None:
    harness = AgentHarness(
        id="opencode",
        display_name="OpenCode",
        command=("opencode",),
        scroll=None,
    )
    app = AgentHubApp(agent_harnesses={harness.id: harness})
    session = app.session_manager.create(
        name="OpenCode",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=harness,
    )
    session.native_session_id = "native-session"
    monkeypatch.setattr(app, "_refresh_sidebar", lambda: None)
    terminal = session.terminal
    assert terminal is not None

    tracking_ready = await app._prepare_activity_tracking(session, terminal)
    assert tracking_ready is True
    app._initialize_mounted_activity(session)
    assert session.activity is AgentActivity.IDLE
    registration = app._activity_registrations[session.id]
    environment = terminal._environment_overrides
    assert environment[AGENTHUB_OPENCODE_SESSION_ID] == "native-session"
    assert OPENCODE_CONFIG_CONTENT in environment
    try:
        await _send_event(registration.environment, "session.execution.started", "turn-1")
        await _wait_for_activity(session, AgentActivity.WORKING)

        await _send_event(registration.environment, "permission.asked", "turn-1")
        await _wait_for_activity(session, AgentActivity.NEEDS_INPUT)

        await _send_event(registration.environment, "permission.replied", "turn-1")
        await _wait_for_activity(session, AgentActivity.WORKING)

        await _send_event(registration.environment, "form.created", "turn-1")
        await _wait_for_activity(session, AgentActivity.NEEDS_INPUT)

        await _send_event(registration.environment, "form.replied", "turn-1")
        await _wait_for_activity(session, AgentActivity.WORKING)

        await _send_event(registration.environment, "session.execution.succeeded", "turn-1")
        await _wait_for_activity(session, AgentActivity.DONE)

        await _send_event(registration.environment, "permission.asked", "turn-1")
        await asyncio.sleep(0.02)
        assert session.activity is AgentActivity.DONE

        await _send_event(registration.environment, "session.execution.started", "turn-2")
        await _wait_for_activity(session, AgentActivity.WORKING)

        await _send_event(registration.environment, "session.execution.interrupted", "turn-2")
        await _wait_for_activity(session, AgentActivity.IDLE)
    finally:
        receiver = app._activity_receiver
        assert receiver is not None
        await receiver.close()


async def test_invalid_opencode_inline_config_does_not_change_provider_launch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv(OPENCODE_CONFIG_CONTENT, "not valid JSON")
    harness = AgentHarness(
        id="opencode",
        display_name="OpenCode",
        command=("opencode",),
        scroll=None,
    )
    app = AgentHubApp(agent_harnesses={harness.id: harness})
    session = app.session_manager.create(
        name="OpenCode",
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
