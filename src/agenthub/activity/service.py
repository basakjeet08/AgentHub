"""Application-facing activity setup and routing service."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from .adapter import ActivityAdapter, ActivityLaunch
from .model import AgentActivity, AgentActivityEvent, AgentActivityEventKind
from .receiver import ActivityReceiver, ActivityRegistration


class ActivityService:
    """Route generic activity operations to registered provider adapters."""

    def __init__(
        self,
        adapter_registry: Mapping[str, ActivityAdapter],
        on_event: Callable[[AgentActivityEvent], None],
    ) -> None:
        self._adapters = dict(adapter_registry)
        self._on_event = on_event
        self._receiver: ActivityReceiver | None = None
        self._registrations: dict[str, ActivityRegistration] = {}
        self._adapters_by_session: dict[str, ActivityAdapter] = {}
        self._artifacts: dict[str, tuple[Path, ...]] = {}
        self._reports_session_started: dict[str, bool] = {}

    @property
    def receiver(self) -> ActivityReceiver | None:
        """Return the shared receiver, if it has been started."""

        return self._receiver

    @property
    def registrations(self) -> Mapping[str, ActivityRegistration]:
        """Expose active routes for diagnostics and compatibility tests."""

        return self._registrations

    @property
    def artifacts(self) -> Mapping[str, tuple[Path, ...]]:
        """Expose active cleanup artifacts for application diagnostics."""

        return self._artifacts

    async def prepare(
        self,
        session_id: str,
        provider: str,
        command: Sequence[str],
        *,
        native_session_id: str | None = None,
    ) -> ActivityLaunch | None:
        """Prepare one provider launch, returning ``None`` when unsupported."""

        adapter = self._adapters.get(provider)
        if adapter is None or not adapter.matches_command(command):
            return None
        if self._receiver is None:
            self._receiver = ActivityReceiver(self._on_event)
            try:
                await self._receiver.start()
            except Exception:
                self._receiver = None
                raise
        self.revoke(session_id)
        registration = self._receiver.register(
            session_id,
            provider,
            adapter.create_normalizer(native_session_id),
        )
        try:
            launch = adapter.prepare_launch(
                command,
                native_session_id=native_session_id,
                registration_environment=registration.environment,
            )
        except Exception:
            self._receiver.revoke(registration)
            raise
        self._registrations[session_id] = registration
        self._adapters_by_session[session_id] = adapter
        self._artifacts[session_id] = launch.artifacts
        self._reports_session_started[session_id] = launch.reports_session_started
        return launch

    def initial_event(self, session_id: str) -> AgentActivityEvent | None:
        """Return the initial event for adapters without a readiness handshake."""

        if session_id not in self._adapters_by_session:
            return None
        if self._reports_session_started.get(session_id, False):
            return None
        return AgentActivityEvent(session_id, AgentActivityEventKind.SESSION_STARTED)

    def terminal_key_event(
        self,
        session_id: str,
        key: str,
        *,
        provider: str | None = None,
        activity: AgentActivity,
        input_wait_kind: AgentActivityEventKind | None,
    ) -> AgentActivityEvent | None:
        """Route a forwarded terminal key through the active adapter."""

        adapter = self._adapters_by_session.get(session_id)
        if adapter is None and provider is not None:
            adapter = self._adapters.get(provider)
        if adapter is None:
            return None
        return adapter.terminal_key_event(
            session_id,
            key,
            activity=activity,
            input_wait_kind=input_wait_kind,
        )

    def revoke(self, session_id: str) -> None:
        """Revoke one route and remove provider-created temporary artifacts."""

        registration = self._registrations.pop(session_id, None)
        if registration is not None and self._receiver is not None:
            self._receiver.revoke(registration)
        self._adapters_by_session.pop(session_id, None)
        self._reports_session_started.pop(session_id, None)
        for path in self._artifacts.pop(session_id, ()):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    async def close(self) -> None:
        """Revoke every runtime and close the shared receiver."""

        for session_id in tuple(self._registrations) + tuple(
            session_id for session_id in self._artifacts if session_id not in self._registrations
        ):
            self.revoke(session_id)
        receiver = self._receiver
        self._receiver = None
        if receiver is not None:
            await receiver.close()
