"""Provider-neutral contracts for coding-agent providers."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class DiscoveredSession:
    """Session metadata discovered from a coding-agent provider."""

    provider_id: str
    provider_session_id: str
    name: str
    cwd: Path


class Provider(Protocol):
    """Capabilities exposed by one coding-agent provider."""

    display_name: str
    icon: str
    provider_id: str

    def discover_sessions(self) -> tuple[DiscoveredSession, ...]:
        """Discover sessions owned by the provider."""
        ...

    def resume_command(self, provider_session_id: str) -> tuple[str, ...]:
        """Return the command used to resume a provider session."""
        ...

    async def delete_session(self, provider_session_id: str) -> None:
        """Delete a provider session."""
        ...
