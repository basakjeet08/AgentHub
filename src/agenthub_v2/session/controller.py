"""Application controller for AgentHub session operations."""

from agenthub_v2.provider import ProviderService

from .store import SessionStore


class SessionController:
    """Application controller for AgentHub session state operations."""

    def __init__(
        self,
        store: SessionStore,
        providers: ProviderService,
    ) -> None:
        """Initialize the session controller."""

        self._store = store
        self._providers = providers
