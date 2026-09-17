"""Protocol and shared failures for native-session adapters."""

from typing import Protocol

from .model import LaunchSpec, NativeSession


class NativeSessionError(RuntimeError):
    """Base failure raised by a native-session adapter."""


class NativeSessionDiscoveryError(NativeSessionError):
    """A provider's native conversations could not be discovered."""


class NativeSessionResumeError(NativeSessionError):
    """A provider could not construct an exact-session resume launch."""


class NativeSessionDeletionError(NativeSessionError):
    """A provider could not permanently delete a native conversation."""


class NativeSessionDeletionUnavailableError(NativeSessionDeletionError):
    """A provider has no programmatic native-conversation deletion API."""


class NativeSessionAdapter(Protocol):
    """Provider-specific native conversation operations used by AgentHub."""

    harness_id: str

    def discover(self) -> tuple[NativeSession, ...]:
        """Return the provider's existing native conversations.

        Discovery may perform blocking filesystem and SQLite work. Callers are
        responsible for running it outside the application event loop.
        """

    async def resume(self, session: NativeSession) -> LaunchSpec:
        """Return the exact launch needed to resume ``session``."""

    async def delete(self, session: NativeSession) -> None:
        """Permanently delete ``session`` through the native provider."""
