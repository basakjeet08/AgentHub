"""Service for coordinating coding-agent providers."""

from .protocol import DiscoveredSession, Provider
from .registry import DEFAULT_PROVIDER_FACTORIES


class ProviderService:
    """Coordinate operations across coding-agent providers."""

    def __init__(self, providers: tuple[Provider, ...] | None = None) -> None:
        """Initialize the provider service."""

        # Attach built in default providers.
        if providers is None:
            providers = self._default_providers()

        self._providers = {provider.provider_id: provider for provider in providers}

    @staticmethod
    def _default_providers() -> tuple[Provider, ...]:
        """Create the built-in coding-agent providers."""

        return tuple(factory() for factory in DEFAULT_PROVIDER_FACTORIES)

    def discover_sessions(self) -> tuple[DiscoveredSession, ...]:
        """Discover sessions from all providers."""

        return tuple(
            session
            for provider in self._providers.values()
            for session in provider.discover_sessions()
        )
