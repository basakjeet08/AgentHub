"""Unit coverage for the session controller lifecycle."""

from pathlib import Path

import pytest

from agenthub_v2.provider import ProviderService
from agenthub_v2.provider.protocol import DiscoveredSession
from agenthub_v2.session import Session, SessionController
from agenthub_v2.session.store import SessionStore


class RecordingProvider:
    """Stub provider that surfaces one discovered session and records lifecycle calls."""

    display_name = "Stub"
    icon = "🧪"

    def __init__(self, provider_id: str, *, deletion_raises: bool = False) -> None:
        self.provider_id = provider_id
        self.resume_calls: list[tuple[str, str]] = []
        self.delete_calls: list[str] = []
        self.deletion_raises = deletion_raises

    def discover_sessions(self) -> tuple[DiscoveredSession, ...]:
        """Return one stubbed discovered session."""

        return (
            DiscoveredSession(
                self.provider_id,
                f"{self.provider_id}-1",
                f"{self.provider_id} work",
                Path("/data"),
            ),
        )

    def resume_command(self, provider_session_id: str) -> tuple[str, ...]:
        """Record and return a stub resume command for the session."""

        self.resume_calls.append((self.provider_id, provider_session_id))
        return (self.provider_id, "resume", provider_session_id)

    async def delete_session(self, provider_session_id: str) -> None:
        """Record the requested deletion, optionally failing it."""

        if self.deletion_raises:
            raise RuntimeError("deletion failed")

        self.delete_calls.append(provider_session_id)


def _controller(provider: RecordingProvider) -> SessionController:
    return SessionController(SessionStore(), ProviderService((provider,)))


def test_discover_converts_and_stores_composite_sessions() -> None:
    controller = _controller(RecordingProvider("codex"))

    controller.discover_sessions()

    assert controller.get_all_sessions() == (
        Session(
            id="codex:codex-1",
            name="codex work",
            cwd=Path("/data"),
            provider_id="codex",
            provider_session_id="codex-1",
        ),
    )


def test_get_session_returns_existing_and_raises_for_missing() -> None:
    controller = _controller(RecordingProvider("codex"))
    controller.discover_sessions()
    session_id = "codex:codex-1"

    assert controller.get_session(session_id).id == session_id

    with pytest.raises(RuntimeError, match="missing-id"):
        controller.get_session("missing-id")


def test_resume_command_uses_stored_provider_identity() -> None:
    provider = RecordingProvider("codex")
    controller = _controller(provider)
    controller.discover_sessions()

    assert controller.resume_command("codex:codex-1") == (
        "codex",
        "resume",
        "codex-1",
    )
    assert provider.resume_calls == [("codex", "codex-1")]


async def test_delete_session_removes_only_after_successful_deletion() -> None:
    provider = RecordingProvider("codex")
    controller = _controller(provider)
    controller.discover_sessions()

    await controller.delete_session("codex:codex-1")

    assert provider.delete_calls == ["codex-1"]
    assert controller.get_all_sessions() == ()


async def test_failed_deletion_keeps_session_stored() -> None:
    controller = _controller(RecordingProvider("codex", deletion_raises=True))
    controller.discover_sessions()

    with pytest.raises(RuntimeError, match="deletion failed"):
        await controller.delete_session("codex:codex-1")

    assert "codex:codex-1" in {session.id for session in controller.get_all_sessions()}


def test_resume_on_non_provider_session_raises(tmp_path: Path) -> None:
    store = SessionStore()
    store.add(Session(id="shell-1", name="Shell", cwd=tmp_path))
    controller = SessionController(store, ProviderService(()))

    with pytest.raises(RuntimeError, match="not backed by a provider"):
        controller.resume_command("shell-1")


async def test_delete_on_non_provider_session_raises(tmp_path: Path) -> None:
    store = SessionStore()
    store.add(Session(id="shell-1", name="Shell", cwd=tmp_path))
    controller = SessionController(store, ProviderService(()))

    with pytest.raises(RuntimeError, match="not backed by a provider"):
        await controller.delete_session("shell-1")
