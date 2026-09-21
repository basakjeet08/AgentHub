"""Provider-neutral native-session service boundary."""

from collections.abc import Mapping

from .adapter import (
    NativeSessionAdapter,
    NativeSessionDeletionError,
    NativeSessionDiscoveryError,
    NativeSessionResumeError,
)
from .model import LaunchSpec, NativeSession


class NativeSessionService:
    """Route native-session operations through an injected adapter registry."""

    def __init__(self, adapter_registry: Mapping[str, NativeSessionAdapter]) -> None:
        self._adapters = dict(adapter_registry)

    @property
    def harness_ids(self) -> tuple[str, ...]:
        """Return registered provider IDs in registry order."""

        return tuple(self._adapters)

    def delete_capability(self, harness_id: str) -> bool | None:
        """Return deletion support, or ``None`` when no adapter is registered."""

        adapter = self._adapters.get(harness_id)
        return None if adapter is None else adapter.supports_delete

    def discover(self, harness_id: str) -> tuple[NativeSession, ...]:
        """Discover native conversations for one registered provider."""

        try:
            return self._adapters[harness_id].discover()
        except KeyError as error:
            raise NativeSessionDiscoveryError(
                f"No native-session adapter is registered for {harness_id}."
            ) from error

    async def resume(self, session: NativeSession) -> LaunchSpec:
        """Construct an exact-ID launch for one native conversation."""

        try:
            adapter = self._adapters[session.harness_id]
        except KeyError as error:
            raise NativeSessionResumeError(
                f"No native-session adapter is registered for {session.harness_id}."
            ) from error
        return await adapter.resume(session)

    async def delete(self, session: NativeSession) -> None:
        """Delete one native conversation through its registered provider."""

        try:
            adapter = self._adapters[session.harness_id]
        except KeyError as error:
            raise NativeSessionDeletionError(
                f"No native-session adapter is registered for {session.harness_id}."
            ) from error
        await adapter.delete(session)
