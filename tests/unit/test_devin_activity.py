"""Tests for Devin activity normalization, forwarding, and launch setup."""

import asyncio
import io
import json
import stat
from collections.abc import Mapping
from pathlib import Path

import pytest

from agenthub.activity import (
    AGENTHUB_ACTIVITY_ENDPOINT,
    AGENTHUB_ACTIVITY_TOKEN,
    AGENTHUB_SESSION_ID,
    ActivityReceiver,
    ActivityRegistration,
    AgentActivity,
    AgentActivityEvent,
    AgentActivityEventKind,
    normalize_devin_activity,
    prepare_devin_activity_launch,
    run_devin_activity_hook,
)
from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.sessions import AgentSession, SessionKind


@pytest.mark.parametrize(
    ("provider_event", "expected"),
    [
        ("UserPromptSubmit", AgentActivityEventKind.PROMPT_SUBMITTED),
        ("PreToolUse", AgentActivityEventKind.TOOL_STARTED),
        ("PermissionRequest", AgentActivityEventKind.PERMISSION_REQUESTED),
        ("PostToolUse", AgentActivityEventKind.TOOL_FINISHED),
        ("Stop", AgentActivityEventKind.TURN_STOP_REQUESTED),
    ],
)
def test_devin_normalizer_maps_turn_events(
    provider_event: str,
    expected: AgentActivityEventKind,
) -> None:
    event = normalize_devin_activity(
        "logical-session",
        {"hook_event_name": provider_event, "prompt_id": "prompt-1"},
    )

    assert event is not None
    assert event.session_id == "logical-session"
    assert event.kind is expected
    assert event.scope_id == "prompt-1"


def test_devin_normalizer_maps_session_start_without_prompt() -> None:
    event = normalize_devin_activity(
        "logical-session",
        {"hook_event_name": "SessionStart", "source": "startup"},
    )

    assert event is not None
    assert event.kind is AgentActivityEventKind.SESSION_STARTED
    assert event.scope_id is None


def test_devin_normalizer_maps_question_tool_to_input_requested() -> None:
    event = normalize_devin_activity(
        "logical-session",
        {
            "hook_event_name": "PreToolUse",
            "prompt_id": "prompt-1",
            "tool_name": "ask_user_question",
            "tool_input": {"questions": []},
        },
    )

    assert event is not None
    assert event.kind is AgentActivityEventKind.INPUT_REQUESTED
    assert event.scope_id == "prompt-1"


@pytest.mark.parametrize(
    "payload",
    [
        {"hook_event_name": "SessionEnd"},
        {"hook_event_name": "PostCompaction", "prompt_id": "prompt-1"},
        {"hook_event_name": "FutureEvent", "prompt_id": "prompt-1"},
        {"hook_event_name": "Stop"},
        {"hook_event_name": "Stop", "prompt_id": ""},
        {},
        [],
    ],
)
def test_devin_normalizer_ignores_non_activity_events(payload: object) -> None:
    assert normalize_devin_activity("logical-session", payload) is None


def test_devin_launch_merges_user_config_and_existing_hooks(tmp_path: Path) -> None:
    config_home = tmp_path / "config"
    config_path = config_home / "devin" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        """
        {
          // Comments and URL-like strings are valid in Devin config.
          "agent": {"model": "test-model"},
          "proxy": {"url": "https://proxy.example.test/path//value"},
          "hooks": {
            "PreToolUse": [{"matcher": "exec", "hooks": []}]
          }
        }
        """,
        encoding="utf-8",
    )

    launch = prepare_devin_activity_launch(
        ("devin", "--resume", "native-id"),
        environment={"XDG_CONFIG_HOME": str(config_home)},
    )
    try:
        assert launch.command == (
            "devin",
            "--config",
            str(launch.config_path),
            "--resume",
            "native-id",
        )
        merged = json.loads(launch.config_path.read_text(encoding="utf-8"))
        assert merged["agent"] == {"model": "test-model"}
        assert merged["proxy"]["url"] == "https://proxy.example.test/path//value"
        assert merged["hooks"]["PreToolUse"][0] == {
            "matcher": "exec",
            "hooks": [],
        }
        for event_name in (
            "SessionStart",
            "UserPromptSubmit",
            "PreToolUse",
            "PermissionRequest",
            "PostToolUse",
            "Stop",
        ):
            observer = merged["hooks"][event_name][-1]
            assert observer["matcher"] == ""
            assert observer["hooks"][0]["type"] == "command"
            assert observer["hooks"][0]["timeout"] == 1
            assert observer["hooks"][0]["command"].endswith(
                "-m agenthub.main activity-hook devin"
            )
        assert stat.S_IMODE(launch.config_path.stat().st_mode) == 0o600
    finally:
        launch.config_path.unlink(missing_ok=True)


def test_devin_launch_preserves_an_explicit_config_option(tmp_path: Path) -> None:
    source = tmp_path / "custom.json"
    source.write_text('{"theme_mode":"nocolor"}', encoding="utf-8")

    launch = prepare_devin_activity_launch(
        ("devin", "--resume", "native-id", "--config", str(source))
    )
    try:
        assert launch.command.count("--config") == 1
        assert launch.command[1:3] == ("--config", str(launch.config_path))
        assert launch.command[-2:] == ("--resume", "native-id")
        merged = json.loads(launch.config_path.read_text(encoding="utf-8"))
        assert merged["theme_mode"] == "nocolor"
    finally:
        launch.config_path.unlink(missing_ok=True)


async def _forward_event(
    environment: Mapping[str, str],
    event_name: str,
    prompt_id: str | None = "prompt-1",
    *,
    tool_name: str | None = None,
) -> str:
    payload: dict[str, str] = {"hook_event_name": event_name}
    if prompt_id is not None:
        payload["prompt_id"] = prompt_id
    if tool_name is not None:
        payload["tool_name"] = tool_name
    output = io.StringIO()
    exit_code = await asyncio.to_thread(
        run_devin_activity_hook,
        input_stream=io.BytesIO(json.dumps(payload).encode("utf-8")),
        output_stream=output,
        environment=environment,
    )
    assert exit_code == 0
    return output.getvalue()


async def test_devin_receiver_routes_exact_session_and_preserves_prompt_id() -> None:
    received = []
    receiver = ActivityReceiver(received.append)
    await receiver.start()
    first = receiver.register("first-session", "devin")
    second = receiver.register("second-session", "devin")
    try:
        crossed_environment = {
            **first.environment,
            AGENTHUB_SESSION_ID: second.session_id,
        }
        assert await _forward_event(crossed_environment, "UserPromptSubmit") == "{}\n"
        await asyncio.sleep(0.01)
        assert received == []

        await _forward_event(first.environment, "PreToolUse", "prompt-a")
        await _forward_event(second.environment, "PermissionRequest", "prompt-b")
        for _ in range(20):
            if len(received) == 2:
                break
            await asyncio.sleep(0.01)

        assert [(event.session_id, event.kind, event.scope_id) for event in received] == [
            ("first-session", AgentActivityEventKind.TOOL_STARTED, "prompt-a"),
            (
                "second-session",
                AgentActivityEventKind.PERMISSION_REQUESTED,
                "prompt-b",
            ),
        ]
    finally:
        await receiver.close()


def test_devin_hook_receiver_failure_is_neutral() -> None:
    output = io.StringIO()

    exit_code = run_devin_activity_hook(
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


def _app_with_observed_devin(tmp_path: Path) -> tuple[AgentHubApp, AgentSession]:
    harness = AgentHarness(
        id="devin",
        display_name="Devin",
        command=("devin",),
        scroll=None,
    )
    app = AgentHubApp(agent_harnesses={harness.id: harness})
    session = app.session_manager.create(
        name="Devin",
        kind=SessionKind.AGENT,
        cwd=tmp_path,
        harness=harness,
    )
    app._activity_registrations[session.id] = ActivityRegistration(
        session_id=session.id,
        provider="devin",
        token="test-token",
        endpoint="tcp://127.0.0.1:1",
    )
    return app, session


def test_devin_ctrl_c_observation_clears_active_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, session = _app_with_observed_devin(tmp_path)
    monkeypatch.setattr(app, "_refresh_sidebar", lambda: None)
    app.session_manager.apply_activity_event(
        AgentActivityEvent(
            session.id,
            AgentActivityEventKind.PROMPT_SUBMITTED,
            scope_id="prompt-a",
        )
    )

    app._on_devin_terminal_key(session.id, "ctrl+c")

    assert session.activity is AgentActivity.IDLE


def test_devin_single_escape_observation_clears_working_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app, session = _app_with_observed_devin(tmp_path)
    monkeypatch.setattr(app, "_refresh_sidebar", lambda: None)
    app.session_manager.apply_activity_event(
        AgentActivityEvent(
            session.id,
            AgentActivityEventKind.PROMPT_SUBMITTED,
            scope_id="prompt-a",
        )
    )

    app._on_devin_terminal_key(session.id, "escape")
    assert session.activity is AgentActivity.IDLE


@pytest.mark.parametrize(
    "request_kind",
    [
        AgentActivityEventKind.PERMISSION_REQUESTED,
        AgentActivityEventKind.INPUT_REQUESTED,
    ],
)
def test_devin_single_escape_observation_clears_waiting_prompt(
    tmp_path: Path,
    monkeypatch,
    request_kind: AgentActivityEventKind,
) -> None:
    app, session = _app_with_observed_devin(tmp_path)
    monkeypatch.setattr(app, "_refresh_sidebar", lambda: None)
    app.session_manager.apply_activity_event(
        AgentActivityEvent(
            session.id,
            AgentActivityEventKind.PROMPT_SUBMITTED,
            scope_id="prompt-a",
        )
    )
    app.session_manager.apply_activity_event(
        AgentActivityEvent(
            session.id,
            request_kind,
            scope_id="prompt-a",
        )
    )

    app._on_devin_terminal_key(session.id, "escape")
    assert session.activity is AgentActivity.IDLE


async def test_invalid_devin_config_does_not_change_provider_launch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_home = tmp_path / "config"
    config_path = config_home / "devin" / "config.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("not valid JSON", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    harness = AgentHarness(
        id="devin",
        display_name="Devin",
        command=("devin",),
        scroll=None,
    )
    app = AgentHubApp(agent_harnesses={harness.id: harness})
    session = app.session_manager.create(
        name="Devin",
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
    assert session.id not in app._activity_artifacts
    receiver = app._activity_receiver
    assert receiver is not None
    await receiver.close()


async def test_devin_hooks_update_sidebar_activity_end_to_end(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    harness = AgentHarness(
        id="devin",
        display_name="Devin",
        command=("devin",),
        scroll=None,
    )
    app = AgentHubApp(agent_harnesses={harness.id: harness})
    session = app.session_manager.create(
        name="Devin",
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
    config_path = app._activity_artifacts[session.id][0]
    assert config_path.exists()
    try:
        await _forward_event(registration.environment, "UserPromptSubmit", "prompt-a")
        for _ in range(20):
            if session.activity is AgentActivity.WORKING:
                break
            await asyncio.sleep(0.01)
        assert session.activity is AgentActivity.WORKING

        await _forward_event(registration.environment, "PermissionRequest", "prompt-a")
        for _ in range(20):
            if session.activity is AgentActivity.NEEDS_INPUT:
                break
            await asyncio.sleep(0.01)
        assert session.activity is AgentActivity.NEEDS_INPUT

        await _forward_event(registration.environment, "PostToolUse", "prompt-a")
        for _ in range(20):
            if session.activity is AgentActivity.WORKING:
                break
            await asyncio.sleep(0.01)
        assert session.activity is AgentActivity.WORKING

        await _forward_event(
            registration.environment,
            "PreToolUse",
            "prompt-a",
            tool_name="ask_user_question",
        )
        for _ in range(20):
            if session.activity is AgentActivity.NEEDS_INPUT:
                break
            await asyncio.sleep(0.01)
        assert session.activity is AgentActivity.NEEDS_INPUT

        await _forward_event(
            registration.environment,
            "PostToolUse",
            "prompt-a",
            tool_name="ask_user_question",
        )
        for _ in range(20):
            if session.activity is AgentActivity.WORKING:
                break
            await asyncio.sleep(0.01)
        assert session.activity is AgentActivity.WORKING

        await _forward_event(registration.environment, "Stop", "prompt-a")
        for _ in range(20):
            if session.activity is AgentActivity.DONE:
                break
            await asyncio.sleep(0.01)
        assert session.activity is AgentActivity.DONE

        # Another Stop hook may block Devin's stop request. Work continuing in
        # the same prompt must move the sidebar out of the provisional Done state.
        await _forward_event(registration.environment, "PreToolUse", "prompt-a")
        for _ in range(20):
            if session.activity is AgentActivity.WORKING:
                break
            await asyncio.sleep(0.01)
        assert session.activity is AgentActivity.WORKING

        await _forward_event(registration.environment, "Stop", "prompt-a")
        for _ in range(20):
            if session.activity is AgentActivity.DONE:
                break
            await asyncio.sleep(0.01)
        assert session.activity is AgentActivity.DONE
    finally:
        app._revoke_activity_tracking(session.id)
        assert not config_path.exists()
        receiver = app._activity_receiver
        assert receiver is not None
        await receiver.close()
