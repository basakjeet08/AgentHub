"""Unit coverage for the provider coordination service."""

from pathlib import Path

import pytest

from agenthub_v2.provider import ProviderService
from agenthub_v2.provider.protocol import DiscoveredSession


class StubProvider:
    """Minimal provider implementing the full discovery lifecycle protocol."""

    display_name = "Stub"
    icon = "🧪"

    def __init__(
        self,
        provider_id: str,
        sessions: tuple[DiscoveredSession, ...] = (),
    ) -> None:
        self.provider_id = provider_id
        self._sessions = sessions
        self.resume_calls: list[tuple[str, str]] = []
        self.delete_calls: list[str] = []

    def discover_sessions(self) -> tuple[DiscoveredSession, ...]:
        """Return the stubbed discovered sessions."""

        return self._sessions

    def resume_command(self, provider_session_id: str) -> tuple[str, ...]:
        """Record and return a stub resume command for the session."""

        self.resume_calls.append((self.provider_id, provider_session_id))
        return (self.provider_id, "resume", provider_session_id)

    async def delete_session(self, provider_session_id: str) -> None:
        """Record the requested deletion without performing any operation."""

        self.delete_calls.append(provider_session_id)


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


def test_resume_command_routes_to_requested_provider(tmp_path: Path) -> None:
    codex = StubProvider("codex")
    devin = StubProvider("devin")
    service = ProviderService((codex, devin))

    assert service.resume_command("codex", "codex-1") == ("codex", "resume", "codex-1")
    assert codex.resume_calls == [("codex", "codex-1")]
    assert devin.resume_calls == []


async def test_delete_session_delegates_to_requested_provider() -> None:
    codex = StubProvider("codex")
    devin = StubProvider("devin")
    service = ProviderService((codex, devin))

    await service.delete_session("devin", "devin-1")

    assert devin.delete_calls == ["devin-1"]
    assert codex.delete_calls == []


def test_unknown_provider_id_raises_runtime_error() -> None:
    service = ProviderService(())

    with pytest.raises(RuntimeError, match="nope"):
        service.resume_command("nope", "any-id")


async def test_unknown_provider_id_raises_for_deletion() -> None:
    service = ProviderService(())

    with pytest.raises(RuntimeError, match="nope"):
        await service.delete_session("nope", "any-id")
