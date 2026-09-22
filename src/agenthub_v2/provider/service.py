"""Service for coordinating coding-agent providers."""

from .protocol import DiscoveredSession, Provider


class ProviderService:
    """Coordinate operations across coding-agent providers."""

    def __init__(self, providers: tuple[Provider, ...]) -> None:
        """Initialize the provider service."""

        self._providers = {provider.provider_id: provider for provider in providers}

    def discover_sessions(self) -> tuple[DiscoveredSession, ...]:
        """Discover sessions from all providers."""

        return tuple(
            session
            for provider in self._providers.values()
            for session in provider.discover_sessions()
        )
