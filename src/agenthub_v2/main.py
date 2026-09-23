"""Entry point for the AgentHub TUI application."""

from pathlib import Path

from agenthub_v2.provider import ProviderService
from agenthub_v2.session import Session


def main() -> int | None:
    """Main entry point for the application."""

    session = Session(
        id="test-session-1",
        name="Test Session",
        cwd=Path.cwd(),
        provider_id="codex",
        provider_session_id="codex-test-123",
    )

    print(session)

    print(f"ID: {session.id}")
    print(f"Name: {session.name}")
    print(f"CWD: {session.cwd}")
    print(f"Loaded: {session.is_loaded}")
    print(f"Shell: {session.is_shell}")
    print(f"Provider: {session.provider_id}")
    print(f"Provider Session ID: {session.provider_session_id}")
    print(f"Activity: {session.activity}")

    # Creating the provider service that will later be used by controllers.
    provider_service = ProviderService()
    sessions = provider_service.discover_sessions()

    for discovered_sessions in sessions:
        print(discovered_sessions)

    return None
