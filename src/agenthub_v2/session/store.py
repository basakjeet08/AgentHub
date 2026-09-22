"""In-memory store for AgentHub sessions."""

from .model import Session


class SessionStore:
    """Source of truth for AgentHub session state."""

    def __init__(self) -> None:
        """Initialize an empty session store."""

        self._sessions: dict[str, Session] = {}

    def add(self, session: Session) -> None:
        """Add a session to the store."""

        self._sessions[session.id] = session

    def get(self, session_id: str) -> Session | None:
        """Return a session by ID."""

        return self._sessions.get(session_id)

    def all(self) -> tuple[Session, ...]:
        """Return all sessions."""

        return tuple(self._sessions.values())

    def remove(self, session_id: str) -> None:
        """Remove a session by ID."""

        self._sessions.pop(session_id, None)
