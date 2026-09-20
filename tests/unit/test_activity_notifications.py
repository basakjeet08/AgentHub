"""Tests for provider-neutral desktop activity notifications."""

import asyncio

import pytest

from agenthub.activity import AgentActivity
from agenthub.notifications import (
    DesktopNotification,
    DesktopNotificationService,
)
from agenthub.notifications.backends import LinuxDesktopNotificationBackend
from agenthub.notifications.backends import factory as backend_factory_module
from agenthub.notifications.backends import linux as linux_backend_module


@pytest.mark.parametrize(
    ("activity", "expected_title"),
    [
        (AgentActivity.NEEDS_INPUT, "Codex needs input"),
        (AgentActivity.DONE, "Codex finished"),
    ],
)
async def test_attention_transition_builds_provider_neutral_notification(
    activity: AgentActivity,
    expected_title: str,
) -> None:
    notifications: list[DesktopNotification] = []

    class RecordingBackend:
        async def send(self, notification: DesktopNotification) -> None:
            notifications.append(notification)

    service = DesktopNotificationService(RecordingBackend())
    service.handle_activity_transition(
        AgentActivity.WORKING,
        activity,
        harness_name="Codex",
        session_title="Refactor authentication",
        is_loaded_agent=True,
    )
    await asyncio.sleep(0)
    await service.shutdown()

    assert notifications == [
        DesktopNotification(
            title=expected_title,
            message="Refactor authentication",
        )
    ]


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
async def test_non_attention_or_repeated_transition_does_not_notify(
    previous: AgentActivity,
    current: AgentActivity,
) -> None:
    notifications: list[DesktopNotification] = []

    class RecordingBackend:
        async def send(self, notification: DesktopNotification) -> None:
            notifications.append(notification)

    service = DesktopNotificationService(RecordingBackend())
    service.handle_activity_transition(
        previous,
        current,
        harness_name="Devin",
        session_title="Session",
        is_loaded_agent=True,
    )
    await asyncio.sleep(0)
    await service.shutdown()

    assert not notifications


async def test_unloaded_agent_does_not_notify() -> None:
    notifications: list[DesktopNotification] = []

    class RecordingBackend:
        async def send(self, notification: DesktopNotification) -> None:
            notifications.append(notification)

    service = DesktopNotificationService(RecordingBackend())
    service.handle_activity_transition(
        AgentActivity.WORKING,
        AgentActivity.DONE,
        harness_name="OpenCode",
        session_title="Session",
        is_loaded_agent=False,
    )
    await asyncio.sleep(0)
    await service.shutdown()

    assert not notifications


def test_unsupported_platform_has_no_desktop_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backend_factory_module.sys, "platform", "darwin")

    assert backend_factory_module.create_desktop_notification_backend() is None


def test_linux_platform_builds_linux_desktop_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backend_factory_module.sys, "platform", "linux")
    monkeypatch.setattr(
        linux_backend_module.shutil,
        "which",
        lambda command: "/usr/bin/notify-send" if command == "notify-send" else None,
    )
    monkeypatch.setattr(
        linux_backend_module,
        "_linux_sound_command",
        lambda: ("canberra-gtk-play", "--id=message-new-instant"),
    )

    backend = backend_factory_module.create_desktop_notification_backend()

    assert isinstance(backend, LinuxDesktopNotificationBackend)
    assert backend._notification_command == ("/usr/bin/notify-send",)
    assert backend._sound_command == (
        "canberra-gtk-play",
        "--id=message-new-instant",
    )


async def test_notification_service_contains_backend_failure() -> None:
    class FailingBackend:
        def __init__(self) -> None:
            self.attempted = asyncio.Event()

        async def send(self, notification: DesktopNotification) -> None:
            self.attempted.set()
            raise RuntimeError("desktop unavailable")

    backend = FailingBackend()
    service = DesktopNotificationService(backend)

    service.schedule(DesktopNotification("Codex finished", "Auth work"))
    await backend.attempted.wait()
    await service.shutdown()


async def test_notification_service_cancels_delivery_during_shutdown() -> None:
    class BlockingBackend:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.cancelled = asyncio.Event()

        async def send(self, notification: DesktopNotification) -> None:
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise

    backend = BlockingBackend()
    service = DesktopNotificationService(backend)

    service.schedule(DesktopNotification("Agent finished", "Session"))
    await backend.started.wait()
    await service.shutdown()

    assert backend.cancelled.is_set()


async def test_linux_backend_runs_notification_and_standard_sound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []

    async def record(command: tuple[str, ...]) -> None:
        commands.append(command)

    monkeypatch.setattr(linux_backend_module, "_run_command_best_effort", record)
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

    monkeypatch.setattr(linux_backend_module, "_run_command_best_effort", fail_once)
    backend = LinuxDesktopNotificationBackend(
        notification_command=("notify-send",),
        sound_command=("play-standard-sound",),
    )

    await backend.send(DesktopNotification("Agent finished", "Session"))

    assert calls == 2
