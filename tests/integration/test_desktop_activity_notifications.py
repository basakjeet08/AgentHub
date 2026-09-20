"""Integration coverage for activity transitions and desktop delivery policy."""

from pathlib import Path

from agenthub.activity import AgentActivity, AgentActivityEvent, AgentActivityEventKind
from agenthub.app import AgentHubApp
from agenthub.harnesses import AgentHarness
from agenthub.notifications import DesktopNotification
from agenthub.sessions import SessionKind


class RecordingNotificationBackend:
    """Capture desktop notifications without touching the test desktop."""

    def __init__(self) -> None:
        self.notifications: list[DesktopNotification] = []

    async def send(self, notification: DesktopNotification) -> None:
        self.notifications.append(notification)


class FailingNotificationBackend:
    """Represent a desktop service failure after delivery is scheduled."""

    def __init__(self) -> None:
        self.attempts = 0

    async def send(self, notification: DesktopNotification) -> None:
        self.attempts += 1
        raise RuntimeError("desktop service unavailable")


async def test_all_loaded_attention_transitions_notify_once_even_when_focused(
    sleeping_harness: AgentHarness,
) -> None:
    backend = RecordingNotificationBackend()
    app = AgentHubApp(
        native_session_adapters={},
        desktop_notification_backend=backend,
    )
    background = app.session_manager.create(
        name="Background task",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    active = app.session_manager.create(
        name="Visible task",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        assert app.app_focus is True
        app._on_activity_event(
            AgentActivityEvent(background.id, AgentActivityEventKind.PROMPT_SUBMITTED)
        )
        app._on_activity_event(
            AgentActivityEvent(background.id, AgentActivityEventKind.PERMISSION_REQUESTED)
        )
        app._on_activity_event(
            AgentActivityEvent(background.id, AgentActivityEventKind.PERMISSION_REQUESTED)
        )
        app._on_activity_event(
            AgentActivityEvent(background.id, AgentActivityEventKind.TURN_COMPLETED)
        )
        app._on_activity_event(
            AgentActivityEvent(background.id, AgentActivityEventKind.TURN_COMPLETED)
        )

        app._on_activity_event(
            AgentActivityEvent(active.id, AgentActivityEventKind.PROMPT_SUBMITTED)
        )
        app._on_activity_event(
            AgentActivityEvent(active.id, AgentActivityEventKind.PERMISSION_REQUESTED)
        )
        app._on_activity_event(AgentActivityEvent(active.id, AgentActivityEventKind.TURN_COMPLETED))
        await pilot.pause()

        assert background.activity is AgentActivity.DONE
        assert active.activity is AgentActivity.DONE
        assert backend.notifications == [
            DesktopNotification(
                title="Test Sleeper needs input",
                message="Background task",
            ),
            DesktopNotification(
                title="Test Sleeper finished",
                message="Background task",
            ),
            DesktopNotification(
                title="Test Sleeper needs input",
                message="Visible task",
            ),
            DesktopNotification(
                title="Test Sleeper finished",
                message="Visible task",
            ),
        ]


async def test_active_agent_notifies_when_application_is_not_focused(
    sleeping_harness: AgentHarness,
) -> None:
    backend = RecordingNotificationBackend()
    app = AgentHubApp(
        native_session_adapters={},
        desktop_notification_backend=backend,
    )
    session = app.session_manager.create(
        name="Background window task",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        app.app_focus = False
        app._on_activity_event(
            AgentActivityEvent(session.id, AgentActivityEventKind.PROMPT_SUBMITTED)
        )
        app._on_activity_event(
            AgentActivityEvent(session.id, AgentActivityEventKind.TURN_COMPLETED)
        )
        await pilot.pause()

        assert backend.notifications == [
            DesktopNotification(
                title="Test Sleeper finished",
                message="Background window task",
            )
        ]


async def test_backend_failure_does_not_affect_activity_or_application(
    sleeping_harness: AgentHarness,
) -> None:
    backend = FailingNotificationBackend()
    app = AgentHubApp(
        native_session_adapters={},
        desktop_notification_backend=backend,
    )
    background = app.session_manager.create(
        name="Background task",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )
    app.session_manager.create(
        name="Visible task",
        kind=SessionKind.AGENT,
        cwd=Path.cwd(),
        harness=sleeping_harness,
    )

    async with app.run_test() as pilot:
        app._on_activity_event(
            AgentActivityEvent(background.id, AgentActivityEventKind.PROMPT_SUBMITTED)
        )
        app._on_activity_event(
            AgentActivityEvent(background.id, AgentActivityEventKind.TURN_COMPLETED)
        )
        await pilot.pause()

        assert background.activity is AgentActivity.DONE
        assert backend.attempts == 1
        assert not app._desktop_notification_tasks
