"""Service for coordinating coding-agent providers."""

from .protocol import DiscoveredSession, Provider
from .registry import DEFAULT_PROVIDER_FACTORIES


class ProviderService:
    """Coordinate operations across coding-agent providers."""

    def __init__(self, providers: tuple[Provider, ...] | None = None) -> None:
        """Initialize the provider service."""

        if providers is None:
            providers = self._default_providers()

        self._providers = {provider.provider_id: provider for provider in providers}

    @staticmethod
    def _default_providers() -> tuple[Provider, ...]:
        """Create the built-in coding-agent providers."""

        return tuple(factory() for factory in DEFAULT_PROVIDER_FACTORIES)

    def _get_provider(self, provider_id: str) -> Provider:
        """Return a registered provider by ID."""

        provider = self._providers.get(provider_id)

        if provider is None:
            raise RuntimeError(f"No provider registered for {provider_id}.")

        return provider

    def discover_sessions(self) -> tuple[DiscoveredSession, ...]:
        """Discover sessions from all providers."""

        return tuple(
            session
            for provider in self._providers.values()
            for session in provider.discover_sessions()
        )

    def resume_command(
        self,
        provider_id: str,
        provider_session_id: str,
    ) -> tuple[str, ...]:
        """Return the command used to resume a provider session."""

        provider = self._get_provider(provider_id)
        return provider.resume_command(provider_session_id)

    async def delete_session(
        self,
        provider_id: str,
        provider_session_id: str,
    ) -> None:
        """Delete a provider session."""

        provider = self._get_provider(provider_id)
        await provider.delete_session(provider_session_id)
