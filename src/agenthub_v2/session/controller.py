"""Application controller for AgentHub session operations."""

from agenthub_v2.provider import DiscoveredSession, ProviderService

from .model import Session
from .store import SessionStore


class SessionController:
    """Application controller for AgentHub session state operations."""

    def __init__(
        self,
        store: SessionStore | None = None,
        providers: ProviderService | None = None,
    ) -> None:
        """Initialize the session controller."""

        self._store = store if store is not None else SessionStore()
        self._providers = providers if providers is not None else ProviderService()

    @staticmethod
    def _from_discovered(discovered: DiscoveredSession) -> Session:
        """Convert a discovered provider session into an AgentHub session."""

        return Session(
            id=f"{discovered.provider_id}:{discovered.provider_session_id}",
            name=discovered.name,
            cwd=discovered.cwd,
            provider_id=discovered.provider_id,
            provider_session_id=discovered.provider_session_id,
        )

    def discover_sessions(self) -> None:
        """Discover provider sessions and add them to the session store."""

        for discovered_session in self._providers.discover_sessions():
            session = self._from_discovered(discovered_session)
            self._store.add(session)

    def get_all_sessions(self) -> tuple[Session, ...]:
        """Return all managed sessions."""

        return self._store.all()

    def get_session(self, session_id: str) -> Session:
        """Return a managed session by ID."""

        session = self._store.get(session_id)

        if session is None:
            raise RuntimeError(f"Session not found: {session_id}")

        return session

    def _get_provider_identity(self, session_id: str) -> tuple[str, str]:
        """Return the provider identity for a provider-backed session."""

        session = self.get_session(session_id)

        provider_id = session.provider_id
        provider_session_id = session.provider_session_id

        if provider_id is None or provider_session_id is None:
            raise RuntimeError(f"Session is not backed by a provider: {session_id}")

        return provider_id, provider_session_id

    def resume_command(self, session_id: str) -> tuple[str, ...]:
        """Return the command used to resume a managed provider session."""

        provider_id, provider_session_id = self._get_provider_identity(session_id)
        return self._providers.resume_command(provider_id, provider_session_id)

    async def delete_session(self, session_id: str) -> None:
        """Delete a provider session and remove it from the session store."""

        provider_id, provider_session_id = self._get_provider_identity(session_id)
        await self._providers.delete_session(provider_id, provider_session_id)
        self._store.remove(session_id)
