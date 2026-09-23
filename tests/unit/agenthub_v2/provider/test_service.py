"""Unit coverage for the provider coordination service."""

from pathlib import Path

from agenthub_v2.provider import ProviderService
from agenthub_v2.provider.protocol import DiscoveredSession


class StubProvider:
    """Minimal provider implementing the discovery protocol."""

    display_name = "Stub"
    icon = "🧪"

    def __init__(
        self,
        provider_id: str,
        sessions: tuple[DiscoveredSession, ...],
    ) -> None:
        self.provider_id = provider_id
        self._sessions = sessions

    def discover_sessions(self) -> tuple[DiscoveredSession, ...]:
        """Return the stubbed discovered sessions."""

        return self._sessions


def test_service_aggregates_sessions_from_injected_providers(
    tmp_path: Path,
) -> None:
    first = StubProvider("codex", (DiscoveredSession("codex", "codex-1", "Codex work", tmp_path),))
    second = StubProvider("devin", (DiscoveredSession("devin", "devin-1", "Devin work", tmp_path),))

    service = ProviderService((first, second))

    assert service.discover_sessions() == (
        DiscoveredSession("codex", "codex-1", "Codex work", tmp_path),
        DiscoveredSession("devin", "devin-1", "Devin work", tmp_path),
    )


def test_service_with_no_providers_discovers_nothing() -> None:
    assert ProviderService(()).discover_sessions() == ()
