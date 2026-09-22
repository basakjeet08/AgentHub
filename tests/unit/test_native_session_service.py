"""Tests for the provider-neutral native-session service boundary."""

from pathlib import Path

import pytest

from agenthub.native_sessions import (
    LaunchSpec,
    NativeSession,
    NativeSessionDeletionError,
    NativeSessionDiscoveryError,
    NativeSessionResumeError,
    NativeSessionService,
)


class StubAdapter:
    harness_id = "stub"
    supports_delete = True

    def __init__(self) -> None:
        self.discover_calls = 0
        self.resume_calls: list[NativeSession] = []
        self.delete_calls: list[NativeSession] = []
        self.sessions = (NativeSession("stub", "native-1", "Stub"),)

    def discover(self) -> tuple[NativeSession, ...]:
        self.discover_calls += 1
        return self.sessions

    async def resume(self, session: NativeSession) -> LaunchSpec:
        self.resume_calls.append(session)
        return LaunchSpec(("stub", "resume", session.native_session_id), Path.cwd())

    async def delete(self, session: NativeSession) -> None:
        self.delete_calls.append(session)


class KeyErrorDiscoveryAdapter(StubAdapter):
    def discover(self) -> tuple[NativeSession, ...]:
        raise KeyError("provider record")


def test_service_routes_operations_through_injected_registry() -> None:
    adapter = StubAdapter()
    service = NativeSessionService({"stub": adapter})

    assert service.harness_ids == ("stub",)
    assert service.delete_capability("stub") is True
    assert service.discover("stub") == adapter.sessions
    assert adapter.discover_calls == 1


async def test_service_routes_async_operations_through_injected_registry() -> None:
    adapter = StubAdapter()
    service = NativeSessionService({"stub": adapter})
    session = adapter.sessions[0]

    launch = await service.resume(session)
    await service.delete(session)

    assert launch.command == ("stub", "resume", "native-1")
    assert adapter.resume_calls == [session]
    assert adapter.delete_calls == [session]


def test_service_preserves_provider_key_errors_during_discovery() -> None:
    service = NativeSessionService({"stub": KeyErrorDiscoveryAdapter()})

    with pytest.raises(KeyError, match="provider record"):
        service.discover("stub")


@pytest.mark.parametrize(
    ("operation", "error_type"),
    (
        ("discover", NativeSessionDiscoveryError),
        ("resume", NativeSessionResumeError),
        ("delete", NativeSessionDeletionError),
    ),
)
async def test_service_reports_missing_provider_by_operation(
    operation: str,
    error_type: type[Exception],
) -> None:
    service = NativeSessionService({})
    session = NativeSession("missing", "native-1", "Missing")

    with pytest.raises(error_type, match="No native-session adapter"):
        if operation == "discover":
            service.discover("missing")
        elif operation == "resume":
            await service.resume(session)
        else:
            await service.delete(session)

    assert service.delete_capability("missing") is None
