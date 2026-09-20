"""Tests for provider-neutral desktop activity notifications."""

import pytest

from agenthub.activity import AgentActivity
from agenthub.notifications import (
    DesktopNotification,
    LinuxDesktopNotificationBackend,
    notification_for_activity_transition,
)
from agenthub.notifications import backend as backend_module


@pytest.mark.parametrize(
    ("activity", "expected_title"),
    [
        (AgentActivity.NEEDS_INPUT, "Codex needs input"),
        (AgentActivity.DONE, "Codex finished"),
    ],
)
def test_attention_transition_builds_provider_neutral_notification(
    activity: AgentActivity,
    expected_title: str,
) -> None:
    notification = notification_for_activity_transition(
        AgentActivity.WORKING,
        activity,
        harness_name="Codex",
        session_title="Refactor authentication",
        is_loaded_agent=True,
    )

    assert notification == DesktopNotification(
        title=expected_title,
        message="Refactor authentication",
    )


@pytest.mark.parametrize(
    ("previous", "current"),
    [
        (AgentActivity.UNKNOWN, AgentActivity.UNKNOWN),
        (AgentActivity.UNKNOWN, AgentActivity.IDLE),
        (AgentActivity.IDLE, AgentActivity.WORKING),
        (AgentActivity.NEEDS_INPUT, AgentActivity.NEEDS_INPUT),
        (AgentActivity.DONE, AgentActivity.DONE),
    ],
)
def test_non_attention_or_repeated_transition_does_not_notify(
    previous: AgentActivity,
    current: AgentActivity,
) -> None:
    assert (
        notification_for_activity_transition(
            previous,
            current,
            harness_name="Devin",
            session_title="Session",
            is_loaded_agent=True,
        )
        is None
    )


def test_unloaded_agent_does_not_notify() -> None:
    assert (
        notification_for_activity_transition(
            AgentActivity.WORKING,
            AgentActivity.DONE,
            harness_name="OpenCode",
            session_title="Session",
            is_loaded_agent=False,
        )
        is None
    )


async def test_linux_backend_runs_notification_and_standard_sound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []

    async def record(command: tuple[str, ...]) -> None:
        commands.append(command)

    monkeypatch.setattr(backend_module, "_run_command_best_effort", record)
    backend = LinuxDesktopNotificationBackend(
        notification_command=("notify-send",),
        sound_command=("play-standard-sound",),
    )

    await backend.send(DesktopNotification("Codex finished", "Auth work"))

    assert commands == [
        (
            "notify-send",
            "--app-name=AgentHub",
            "--icon=dialog-information",
            "--hint=boolean:suppress-sound:true",
            "Codex finished",
            "Auth work",
        ),
        ("play-standard-sound",),
    ]


async def test_linux_backend_contains_independent_command_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def fail_once(command: tuple[str, ...]) -> None:
        nonlocal calls
        calls += 1
        if command[0] == "notify-send":
            raise OSError("desktop unavailable")

    monkeypatch.setattr(backend_module, "_run_command_best_effort", fail_once)
    backend = LinuxDesktopNotificationBackend(
        notification_command=("notify-send",),
        sound_command=("play-standard-sound",),
    )

    await backend.send(DesktopNotification("Agent finished", "Session"))

    assert calls == 2
