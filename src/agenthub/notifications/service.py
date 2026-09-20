"""Notification policy and best-effort delivery coordination."""

from __future__ import annotations

import asyncio

from agenthub.activity import AgentActivity

from .backend import DesktopNotificationBackend
from .backends import create_desktop_notification_backend
from .model import DesktopNotification


class DesktopNotificationService:
    """Schedule and contain optional desktop notification delivery."""

    def __init__(self, backend: DesktopNotificationBackend | None = None) -> None:
        self._backend = create_desktop_notification_backend() if backend is None else backend
        self._tasks: set[asyncio.Task[None]] = set()

    def schedule_activity_transition(
        self,
        previous: AgentActivity,
        current: AgentActivity,
        *,
        harness_name: str,
        session_title: str,
        is_loaded_agent: bool,
    ) -> None:
        """Schedule desktop attention for a qualifying Agent transition."""

        if previous is current or not is_loaded_agent:
            return

        if current is AgentActivity.NEEDS_INPUT:
            title = f"{harness_name} needs input"
        elif current is AgentActivity.DONE:
            title = f"{harness_name} finished"
        else:
            return

        self.schedule(DesktopNotification(title=title, message=session_title))

    def schedule(self, notification: DesktopNotification) -> None:
        """Deliver one notification outside activity and session control flow."""

        if self._backend is None:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        task = loop.create_task(
            self._deliver(notification),
            name="agenthub-desktop-notification",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _deliver(self, notification: DesktopNotification) -> None:
        """Contain every backend failure at the optional desktop boundary."""

        if self._backend is None:
            return
        try:
            await self._backend.send(notification)
        except Exception:  # noqa: BLE001 - notifications must never affect Agents
            return

    async def shutdown(self) -> None:
        """Cancel outstanding deliveries without surfacing any failure."""

        tasks = tuple(self._tasks)

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
