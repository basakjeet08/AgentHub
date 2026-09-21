"""Tests for OpenCode activity normalization and plugin integration."""

import asyncio
import json
import os
import shutil
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from agenthub.activity import (
    AGENTHUB_ACTIVITY_ENDPOINT,
    AGENTHUB_ACTIVITY_TOKEN,
    AGENTHUB_SESSION_ID,
    ActivityReceiver,
    AgentActivity,
    AgentActivityEvent,
    AgentActivityEventKind,
)
from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.providers.opencode.activity_adapter import (
    AGENTHUB_OPENCODE_SESSION_ID,
    OPENCODE_CONFIG_CONTENT,
    normalize_opencode_activity,
    opencode_activity_environment,
)
from agenthub.sessions import SessionKind


@pytest.mark.parametrize(
    ("provider_event", "expected"),
    [
        ("session.execution.started", AgentActivityEventKind.PROMPT_SUBMITTED),
        ("permission.asked", AgentActivityEventKind.PERMISSION_REQUESTED),
        ("permission.v2.asked", AgentActivityEventKind.PERMISSION_REQUESTED),
        ("permission.replied", AgentActivityEventKind.INPUT_RESOLVED),
        ("permission.v2.replied", AgentActivityEventKind.INPUT_RESOLVED),
        ("form.created", AgentActivityEventKind.INPUT_REQUESTED),
        ("form.replied", AgentActivityEventKind.INPUT_RESOLVED),
        ("form.cancelled", AgentActivityEventKind.INPUT_RESOLVED),
        ("question.asked", AgentActivityEventKind.INPUT_REQUESTED),
        ("question.replied", AgentActivityEventKind.INPUT_RESOLVED),
        ("question.rejected", AgentActivityEventKind.INPUT_RESOLVED),
        ("question.v2.asked", AgentActivityEventKind.INPUT_REQUESTED),
        ("question.v2.replied", AgentActivityEventKind.INPUT_RESOLVED),
        ("question.v2.rejected", AgentActivityEventKind.INPUT_RESOLVED),
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


def test_opencode_plugin_ready_does_not_require_an_execution_scope() -> None:
    event = normalize_opencode_activity(
        "logical-session",
        {"type": "agenthub.plugin.ready"},
    )

    assert event == AgentActivityEvent(
        session_id="logical-session",
        kind=AgentActivityEventKind.SESSION_STARTED,
    )


def test_opencode_environment_preserves_inline_config_and_plugins(tmp_path: Path) -> None:
    plugin = tmp_path / "activity.js"
    original = json.dumps(
        {
            "model": "test/model",
            "plugin": ["existing-v1-plugin"],
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
    assert merged["plugin"] == ["existing-v1-plugin", str(plugin.resolve())]
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


def test_opencode_environment_uses_the_packaged_compatibility_plugin() -> None:
    overrides = opencode_activity_environment(environment={})
    config = json.loads(overrides[OPENCODE_CONFIG_CONTENT])
    plugin_path = Path(config["plugins"][-1])
    source = plugin_path.read_text(encoding="utf-8")

    assert plugin_path.name == "activity_plugin.js"
    assert config["plugin"][-1] == str(plugin_path)
    assert "ctx.event.subscribe" in source
    assert "server" in source
    assert "session.status" in source
    assert "session.execution.started" in source
    assert "tool.execute.before" not in source


async def test_packaged_plugin_tracks_all_concurrent_v1_input_blockers() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required to execute the packaged OpenCode plugin")

    received: list[AgentActivityEvent] = []
    receiver = ActivityReceiver(received.append)
    await receiver.start()
    registration = receiver.register(
        "logical-session", "opencode", normalize_opencode_activity
    )
    plugin_path = (
        Path(__file__).parents[2]
        / "src/agenthub/providers/opencode/activity_plugin.js"
    )
    events = [
        {
            "type": "session.status",
            "properties": {"sessionID": "root", "status": {"type": "busy"}},
        },
        {
            "type": "permission.asked",
            "properties": {"id": "permission-1", "sessionID": "root"},
        },
        {
            "type": "session.created",
            "properties": {"info": {"id": "child", "parentID": "root"}},
        },
        {
            "type": "question.asked",
            "properties": {"id": "question-1", "sessionID": "child"},
        },
        {
            "type": "permission.replied",
            "properties": {"requestID": "permission-1", "sessionID": "root"},
        },
        {
            "type": "question.replied",
            "properties": {"requestID": "question-1", "sessionID": "child"},
        },
        {"type": "session.idle", "properties": {"sessionID": "root"}},
    ]
    script = """
import { readFile } from "node:fs/promises"
const source = await readFile(process.argv[1], "utf8")
const url = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
const plugin = (await import(url)).default
const hooks = await plugin.server()
for (const event of JSON.parse(process.argv[2])) await hooks.event({ event })
await new Promise((resolve) => setTimeout(resolve, 500))
"""
    environment = os.environ.copy()
    environment.update(registration.environment)
    environment[AGENTHUB_OPENCODE_SESSION_ID] = "root"
    try:
        process = await asyncio.create_subprocess_exec(
            node,
            "--input-type=module",
            "--eval",
            script,
            str(plugin_path),
            json.dumps(events),
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        assert process.returncode == 0, (stdout + stderr).decode(errors="replace")
        for _ in range(50):
            if len(received) >= 5:
                break
            await asyncio.sleep(0.01)
    finally:
        await receiver.close()

    assert [event.kind for event in received] == [
        AgentActivityEventKind.SESSION_STARTED,
        AgentActivityEventKind.PROMPT_SUBMITTED,
        AgentActivityEventKind.PERMISSION_REQUESTED,
        AgentActivityEventKind.INPUT_RESOLVED,
        AgentActivityEventKind.TURN_COMPLETED,
    ]
    assert received[2].scope_id == "root:1"
    assert received[3].scope_id == "root:1"


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


async def test_opencode_events_update_sidebar_activity_end_to_end(
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
    assert session.activity is AgentActivity.UNKNOWN
    registration = app._activity_registrations[session.id]
    environment = terminal._environment_overrides
    assert environment[AGENTHUB_OPENCODE_SESSION_ID] == "native-session"
    assert OPENCODE_CONFIG_CONTENT in environment
    try:
        await _send_event(registration.environment, "agenthub.plugin.ready", "")
        await _wait_for_activity(session, AgentActivity.IDLE)

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
